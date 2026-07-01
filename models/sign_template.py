# -*- coding: utf-8 -*-
import base64
import io
import uuid
from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError
from odoo.tools import pdf
from odoo.tools.pdf import PdfFileReader


class SignTemplate(models.Model):
    _name = "sign.template"
    _description = "Signature Template"

    def _get_default_favorited_ids(self):
        return [(4, self.env.user.id)]

    name = fields.Char(string="Template Name", required=True)
    num_pages = fields.Integer('Number of pages', compute="_compute_num_pages", readonly=True, store=True)
    datas = fields.Binary(string="PDF Document", required=True, attachment=True)
    sign_item_ids = fields.One2many('sign.item', 'template_id', string="Signature Items", copy=True)
    sign_request_ids = fields.One2many('sign.request', 'template_id', string="Sign Requests")
    active = fields.Boolean(default=True, string="Active")
    favorited_ids = fields.Many2many('res.users', string="Favorited Users", relation="sign_template_favorited_users_rel", default=_get_default_favorited_ids)
    user_id = fields.Many2one('res.users', string="Responsible", default=lambda self: self.env.user)
    has_sign_requests = fields.Boolean(compute="_compute_has_sign_requests", compute_sudo=True, store=True)
    share_token = fields.Char(string="Share Link", copy=False)
    valid_until = fields.Date(string="Valid Until")
    # Temporary field for form view
    datas_fname = fields.Char(string="File Name")

    @api.depends('datas')
    def _compute_num_pages(self):
        for record in self:
            try:
                record.num_pages = self._get_pdf_number_of_pages(base64.b64decode(record.datas))
            except Exception:
                record.num_pages = 0

    @api.depends('sign_request_ids')
    def _compute_has_sign_requests(self):
        for template in self:
            template.has_sign_requests = bool(template.with_context(active_test=False).sign_request_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'datas' in vals:
                self._check_pdf_data_validity(vals['datas'])
        return super().create(vals_list)

    def write(self, vals):
        if 'datas' in vals:
            self._check_pdf_data_validity(vals['datas'])
        return super().write(vals)

    def go_to_custom_template(self):
        self.ensure_one()
        return {
            'name': "Template \"%(name)s\"" % {'name': self.name},
            'type': 'ir.actions.act_url',
            'url': '/sign/template/%d/edit' % self.id,
            'target': 'self',
        }

    def _get_pdf_number_of_pages(self, pdf_data):
        file_pdf = PdfFileReader(io.BytesIO(pdf_data), strict=False, overwriteWarnings=False)
        return len(file_pdf.pages)

    def _check_pdf_data_validity(self, datas):
        try:
            self._get_pdf_number_of_pages(base64.b64decode(datas))
        except Exception as e:
            raise UserError(_("One uploaded file cannot be read. Is it a valid PDF?"))


class SignItem(models.Model):
    _name = "sign.item"
    _description = "Fields to be signed on Document"
    _order = "page asc, posY asc, posX asc"
    _rec_name = 'template_id'

    template_id = fields.Many2one('sign.template', string="Document Template", required=True, ondelete='cascade')
    type_id = fields.Many2one('sign.item.type', string="Type", required=True, ondelete='restrict')
    required = fields.Boolean(default=True)
    responsible_id = fields.Many2one("sign.item.role", string="Responsible", ondelete="restrict")
    name = fields.Char(string="Field Name")
    page = fields.Integer(string="Document Page", required=True, default=1)
    posX = fields.Float(digits=(4, 3), string="Position X", required=True)
    posY = fields.Float(digits=(4, 3), string="Position Y", required=True)
    width = fields.Float(digits=(4, 3), required=True)
    height = fields.Float(digits=(4, 3), required=True)
    alignment = fields.Char(default="center", required=True)
    placeholder = fields.Char(string="Placeholder", translate=True)


class SignItemType(models.Model):
    _name = "sign.item.type"
    _description = "Signature Item Type"

    name = fields.Char(string="Field Name", required=True, translate=True)
    icon = fields.Char()
    item_type = fields.Selection([
        ('signature', "Signature"),
        ('initial', "Initial"),
        ('text', "Text"),
        ('textarea', "Multiline Text"),
        ('checkbox', "Checkbox"),
        ('radio', "Radio"),
    ], required=True, string='Type', default='text')
    opt_model_id = fields.Many2one('ir.model', string="Linked to", ondelete='cascade')
    opt_field_id = fields.Many2one('ir.model.fields', string="Linked field", ondelete='cascade', domain="[('model_id', '=', opt_model_id)]")
    auto_update = fields.Boolean(string="Update Field", default=False)
    is_mandatory = fields.Boolean(string="Mandatory", default=False)
    tip = fields.Char(required=True, default="fill in", help="Hint displayed in the signing hint", translate=True)
    placeholder = fields.Char(translate=True)
    default_width = fields.Float(string="Default Width", digits=(4, 3), required=True, default=0.150)
    default_height = fields.Float(string="Default Height", digits=(4, 3), required=True, default=0.015)


class SignItemRole(models.Model):
    _name = "sign.item.role"
    _description = "Signature Item Party"
    _rec_name = "name"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    color = fields.Integer()
    default = fields.Boolean(required=True, default=False)
    sequence = fields.Integer(string="Default order", default=10)
