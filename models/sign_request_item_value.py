# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SignRequestItemValue(models.Model):
    _name = "sign.request.item.value"
    _description = "Sign Request Item Value"

    sign_request_id = fields.Many2one('sign.request', string='Sign Request', required=True, ondelete='cascade')
    sign_request_item_id = fields.Many2one('sign.request.item', string='Sign Request Item', required=True, ondelete='cascade')
    sign_item_id = fields.Many2one('sign.item', string='Sign Item', required=True, ondelete='cascade')
    value = fields.Text(string='Value')
    frame_value = fields.Text(string='Frame Value')
