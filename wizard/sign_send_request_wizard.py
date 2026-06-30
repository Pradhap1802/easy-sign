# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.tools import get_lang

class SignSendRequestWizard(models.TransientModel):
    _name = "sign.send.request.wizard"
    _description = "Sign Send Request Wizard"

    template_id = fields.Many2one('sign.template', string="Template", required=True, default=lambda self: self.env.context.get('active_id', None))
    reference = fields.Char(string="Document Name", default="New Signature Request")
    subject = fields.Char(string="Email Subject")
    signer_ids = fields.One2many('sign.send.request.signer', 'wizard_id', string="Signers")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id and self.env.context.get('active_model') == 'sign.template':
            template = self.env['sign.template'].browse(active_id)
            roles = template.sign_item_ids.mapped('responsible_id')
            if not roles and template.sign_item_ids:
                default_role = self.env['sign.item.role'].search([('default', '=', True)], limit=1)
                if default_role:
                    roles = default_role
            
            signer_vals = []
            for role in roles:
                signer_vals.append((0, 0, {
                    'role_id': role.id,
                }))
            res['signer_ids'] = signer_vals
        return res

    def send_request(self):
        self.ensure_one()
        request_vals = {
            'template_id': self.template_id.id,
            'reference': self.reference,
            'subject': self.subject,
        }
        sign_request = self.env['sign.request'].create(request_vals)
        
        signers = []
        for sequence, signer in enumerate(self.signer_ids, start=1):
            signers.append({
                'sign_request_id': sign_request.id,
                'role_id': signer.role_id.id,
                'partner_id': signer.partner_id.id,
                'sequence': sequence,
                'state': 'draft',
            })
        self.env['sign.request.signer'].create(signers)
        
        # Trigger the first signature request email
        sign_request.action_send_next_signature_request()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sign Request'),
            'res_model': 'sign.request',
            'view_mode': 'form',
            'res_id': sign_request.id,
        }


class SignSendRequestSigner(models.TransientModel):
    _name = "sign.send.request.signer"
    _description = "Sign Send Request Signer"

    wizard_id = fields.Many2one('sign.send.request.wizard', string="Wizard", required=True, ondelete='cascade')
    role_id = fields.Many2one('sign.item.role', string="Role", required=True)
    partner_id = fields.Many2one('res.partner', string="Recipient", required=True)


class SignRequestSendWizard(models.TransientModel):
    _name = "sign.request.send.wizard"
    _description = "Send Request Wizard"

    request_id = fields.Many2one('sign.request', string="Sign Request", required=True)
    partner_id = fields.Many2one('res.partner', string="Recipient", required=True)
    subject = fields.Char(string="Subject", required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request_id = self.env.context.get('default_request_id') or self.env.context.get('active_id')
        if request_id:
            request_rec = self.env['sign.request'].browse(request_id)
            active_signer = request_rec.signer_ids.filtered(lambda s: s.state == 'sent')
            if not active_signer:
                active_signer = request_rec.signer_ids.filtered(lambda s: s.state == 'draft')
            if active_signer:
                res['partner_id'] = active_signer[0].partner_id.id
        return res

    def send_mail(self):
        self.ensure_one()
        # Find if there is a signer record for this partner
        signer = self.request_id.signer_ids.filtered(lambda s: s.partner_id.id == self.partner_id.id)
        if signer:
            # Send using specific signer's secure token
            self.request_id._send_signer_email(signer[0])
            if signer[0].state == 'draft':
                signer[0].write({'state': 'sent'})
        else:
            # Fallback for requests without mapped signers
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
