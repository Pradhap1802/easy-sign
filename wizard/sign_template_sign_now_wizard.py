# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import uuid

class SignTemplateSignNowWizard(models.TransientModel):
    _name = 'sign.template.sign.now.wizard'
    _description = 'Sign Now Wizard'

    template_id = fields.Many2one('sign.template', string="Template", required=True, ondelete='cascade')
    subject = fields.Char(string="Subject", required=True)
    cc_ids = fields.Many2many('res.partner', string="CC")
    message = fields.Text(string="Message")
    hide_certificate = fields.Boolean(string="Hide certificate key on pages")
    signer_line_ids = fields.One2many('sign.template.sign.now.signer', 'wizard_id', string="Signers")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id') or self.env.context.get('default_template_id')
        if active_id:
            template = self.env['sign.template'].browse(active_id)
            res['template_id'] = template.id
            res['subject'] = _("Signature Request - %s") % template.name
            
            # Load template signers
            signer_lines = []
            if template.template_signer_ids:
                for idx, s in enumerate(template.template_signer_ids, start=1):
                    # Default the first signer to the current user's partner
                    partner = s.partner_id if s.partner_id else (self.env.user.partner_id if idx == 1 else False)
                    signer_lines.append((0, 0, {
                        'role_id': s.role_id.id,
                        'partner_id': partner.id if partner else False,
                    }))
            else:
                roles = template.sign_item_ids.mapped('responsible_id')
                if not roles and template.sign_item_ids:
                    default_role = self.env['sign.item.role'].search([('default', '=', True)], limit=1)
                    if default_role:
                        roles = default_role
                for idx, role in enumerate(roles, start=1):
                    partner = self.env.user.partner_id if idx == 1 else False
                    signer_lines.append((0, 0, {
                        'role_id': role.id,
                        'partner_id': partner.id if partner else False,
                    }))
            res['signer_line_ids'] = signer_lines
        return res

    def action_sign_now(self):
        self.ensure_one()
        request_vals = {
            'template_id': self.template_id.id,
            'reference': self.template_id.name,
            'subject': self.subject,
        }
        sign_request = self.env['sign.request'].create(request_vals)
        
        first_signer = False
        for sequence, line in enumerate(self.signer_line_ids, start=1):
            signer = self.env['sign.request.signer'].create({
                'sign_request_id': sign_request.id,
                'role_id': line.role_id.id,
                'partner_id': line.partner_id.id,
                'sequence': sequence,
                'state': 'draft',
                'access_token': str(uuid.uuid4())
            })
            if sequence == 1:
                first_signer = signer
        
        sign_request.action_send_next_signature_request()
        
        if first_signer:
            return {
                'type': 'ir.actions.act_url',
                'url': '/sign/document/%d/%s' % (sign_request.id, first_signer.access_token),
                'target': 'self',
            }
        return {'type': 'ir.actions.act_window_close'}


class SignTemplateSignNowSigner(models.TransientModel):
    _name = 'sign.template.sign.now.signer'
    _description = 'Sign Now Signer Line'

    wizard_id = fields.Many2one('sign.template.sign.now.wizard', string="Wizard", required=True, ondelete='cascade')
    role_id = fields.Many2one('sign.item.role', string="Role", required=True)
    partner_id = fields.Many2one('res.partner', string="Partner", required=True)
