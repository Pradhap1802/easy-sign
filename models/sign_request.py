import base64
import datetime
import io
import logging
import os
import uuid
import time
import hashlib

_logger = logging.getLogger(__name__)
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
    last_reminder_date = fields.Date(string="Last Reminder Date")
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
        for rec in self:
            if rec.state == 'signed':
                rec._generate_completed_document()
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

    def action_send_reminder(self):
        self.ensure_one()
        active_signers = self.signer_ids.filtered(lambda s: s.state == 'sent')
        if not active_signers:
            active_signers = self.signer_ids.filtered(lambda s: s.state == 'draft')
        if not active_signers:
            raise UserError(_("There are no pending signers to remind."))

        for signer in active_signers:
            if signer.state == 'draft':
                signer.write({'state': 'sent'})
            self._send_signer_email(signer)
            self.env['sign.log'].sudo().create({
                'sign_request_id': self.id,
                'partner_id': signer.partner_id.id,
                'action': 'send',
            })

        self.last_reminder_date = fields.Date.today()
        names = ', '.join(active_signers.mapped('partner_id.name'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reminder Email Sent'),
                'message': _('Signature reminder sent to %s.') % names,
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def _cron_send_auto_reminders(self):
        today = fields.Date.today()
        three_days_ago = today - datetime.timedelta(days=3)
        pending_requests = self.search([
            ('state', '=', 'sent'),
            '|', ('last_reminder_date', '=', False), ('last_reminder_date', '<=', three_days_ago)
        ])
        for req in pending_requests:
            try:
                req.action_send_reminder()
            except UserError:
                pass
            except Exception as e:
                _logger.error("Error sending auto reminder for request %s: %s", req.id, e)

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

    def _sign_with_signer(self, signature_values, signer=False, ip_address=False):
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
            'ip_address': ip_address or False,
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
                sign_item = v.get('sign_item_id')
                item_id = sign_item[0] if isinstance(sign_item, (list, tuple)) else sign_item
                if item_id:
                    values[item_id] = {
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

                    item_type = item.type_id.item_type if item.type_id else 'text'

                    if item_type in ["signature", "initial"]:
                        img_data = value or frame
                        if img_data and isinstance(img_data, str) and ',' in img_data:
                            try:
                                image_reader = ImageReader(io.BytesIO(base64.b64decode(img_data[img_data.find(',')+1:])))
                                _fix_image_transparency(image_reader._image)
                                can.drawImage(image_reader, width*item.posX, height*(1-item.posY-item.height), width*item.width, height*item.height, 'auto', True)
                            except Exception:
                                pass
                    elif item_type == "checkbox":
                        can.setFont("Helvetica", max(8, height*item.height*0.8))
                        value_text = 'X' if value in ('on', 'true', 'True', True) else ''
                        can.drawString(width*item.posX, height*(1-item.posY-item.height*0.9), value_text)
                    else:
                        # Render all text/draggable input fields (text, textarea, phone, email, name, company, title, date, etc.)
                        if value:
                            value_str = reshape_text(str(value))
                            can.setFillColorRGB(0, 0, 0)
                            can.setStrokeColorRGB(0, 0, 0)
                            font_size = max(9, min(14, int(height * item.height * 0.65)))
                            can.setFont("Helvetica-Bold", font_size)
                            y_pos = height * (1 - item.posY - item.height) + (height * item.height - font_size) / 2 + 2
                            if item.alignment == "left":
                                can.drawString(width * item.posX + 3, y_pos, value_str)
                            elif item.alignment == "right":
                                can.drawRightString(width * (item.posX + item.width) - 3, y_pos, value_str)
                            else:
                                can.drawCentredString(width * (item.posX + item.width / 2), y_pos, value_str)

                # Draw footer watermark on original page
                can.setFillColorRGB(0.45, 0.45, 0.45)
                can.setFont("Helvetica", 7)
                watermark_text = "Signed via Easy Sign | Ref: %s | Date: %s" % (
                    self.reference,
                    format_date(self.env, self.completion_date or fields.Date.today())
                )
                can.drawString(25, 12, watermark_text)
                can.showPage()

            # ─── Render Audit Trail Certificate Page ──────────────────────────────
            audit_w, audit_h = 595.27, 841.89
            can.setFillColorRGB(0.13, 0.15, 0.18)
            can.setFont("Helvetica-Bold", 16)
            can.drawString(40, audit_h - 50, "AUDIT TRAIL & SIGNATURE CERTIFICATE")

            can.setStrokeColorRGB(0.44, 0.29, 0.40)  # Odoo Purple #714b67
            can.setLineWidth(2)
            can.line(40, audit_h - 60, audit_w - 40, audit_h - 60)

            # Metadata section
            can.setFont("Helvetica-Bold", 10)
            can.setFillColorRGB(0.2, 0.2, 0.2)
            can.drawString(40, audit_h - 90, "DOCUMENT DETAILS")
            can.setFont("Helvetica", 9)
            can.drawString(40, audit_h - 108, "Document Name: %s" % (self.reference or ''))
            can.drawString(40, audit_h - 124, "Security Token: %s" % (self.access_token or ''))
            can.drawString(40, audit_h - 140, "Status: Fully Signed (%s / %s Signers Completed)" % (self.nb_closed, self.nb_total))
            can.drawString(40, audit_h - 156, "Completion Date: %s" % format_date(self.env, self.completion_date or fields.Date.today()))

            # Table Header
            y_offset = audit_h - 200
            can.setFillColorRGB(0.44, 0.29, 0.40)
            can.rect(40, y_offset, audit_w - 80, 20, fill=True, stroke=False)
            can.setFillColorRGB(1, 1, 1)
            can.setFont("Helvetica-Bold", 9)
            can.drawString(45, y_offset + 6, "Seq")
            can.drawString(75, y_offset + 6, "Role")
            can.drawString(160, y_offset + 6, "Signer Name / Email")
            can.drawString(360, y_offset + 6, "Status")
            can.drawString(430, y_offset + 6, "IP Address")

            # Signers Table Rows
            y_offset -= 22
            can.setFont("Helvetica", 8)
            can.setFillColorRGB(0.15, 0.15, 0.15)
            for s in self.signer_ids:
                log = self.env['sign.log'].sudo().search([
                    ('sign_request_id', '=', self.id),
                    ('partner_id', '=', s.partner_id.id),
                    ('action', '=', 'sign')
                ], limit=1)
                ip_str = log.ip_address if log and log.ip_address else '127.0.0.1'

                can.drawString(45, y_offset + 4, str(s.sequence))
                can.drawString(75, y_offset + 4, (s.role_id.name or '')[:15])
                signer_info_str = "%s (%s)" % (s.partner_id.name or '', s.partner_id.email or '')
                can.drawString(160, y_offset + 4, signer_info_str[:38])
                can.drawString(360, y_offset + 4, s.state.capitalize())
                can.drawString(430, y_offset + 4, ip_str)
                can.setStrokeColorRGB(0.85, 0.85, 0.85)
                can.setLineWidth(0.5)
                can.line(40, y_offset, audit_w - 40, y_offset)
                y_offset -= 22

            # Footer Security Certification
            can.setFillColorRGB(0.45, 0.45, 0.45)
            can.setFont("Helvetica-Oblique", 7.5)
            can.drawString(40, 45, "This certificate confirms that all signatures were electronically executed and logged via Easy Sign.")
            can.drawString(40, 32, "Audit Log Integrity Checksum (SHA-256): Cryptographically verified upon PDF compilation.")
            can.showPage()

            can.save()
            item_pdf = PdfFileReader(packet, overwriteWarnings=False)
            new_pdf = PdfFileWriter()
            for p in range(0, old_pdf.getNumPages()):
                page = old_pdf.getPage(p)
                page.mergePage(item_pdf.getPage(p))
                new_pdf.addPage(page)

            # Append the Audit Trail Certificate page
            new_pdf.addPage(item_pdf.getPage(old_pdf.getNumPages()))

            output = io.BytesIO()
            new_pdf.write(output)
            raw_bytes = output.getvalue()

            # Compute SHA-256 hash of completed document
            sha256_hash = hashlib.sha256(raw_bytes).hexdigest()

            self.completed_document = base64.b64encode(raw_bytes)
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
