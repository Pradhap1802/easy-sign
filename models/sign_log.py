# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SignLog(models.Model):
    _name = "sign.log"
    _description = "Sign Log"

    sign_request_id = fields.Many2one('sign.request', string='Sign Request', required=True, ondelete='cascade')
    sign_request_item_id = fields.Many2one('sign.request.item', string='Sign Request Item', ondelete='cascade')
    action = fields.Selection([
        ('create', 'Create'),
        ('send', 'Send'),
        ('view', 'View'),
        ('sign', 'Sign'),
        ('cancel', 'Cancel'),
        ('decline', 'Decline'),
    ], string='Action', required=True)
    partner_id = fields.Many2one('res.partner', string='Partner', compute='_compute_partner_id', store=True)
    user_id = fields.Many2one('res.users', string='User')
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)
    ip_address = fields.Char(string='IP Address')

    @api.depends('sign_request_item_id.partner_id')
    def _compute_partner_id(self):
        for log in self:
            log.partner_id = log.sign_request_item_id.partner_id
