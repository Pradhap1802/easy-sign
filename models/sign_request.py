# -*- coding: utf-8 -*-
import base64
import io
import os
import uuid
import time
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.rl_config import TTFSearchPath
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from markupsafe import Markup
from datetime import timedelta
from PIL import UnidentifiedImageError

from odoo import api, fields, models, _, Command, tools
from odoo.tools import get_lang, is_html_empty, format_list, format_date
from odoo.exceptions import UserError, ValidationError
from odoo.tools.pdf import PdfFileReader, PdfFileWriter, PdfReadError, reshape_text


def _fix_image_transparency(image):
    pixels = image.load()
    for x in range(image.size[0]):
        for y in range(image.size[1]):
            if pixels[x, y] == (0, 0, 0, 0):
                pixels[x, y] = (255, 255, 255, 0)


class SignRequest(models.Model):
    _name = "sign.request"
    _description = "Signature Request"
    _rec_name = 'reference'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    def _default_access_token(self):
        return str(uuid.uuid4())

    template_id = fields.Many2one('sign.template', string="Template")
    document = fields.Binary(string="Document", attachment=True)
    document_filename = fields.Char(string="Document Filename")
    subject = fields.Char(string="Email Subject")
    reference = fields.Char(required=True, string="Document Name", help="This is how the document will be named in the mail", default="New Signature Request")
    access_token = fields.Char('Security Token', required=True, default=_default_access_token, readonly=True, copy=False)
    request_item_ids = fields.One2many('sign.request.item', 'sign_request_id', string="Signers", copy=True)
    state = fields.Selection([
        ("sent", "To Sign"),
        ("signed", "Fully Signed"),
        ("canceled", "Cancelled"),
        ("expired", "Expired"),
    ], default='sent', tracking=True, group_expand=True, copy=False, index=True)
    completed_document = fields.Binary(readonly=True, string="Completed Document", attachment=True, copy=False)
    validity_date = fields.Date(
        string="Valid Until",
        default=lambda self: fields.Date.today() + timedelta(days=60)
    )
    signer_info = fields.Html(string="Signers", compute="_compute_signer_info")
    
    @api.onchange('document')
    def _onchange_document(self):
        if self.document:
            # Create a new template from the uploaded document
            if not self.reference:
                self.reference = self.document_filename or "New Signature Request"
            template = self.env['sign.template'].create({
                'name': self.reference,
                'attachment_id': self.env['ir.attachment'].create({
                    'name': self.document_filename or "Document",
                    'datas': self.document,
                    'type': 'binary',
                }).id,
            })
            self.template_id = template
    nb_wait = fields.Integer(string="Sent Requests", compute="_compute_stats", store=True)
    nb_closed = fields.Integer(string="Completed Signatures", compute="_compute_stats", store=True)
    nb_total = fields.Integer(string="Requested Signatures", compute="_compute_stats", store=True)
    progress = fields.Char(string="Progress", compute="_compute_progress", compute_sudo=True)
    start_sign = fields.Boolean(string="Signature Started", compute="_compute_progress", compute_sudo=True)
    active = fields.Boolean(default=True, string="Active", copy=False)
    completion_date = fields.Date(string="Completion Date", compute="_compute_progress", compute_sudo=True)
    sign_log_ids = fields.One2many('sign.log', 'sign_request_id', string="Logs", help="Activity logs linked to this request")

    @api.depends('request_item_ids.state')
    def _compute_stats(self):
        for rec in self:
            rec.nb_total = len(rec.request_item_ids)
            rec.nb_wait = len(rec.request_item_ids.filtered(lambda sri: sri.state == 'sent'))
            rec.nb_closed = rec.nb_total - rec.nb_wait

    @api.depends('request_item_ids.state')
    def _compute_progress(self):
        for rec in self:
            rec.start_sign = bool(rec.nb_closed)
            rec.progress = "{} / {}".format(rec.nb_closed, rec.nb_total)
            rec.completion_date = rec.request_item_ids.sorted(key="signing_date", reverse=True)[:1].signing_date if not rec.nb_wait else None

    @api.depends('request_item_ids.partner_id.name', 'request_item_ids.state')
    def _compute_signer_info(self):
        for rec in self:
            badges = []
            for item in rec.request_item_ids:
                color = '#94a3b8'
                if item.state == 'completed':
                    color = '#10b981'
                elif item.state in ('sent', 'viewed'):
                    color = '#fb923c'
                badges.append(
                    f'<span class="badge" style="background: rgba(255,255,255,0.05); color: {color}; border: 1px solid {color}33; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-right: 4px; display: inline-block; margin-bottom: 2px;">{item.partner_id.name}</span>'
                )
            rec.signer_info = Markup(' '.join(badges))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('template_id') and not vals.get('document'):
                raise ValidationError(_("Please either select a template or upload a document"))
            if vals.get('document') and not vals.get('template_id'):
                # Create a new template from the uploaded document
                attachment = self.env['ir.attachment'].create({
                    'name': vals.get('document_filename') or vals.get('reference') or "Document",
                    'datas': vals.get('document'),
                    'type': 'binary',
                })
                template = self.env['sign.template'].create({
                    'name': vals.get('reference') or "New Template",
                    'attachment_id': attachment.id,
                })
                vals['template_id'] = template.id
        sign_requests = super().create(vals_list)
        for sign_request in sign_requests:
            if not sign_request.request_item_ids:
                raise ValidationError(_("A valid sign request needs at least one sign request item"))
            self.env['sign.log'].sudo().create({'sign_request_id': sign_request.id, 'action': 'create'})
        if not self._context.get('no_sign_mail'):
            sign_requests.send_signature_accesses()
        return sign_requests

    def copy_data(self, default=None):
        return super().copy_data(default=default)

    def go_to_document(self):
        self.ensure_one()
        return {
            'name': self.reference,
            'type': 'ir.actions.client',
            'tag': 'sign.Document',
            'context': {
                'id': self.id,
                'token': self.access_token,
                'state': self.state,
            },
        }

    def go_to_signable_document(self, request_items=None):
        self.ensure_one()
        if not request_items:
            request_items = self.request_item_ids.filtered(lambda r: not r.partner_id or (r.state == 'sent' and r.partner_id.id == self.env.user.partner_id.id))
        if not request_items:
            return
        return {
            'name': self.reference,
            'type': 'ir.actions.client',
            'tag': 'sign.SignableDocument',
            'context': {
                'id': self.id,
                'token': request_items[:1].sudo().access_token,
                'state': self.state,
            },
        }

    def get_completed_document(self):
        if not self:
            raise UserError(_('You should select at least one document to download.'))
        if len(self) < 2:
            return {
                'name': 'Signed Document',
                'type': 'ir.actions.act_url',
                'url': '/sign/download/%(request_id)s/%(access_token)s/completed' % {'request_id': self.id, 'access_token': self.access_token},
            }

    def go_to_edit_template(self):
        self.ensure_one()
        if not self.template_id:
            raise UserError(_('Please upload a document or select a template first.'))
        return self.template_id.go_to_custom_template()

    def open_logs(self):
        self.ensure_one()
        return {
            "name": _("Activity Logs"),
            "type": "ir.actions.act_window",
            "res_model": "sign.log",
            'view_mode': 'list,form',
            'domain': [('sign_request_id', '=', self.id)],
        }

    def cancel(self):
        for sign_request in self:
            sign_request.write({'access_token': self._default_access_token(), 'state': 'canceled'})
        self.request_item_ids._cancel()
        self.env['sign.log'].sudo().create([{'sign_request_id': sign_request.id, 'action': 'cancel'} for sign_request in self])

    def send_signature_accesses(self):
        allowed_request_ids = self.filtered(lambda sr: sr.state == 'sent')
        for sign_request in allowed_request_ids:
            sign_request.request_item_ids.send_signature_accesses()

    def action_resend(self):
        for rec in self:
            rec.send_signature_accesses()

    def _sign(self):
        self.ensure_one()
        if self.state != 'sent' or any(sri.state != 'completed' for sri in self.request_item_ids):
            raise UserError(_("This sign request cannot be signed"))
        self.write({'state': 'signed'})
        self._send_completed_document()

    def _send_completed_document(self):
        self.ensure_one()
        if self.state != 'signed':
            raise UserError(_('The sign request has not been fully signed'))
        if not self.completed_document:
            self._generate_completed_document()
        for sign_request_item in self.request_item_ids:
            self._send_completed_document_mail(sign_request_item.partner_id, access_token=sign_request_item.sudo().access_token, force_send=True)

    def _send_completed_document_mail(self, partner, access_token=None, force_send=False):
        self.ensure_one()
        if access_token is None:
            access_token = self.access_token
        partner_lang = get_lang(self.env, lang_code=partner.lang).code if partner else 'en_US'
        base_url = self.get_base_url()
        subject = '%s signed' % self.reference
        body = self.env['ir.qweb']._render('easy_sign.sign_template_mail_completed', {
            'record': self,
            'link': '%s/sign/document/%s/%s' % (base_url, self.id, access_token),
            'subject': subject,
            'recipient_name': partner.name if partner else '',
        }, lang=partner_lang, minimal_qcontext=True)
        notification_template = 'mail.mail_notification_light'
        self._message_send_mail(
            body, notification_template,
            {'record_name': self.reference},
            {'model_description': _('Signature')},
            {'email_to': partner.email if partner else ''},
            force_send=force_send,
            lang=partner_lang,
        )

    def _refuse(self, refuser, refusal_reason):
        self.ensure_one()
        if self.state != 'sent':
            raise UserError(_("This sign request cannot be refused"))
        self.write({'state': 'canceled'})
        self.request_item_ids._cancel()

    def _message_send_mail(self, body, template_xmlid, record_name, model_description, email_values, **kwargs):
        self.ensure_one()
        mail_values = {
            'subject': email_values.get('subject', _('Signature Request')),
            'body_html': body,
            'email_to': email_values.get('email_to', ''),
            'res_id': self.id,
            'model': self._name,
        }
        if email_values.get('attachment_ids'):
            mail_values['attachment_ids'] = [Command.set(email_values['attachment_ids'])]
        mail = self.env['mail.mail'].sudo().create(mail_values)
        if kwargs.get('force_send'):
            mail.send()
        return mail

    @staticmethod
    def get_page_size(pdf_reader):
        max_width = max_height = 0
        for page in pdf_reader.pages:
            media_box = page.mediaBox
            width = media_box and media_box.getWidth()
            height = media_box and media_box.getHeight()
            max_width = width if width > max_width else max_width
            max_height = height if height > max_height else max_height
        return (max_width, max_height) if max_width and max_height else None

    def _generate_completed_document(self):
        self.ensure_one()
        if self.state != 'signed':
            raise UserError(_("The completed document cannot be created because the sign request is not fully signed"))
        if not self.template_id.sign_item_ids:
            self.completed_document = self.template_id.attachment_id.datas
        else:
            try:
                old_pdf = PdfFileReader(io.BytesIO(base64.b64decode(self.template_id.attachment_id.datas)), strict=False, overwriteWarnings=False)
            except Exception:
                raise ValidationError(_("ERROR: Invalid PDF file!"))
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=self.get_page_size(old_pdf))
            itemsByPage = {}
            for item in self.template_id.sign_item_ids:
                if item.page not in itemsByPage:
                    itemsByPage[item.page] = []
                itemsByPage[item.page].append(item)
            items_ids = [id for items in itemsByPage.values() for id in items.ids]
            values_dict = self.env['sign.request.item.value'].sudo().search_read(
                [('sign_item_id', 'in', items_ids), ('sign_request_id', '=', self.id)],
                ['sign_item_id', 'value', 'frame_value']
            )
            values = {}
            for v in values_dict:
                values[v['sign_item_id']] = {
                    'value': v['value'],
                    'frame': v['frame_value'],
                }
            for p in range(0, old_pdf.getNumPages()):
                page = old_pdf.getPage(p)
                width = float(abs(page.mediaBox.getWidth()))
                height = float(abs(page.mediaBox.getHeight()))
                rotation = page['/Rotate'] if '/Rotate' in page else 0
                if rotation and isinstance(rotation, int):
                    can.rotate(rotation)
                    if rotation == 90:
                        width, height = height, width
                        can.translate(0, -height)
                    elif rotation == 180:
                        can.translate(-width, -height)
                    elif rotation == 270:
                        width, height = height, width
                        can.translate(-width, 0)
                items = itemsByPage.get(p + 1, [])
                for item in items:
                    value_dict = values.get(item.id)
                    if not value_dict:
                        continue
                    value = value_dict['value']
                    frame = value_dict.get('frame')
                    if frame:
                        try:
                            image_reader = ImageReader(io.BytesIO(base64.b64decode(frame[frame.find(',')+1:])))
                        except UnidentifiedImageError:
                            raise ValidationError(_("There was an issue downloading your document. Please contact an administrator."))
                        _fix_image_transparency(image_reader._image)
                        can.drawImage(
                            image_reader,
                            width*item.posX,
                            height*(1-item.posY-item.height),
                            width*item.width,
                            height*item.height,
                            'auto',
                            True
                        )
                    if item.type_id.item_type == "text":
                        value = reshape_text(value)
                        can.setFont("Helvetica", height*item.height*0.8)
                        if item.alignment == "left":
                            can.drawString(width*item.posX, height*(1-item.posY-item.height*0.9), value)
                        elif item.alignment == "right":
                            can.drawRightString(width*(item.posX+item.width), height*(1-item.posY-item.height*0.9), value)
                        else:
                            can.drawCentredString(width*(item.posX+item.width/2), height*(1-item.posY-item.height*0.9), value)
                    elif item.type_id.item_type == "checkbox":
                        can.setFont("Helvetica", height*item.height*0.8)
                        value_text = 'X' if value == 'on' else ''
                        can.drawString(width*item.posX, height*(1-item.posY-item.height*0.9), value_text)
                    elif item.type_id.item_type in ["signature", "initial"]:
                        try:
                            image_reader = ImageReader(io.BytesIO(base64.b64decode(value[value.find(',')+1:])))
                        except UnidentifiedImageError:
                            raise ValidationError(_("There was an issue downloading your document. Please contact an administrator."))
                        _fix_image_transparency(image_reader._image)
                        can.drawImage(image_reader, width*item.posX, height*(1-item.posY-item.height), width*item.width, height*item.height, 'auto', True)
                can.showPage()
            can.save()
            item_pdf = PdfFileReader(packet, overwriteWarnings=False)
            new_pdf = PdfFileWriter()
            for p in range(0, old_pdf.getNumPages()):
                page = old_pdf.getPage(p)
                page.mergePage(item_pdf.getPage(p))
                new_pdf.addPage(page)
            output = io.BytesIO()
            new_pdf.write(output)
            self.completed_document = base64.b64encode(output.getvalue())
            output.close()
        self.env['ir.attachment'].create({
            'name': "%s.pdf" % self.reference if self.reference.split('.')[-1] != 'pdf' else self.reference,
            'datas': self.completed_document,
            'type': 'binary',
            'res_model': self._name,
            'res_id': self.id,
        })
