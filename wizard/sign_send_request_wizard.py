# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.tools import get_lang

class SignSendRequestWizard(models.TransientModel):
    _name = "sign.send.request.wizard"
    _description = "Sign Send Request Wizard"

    template_id = fields.Many2one('sign.template', string="Template", required=True, default=lambda self: self.env.context.get('active_id', None))
    reference = fields.Char(string="Document Name", default="New Signature Request")
    subject = fields.Char(string="Email Subject")
    cc_emails = fields.Char(string="CC")
    signer_ids = fields.One2many('sign.send.request.signer', 'wizard_id', string="Signers")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id and self.env.context.get('active_model') == 'sign.template':
            template = self.env['sign.template'].browse(active_id)
            if 'cc_emails' in fields_list and not res.get('cc_emails'):
                res['cc_emails'] = template.cc_emails
            
            signer_vals = []
            if template.template_signer_ids:
                for s in template.template_signer_ids:
                    signer_vals.append((0, 0, {
                        'role_id': s.role_id.id,
                        'partner_id': s.partner_id.id if s.partner_id else False,
                        'email': s.email or (s.partner_id.email if s.partner_id else ''),
                    }))
            else:
                roles = template.sign_item_ids.mapped('responsible_id')
                if not roles and template.sign_item_ids:
                    default_role = self.env['sign.item.role'].search([('default', '=', True)], limit=1)
                    if default_role:
                        roles = default_role
                
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
            'cc_emails': self.cc_emails,
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
    partner_id = fields.Many2one('res.partner', string="Full Name", required=True)
    email = fields.Char(string="Email")

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.email = self.partner_id.email


class SignRequestSendWizard(models.TransientModel):
    _name = "sign.request.send.wizard"
    _description = "Send Request Wizard"

    request_id = fields.Many2one('sign.request', string="Sign Request", required=True)
    partner_id = fields.Many2one('res.partner', string="Recipient")
    subject = fields.Char(string="Subject", required=True)
    cc_emails = fields.Char(string="CC")
    signer_ids = fields.One2many('sign.request.send.wizard.signer', 'wizard_id', string="Recipients")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request_id = self.env.context.get('default_request_id') or self.env.context.get('active_id')
        if request_id:
            request_rec = self.env['sign.request'].browse(request_id)
            if 'subject' in fields_list and not res.get('subject'):
                res['subject'] = request_rec.subject or (_('Signature Request: %s') % request_rec.reference)
            if 'cc_emails' in fields_list and not res.get('cc_emails'):
                res['cc_emails'] = request_rec.cc_emails

            signer_vals = []
            if request_rec.signer_ids:
                for signer in request_rec.signer_ids:
                    signer_vals.append((0, 0, {
                        'signer_id': signer.id,
                        'role_id': signer.role_id.id if signer.role_id else False,
                        'partner_id': signer.partner_id.id if signer.partner_id else False,
                        'email': signer.partner_id.email if signer.partner_id else '',
                        'state': signer.state,
                    }))
                if signer_vals and 'partner_id' in fields_list:
                    res['partner_id'] = request_rec.signer_ids[0].partner_id.id
            res['signer_ids'] = signer_vals
        return res

    def send_mail(self):
        self.ensure_one()
        if self.subject and self.request_id.subject != self.subject:
            self.request_id.write({'subject': self.subject})
        if self.cc_emails and self.request_id.cc_emails != self.cc_emails:
            self.request_id.write({'cc_emails': self.cc_emails})

        if self.signer_ids:
            for w_signer in self.signer_ids:
                if w_signer.signer_id and w_signer.partner_id:
                    if w_signer.signer_id.partner_id != w_signer.partner_id:
                        w_signer.signer_id.write({'partner_id': w_signer.partner_id.id})
            self.request_id.action_send_next_signature_request()
        elif self.partner_id:
            signer = self.request_id.signer_ids.filtered(lambda s: s.partner_id.id == self.partner_id.id)
            if signer:
                if signer[0].state == 'draft':
                    signer[0].write({'state': 'sent'})
                self.request_id._send_signer_email(signer[0])
            else:
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



class SignRequestSendWizardSigner(models.TransientModel):
    _name = "sign.request.send.wizard.signer"
    _description = "Send Request Wizard Signer Line"

    wizard_id = fields.Many2one('sign.request.send.wizard', string="Wizard", required=True, ondelete='cascade')
    signer_id = fields.Many2one('sign.request.signer', string="Signer")
    role_id = fields.Many2one('sign.item.role', string="Role")
    partner_id = fields.Many2one('res.partner', string="Recipient", required=True)
    email = fields.Char(string="Email")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('signed', 'Signed'),
    ], string="Status")

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.email = self.partner_id.email

