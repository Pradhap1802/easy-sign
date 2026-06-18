# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class SignSendRequestWizard(models.TransientModel):
    _name = "sign.send.request.wizard"
    _description = "Sign Send Request Wizard"

    template_id = fields.Many2one('sign.template', string="Template", required=True, default=lambda self: self.env.context.get('active_id', None))
    reference = fields.Char(string="Document Name", default="New Signature Request")
    subject = fields.Char(string="Email Subject")



    def send_request(self):
        self.ensure_one()
        request_vals = {
            'template_id': self.template_id.id,
            'reference': self.reference,
            'subject': self.subject,
        }
        sign_request = self.env['sign.request'].create(request_vals)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sign Request'),
            'res_model': 'sign.request',
            'view_mode': 'form',
            'res_id': sign_request.id,
        }


from odoo.tools import get_lang

class SignRequestSendWizard(models.TransientModel):
    _name = "sign.request.send.wizard"
    _description = "Send Request Wizard"

    request_id = fields.Many2one('sign.request', string="Sign Request", required=True)
    partner_id = fields.Many2one('res.partner', string="Recipient", required=True)
    subject = fields.Char(string="Subject", required=True)

    def send_mail(self):
        self.ensure_one()
        base_url = self.request_id.get_base_url()
        lang = get_lang(self.env, self.partner_id.lang).code if self.partner_id.lang else 'en_US'
        link = "%s/sign/document/%s/%s" % (base_url, self.request_id.id, self.request_id.access_token)
        body = self.env['ir.qweb']._render('easy_sign.sign_template_mail', {
            'record': self.request_id,
            'recipient': self.partner_id,
            'link': link,
            'subject': self.subject,
        }, lang=lang, minimal_qcontext=True)
        self.request_id._message_send_mail(
            body,
            'mail.mail_notification_light',
            {'record_name': self.request_id.reference},
            {'model_description': _('Signature')},
            {'email_to': self.partner_id.email, 'subject': self.subject},
            force_send=True,
            lang=lang,
        )
        self.env['sign.log'].sudo().create({
            'sign_request_id': self.request_id.id,
            'partner_id': self.partner_id.id,
            'action': 'send',
        })

