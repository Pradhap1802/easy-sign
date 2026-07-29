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
        
        if not self.signer_ids:
            from odoo.exceptions import UserError
            raise UserError(_("Please add at least one signer before sending the request."))

        signer_vals = []
        for sequence, signer in enumerate(self.signer_ids, start=1):
            partner_id = signer.partner_id.id
            if not partner_id and signer.email:
                partner = self.env['res.partner'].search([('email', '=', signer.email)], limit=1)
                if not partner:
                    partner = self.env['res.partner'].create({
                        'name': signer.name or signer.email,
                        'email': signer.email,
                    })
                partner_id = partner.id

            if not partner_id:
                from odoo.exceptions import UserError
                raise UserError(_("Please select a contact or enter a valid email for role '%s'.") % (signer.role_id.name or ''))

            signer_vals.append((0, 0, {
                'role_id': signer.role_id.id,
                'partner_id': partner_id,
                'sequence': sequence,
                'state': 'draft',
            }))

        request_vals = {
            'template_id': self.template_id.id,
            'reference': self.reference,
            'subject': self.subject,
            'cc_emails': self.cc_emails,
            'signer_ids': signer_vals,
        }
        sign_request = self.env['sign.request'].create(request_vals)
        self.env.flush_all()
        
        # Trigger the first signature request email
        sign_request.action_send_next_signature_request()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Sign Request'),
            'res_model': 'sign.request',
            'view_mode': 'form',
            'res_id': sign_request.id,
            'target': 'current',
        }


class SignSendRequestSigner(models.TransientModel):
    _name = "sign.send.request.signer"
    _description = "Sign Send Request Signer"

    wizard_id = fields.Many2one('sign.send.request.wizard', string="Wizard", required=True, ondelete='cascade')
    role_id = fields.Many2one('sign.item.role', string="Role", required=True)
    partner_id = fields.Many2one('res.partner', string="Contact")
    name = fields.Char(string="Name")
    email = fields.Char(string="Email")

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.name = self.partner_id.name
            self.email = self.partner_id.email

