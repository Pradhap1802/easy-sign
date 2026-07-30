# -*- coding: utf-8 -*-
from odoo import fields, models


class SignTag(models.Model):
    _name = 'sign.tag'
    _description = 'Signature Tag'
    _order = 'name'

    name = fields.Char(string="Tag Name", required=True, translate=True)
    color = fields.Integer(string="Color Index", default=0)

    _sql_constraints = [
        ('name_uniq', 'UNIQUE(name)', 'Tag name must be unique.')
    ]
