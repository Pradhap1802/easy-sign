# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class SignSendRequestWizard(models.TransientModel):
    _name = "sign.send.request.wizard"
    _description = "Sign Send Request Wizard"

    template_id = fields.Many2one('sign.template', string="Template", required=True, default=lambda self: self.env.context.get('active_id', None))
    reference = fields.Char(string="Document Name", default="New Signature Request")
    partner_ids = fields.Many2many('res.partner', string="Recipients")
    subject = fields.Char(string="Email Subject")



    def send_request(self):
        self.ensure_one()
        request_vals = {
            'template_id': self.template_id.id,
            'reference': self.reference,
            'subject': self.subject,
            'request_item_ids': [(0, 0, {
                'partner_id': partner.id,
                'role_id': self.env.ref('easy_sign.sign_item_role_default').id,
            }) for partner in self.partner_ids]
        }
        sign_request = self.env['sign.request'].create(request_vals)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sign Request'),
            'res_model': 'sign.request',
            'view_mode': 'form',
            'res_id': sign_request.id,
        }
