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
    
    @api.onchange('document')
    def _onchange_document(self):
        if self.document:
            # Create a new template from the uploaded document
            if not self.reference:
                self.reference = self.document_filename or "New Signature Request"
            template = self.env['sign.template'].create({
                'name': self.reference,
                'datas': self.document,
            })
            self.template_id = template
    signer_ids = fields.One2many('sign.request.signer', 'sign_request_id', string="Signers")
    nb_wait = fields.Integer(string="Sent Requests", compute="_compute_stats", store=True)
    nb_closed = fields.Integer(string="Completed Signatures", compute="_compute_stats", store=True)
    nb_total = fields.Integer(string="Requested Signatures", compute="_compute_stats", store=True)
    progress = fields.Char(string="Progress", compute="_compute_progress", compute_sudo=True)
    start_sign = fields.Boolean(string="Signature Started", compute="_compute_progress", compute_sudo=True)
    active = fields.Boolean(default=True, string="Active", copy=False)
    completion_date = fields.Date(string="Completion Date", compute="_compute_progress", compute_sudo=True)
    sign_log_ids = fields.One2many('sign.log', 'sign_request_id', string="Logs", help="Activity logs linked to this request")
    tag_ids = fields.Many2many('sign.tag', 'sign_request_tag_rel', 'request_id', 'tag_id', string="Tags")

    @api.depends('state', 'signer_ids.state')
    def _compute_stats(self):
        for rec in self:
            if rec.signer_ids:
                rec.nb_total = len(rec.signer_ids)
                rec.nb_wait = len(rec.signer_ids.filtered(lambda s: s.state in ('sent', 'draft')))
                rec.nb_closed = len(rec.signer_ids.filtered(lambda s: s.state == 'signed'))
            else:
                rec.nb_total = 1
                rec.nb_wait = 1 if rec.state == 'sent' else 0
                rec.nb_closed = 1 if rec.state == 'signed' else 0

    @api.depends('state', 'signer_ids.state')
    def _compute_progress(self):
        for rec in self:
            if rec.signer_ids:
                total = len(rec.signer_ids)
                signed = len(rec.signer_ids.filtered(lambda s: s.state == 'signed'))
                rec.start_sign = (signed > 0)
                rec.progress = "%d / %d" % (signed, total)
                rec.completion_date = fields.Date.today() if rec.state == 'signed' else None
            else:
                rec.start_sign = (rec.state == 'signed')
                rec.progress = "1 / 1" if rec.state == 'signed' else "0 / 1"
                rec.completion_date = fields.Date.today() if rec.state == 'signed' else None

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('template_id') and not vals.get('document'):
                raise ValidationError(_("Please either select a template or upload a document"))
            if vals.get('document') and not vals.get('template_id'):
                # Create a new template from the uploaded document
                template = self.env['sign.template'].create({
                    'name': vals.get('reference') or "New Template",
                    'datas': vals.get('document'),
                })
                vals['template_id'] = template.id
        sign_requests = super().create(vals_list)
        for sign_request in sign_requests:
            self.env['sign.log'].sudo().create({'sign_request_id': sign_request.id, 'action': 'create'})
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

    def go_to_signable_document(self):
        self.ensure_one()
        # Use the first active (sent) signer's token so the route matches sign.request.signer
        active_signer = self.signer_ids.filtered(lambda s: s.state == 'sent')
        if active_signer:
            token = active_signer[0].access_token
        else:
            token = self.access_token
        return {
            'name': self.reference,
            'type': 'ir.actions.act_url',
            'url': '/sign/document/%d/%s' % (self.id, token),
            'target': 'self',
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
        if self.state in ('signed', 'canceled'):
            raise UserError(_('You cannot edit the template of a signed or cancelled document.'))
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
        self.env['sign.log'].sudo().create([{'sign_request_id': sign_request.id, 'action': 'cancel'} for sign_request in self])

    def action_open_send_wizard(self):
        self.ensure_one()
        return {
            'name': _('Send Signature Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'sign.request.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.id,
                'default_subject': _('Signature Request: %s') % self.reference,
            }
        }



    def _send_signer_email(self, signer):
        self.ensure_one()
        base_url = self.get_base_url()
        lang = get_lang(self.env, signer.partner_id.lang).code if signer.partner_id.lang else 'en_US'
        link = "%s/sign/document/%s/%s" % (base_url, self.id, signer.access_token)
        subject = self.subject or (_('Signature Request: %s') % self.reference)
        body = self.env['ir.qweb']._render('easy_sign.sign_template_mail', {
            'record': self,
            'recipient': signer.partner_id,
            'link': link,
            'subject': subject,
        }, lang=lang, minimal_qcontext=True)
        self._message_send_mail(
            body,
            'mail.mail_notification_light',
            {'record_name': self.reference},
            {'model_description': _('Signature')},
            {'email_to': signer.partner_id.email, 'subject': subject},
            force_send=True,
            lang=lang,
        )
        self.env['sign.log'].sudo().create({
            'sign_request_id': self.id,
            'partner_id': signer.partner_id.id,
            'action': 'send',
        })

    def action_send_next_signature_request(self):
        self.ensure_one()
        pending_signers = self.signer_ids.filtered(lambda s: s.state == 'draft')
        if pending_signers:
            next_signer = sorted(pending_signers, key=lambda s: s.sequence)[0]
            next_signer.write({'state': 'sent'})
            self._send_signer_email(next_signer)
        else:
            sent_unsigned = self.signer_ids.filtered(lambda s: s.state == 'sent')
            if sent_unsigned:
                next_signer = sorted(sent_unsigned, key=lambda s: s.sequence)[0]
                self._send_signer_email(next_signer)
            elif all(s.state == 'signed' for s in self.signer_ids) or not self.signer_ids:
                self.write({'state': 'signed'})
                self._generate_completed_document()


    def _sign(self, signature_values):
        self._sign_with_signer(signature_values, False)

    def _sign_with_signer(self, signature_values, signer=False):
        self.ensure_one()
        if self.state != 'sent':
            raise UserError(_("This signature request has already been processed or cancelled"))
        
        # Save signature values
        SignRequestItemValue = self.env['sign.request.item.value']
        for sign_item_id, value in signature_values.items():
            if isinstance(value, dict):
                frame_value = value.get('frame')
                value = value.get('value')
            else:
                frame_value = None
            SignRequestItemValue.sudo().create({
                'sign_request_id': self.id,
                'sign_item_id': int(sign_item_id),
                'value': value,
                'frame_value': frame_value,
            })
            
        # Log signature action
        partner = signer.partner_id if signer else self.env.user.partner_id
        self.env['sign.log'].sudo().create({
            'sign_request_id': self.id,
            'partner_id': partner.id,
            'action': 'sign',
        })
        
        if signer:
            signer.write({'state': 'signed'})
            self.action_send_next_signature_request()
        else:
            self.write({'state': 'signed'})
            self._generate_completed_document()

    def _refuse(self, refuser, refusal_reason):
        self.ensure_one()
        if self.state != 'sent':
            raise UserError(_("This sign request cannot be refused"))
        self.write({'state': 'canceled'})

    def _message_send_mail(self, body, template_xmlid, record_name, model_description, email_values, **kwargs):
        self.ensure_one()
        email_from = email_values.get('email_from')
        if not email_from:
            company = self.env.company
            email_from = company.email_formatted or self.create_uid.email_formatted or self.env.user.email_formatted
            if not email_from and company.email:
                email_from = tools.formataddr((company.name, company.email))
            if not email_from:
                email_from = self.env['ir.config_parameter'].sudo().get_param('mail.default.from')

        mail_values = {
            'subject': email_values.get('subject', _('Signature Request')),
            'body_html': body,
            'email_to': email_values.get('email_to', ''),
            'email_from': email_from,
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
            self.completed_document = self.template_id.datas
        else:
            try:
                old_pdf = PdfFileReader(io.BytesIO(base64.b64decode(self.template_id.datas)), strict=False, overwriteWarnings=False)
            except Exception:
                raise ValidationError(_("ERROR: Invalid PDF file!"))
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=self.get_page_size(old_pdf))
            itemsByPage = {}
            for item in self.template_id.sign_item_ids:
                if item.page not in itemsByPage:
                    itemsByPage[item.page] = []
                itemsByPage[item.page].append(item)
            items_ids = self.template_id.sign_item_ids.ids
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

    @api.model
    def _cron_check_expired(self):
        today = fields.Date.today()
        expired_requests = self.search([
            ('state', '=', 'sent'),
            ('validity_date', '<', today)
        ])
        for req in expired_requests:
            req.write({'state': 'expired'})
            self.env['sign.log'].sudo().create({
                'sign_request_id': req.id,
                'action': 'expire',
                'partner_id': False,
                'user_id': False,
            })



class SignRequestSigner(models.Model):
    _name = "sign.request.signer"
    _description = "Sign Request Signer"
    _order = "sequence, id"

    def _default_access_token(self):
        return str(uuid.uuid4())

    sign_request_id = fields.Many2one('sign.request', string="Sign Request", required=True, ondelete='cascade')
    role_id = fields.Many2one('sign.item.role', string="Role", required=True)
    partner_id = fields.Many2one('res.partner', string="Recipient", required=True)
    state = fields.Selection([
        ('draft', 'Waiting'),
        ('sent', 'Signing'),
        ('signed', 'Signed'),
        ('canceled', 'Canceled')
    ], default='draft', required=True)
    access_token = fields.Char('Security Token', required=True, default=_default_access_token, readonly=True, copy=False)
    sequence = fields.Integer(string="Sequence", default=10)
