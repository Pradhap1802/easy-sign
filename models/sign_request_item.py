# -*- coding: utf-8 -*-
import uuid
from datetime import datetime
from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError
from odoo.tools import get_lang


class SignRequestItem(models.Model):
    _name = "sign.request.item"
    _description = "Sign Request Item"

    def _default_access_token(self):
        return str(uuid.uuid4())

    sign_request_id = fields.Many2one('sign.request', string="Sign Request", required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string="Signer", required=True)
    role_id = fields.Many2one('sign.item.role', string="Role", ondelete='restrict')
    access_token = fields.Char('Security Token', required=True, default=_default_access_token, readonly=True, copy=False)
    state = fields.Selection([
        ('sent', 'Sent'),
        ('viewed', 'Viewed'),
        ('completed', 'Signed'),
        ('canceled', 'Cancelled'),
    ], default='sent', string='State')
    signing_date = fields.Datetime('Signed on')
    signature = fields.Binary(string='Signature')
    is_mail_sent = fields.Boolean(default=False, string="Mail sent")
    signer_email = fields.Char(string="Signer email", related="partner_id.email")

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)

    def send_signature_accesses(self):
        base_url = self.get_base_url()
        for item in self:
            item.write({'is_mail_sent': True})
            partner = item.partner_id
            lang = get_lang(self.env, partner.lang).code
            subject = _("Signature Request: %s", item.sign_request_id.reference)
            link = "%s/sign/document/%s/%s" % (base_url, item.sign_request_id.id, item.access_token)
            body = self.env['ir.qweb']._render('easy_sign.sign_template_mail', {
                'record': item.sign_request_id,
                'recipient': partner,
                'link': link,
                'subject': subject,
            }, lang=lang, minimal_qcontext=True)
            item.sign_request_id._message_send_mail(
                body,
                'mail.mail_notification_light',
                {'record_name': item.sign_request_id.reference},
                {'model_description': _('Signature')},
                {'email_to': partner.email, 'subject': subject},
                force_send=True,
                lang=lang,
            )
            self.env['sign.log'].sudo().create({
                'sign_request_id': item.sign_request_id.id,
                'sign_request_item_id': item.id,
                'action': 'send',
            })

    def _sign(self, signature_values):
        self.ensure_one()
        if self.state != 'sent' and self.state != 'viewed':
            raise UserError(_("This signature has already been processed or cancelled"))
        self.write({
            'state': 'completed',
            'signing_date': fields.Datetime.now(),
        })
        SignRequestItemValue = self.env['sign.request.item.value']
        for sign_item_id, value in signature_values.items():
            if isinstance(value, dict):
                frame_value = value.get('frame')
                value = value.get('value')
            else:
                frame_value = None
            SignRequestItemValue.sudo().create({
                'sign_request_id': self.sign_request_id.id,
                'sign_request_item_id': self.id,
                'sign_item_id': int(sign_item_id),
                'value': value,
                'frame_value': frame_value,
            })
        self.env['sign.log'].sudo().create({
            'sign_request_id': self.sign_request_id.id,
            'sign_request_item_id': self.id,
            'action': 'sign',
        })
        if all(item.state == 'completed' for item in self.sign_request_id.request_item_ids):
            self.sign_request_id._sign()

    def _refuse(self, refusal_reason):
        self.ensure_one()
        self.write({'state': 'canceled'})
        self.sign_request_id._refuse(self.partner_id, refusal_reason)

    def _cancel(self):
        self.write({'state': 'canceled'})
