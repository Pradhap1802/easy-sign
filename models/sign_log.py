# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SignLog(models.Model):
    _name = "sign.log"
    _description = "Sign Log"

    sign_request_id = fields.Many2one('sign.request', string='Sign Request', required=True, ondelete='cascade')
    action = fields.Selection([
        ('create', 'Create'),
        ('send', 'Send'),
        ('view', 'View'),
        ('sign', 'Sign'),
        ('cancel', 'Cancel'),
        ('decline', 'Decline'),
        ('expire', 'Expire'),
        ('delegate', 'Delegate'),
    ], string='Action', required=True)
    partner_id = fields.Many2one('res.partner', string='Partner', default=lambda self: self.env.user.partner_id)
    user_id = fields.Many2one('res.users', string='User')
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)
    ip_address = fields.Char(string='IP Address')
