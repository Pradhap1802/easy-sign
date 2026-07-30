# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import uuid

class SignTemplateShare(models.TransientModel):
    _name = 'sign.template.share'
    _description = 'Share Signature Template'

    template_id = fields.Many2one('sign.template', string="Template", required=True, ondelete='cascade')
    share_url = fields.Char(string="Share Link", readonly=True)
    valid_until = fields.Date(string="Valid Until")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id') or self.env.context.get('default_template_id')
        if active_id:
            template = self.env['sign.template'].browse(active_id)
            if not template.share_token:
                template.sudo().write({'share_token': str(uuid.uuid4())})
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            share_url = "%s/sign/share/%d/%s" % (base_url, template.id, template.share_token)
            res.update({
                'template_id': template.id,
                'share_url': share_url,
                'valid_until': template.valid_until,
            })
        return res

    def action_update_validity(self):
        self.ensure_one()
        self.template_id.sudo().write({'valid_until': self.valid_until})
        return {'type': 'ir.actions.act_window_close'}
