import base64
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SignTemplate(models.Model):
    _name = "sign.template"
    _description = "Sign Document Template"
    _order = "id desc"
    _rec_name = "name"

    name = fields.Char(string="Template Name", required=True)
    pdf_document = fields.Binary(
        string="PDF Document", required=True, attachment=True
    )
    pdf_document_name = fields.Char(string="File Name")
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)
    field_ids = fields.One2many(
        "sign.template.field", "template_id", string="Fields"
    )
    field_count = fields.Integer(
        compute="_compute_field_count", string="Fields", store=True
    )
    signer_count = fields.Integer(
        string="Required Signers", default=1
    )
    request_ids = fields.One2many(
        "sign.request", "template_id", string="Requests"
    )
    request_count = fields.Integer(
        compute="_compute_request_count", string="Requests Used"
    )

    @api.depends("field_ids")
    def _compute_field_count(self):
        for rec in self:
            rec.field_count = len(rec.field_ids)



    def _compute_request_count(self):
        for rec in self:
            rec.request_count = len(rec.request_ids)

    def action_edit_template(self):
        self.ensure_one()
        base_url = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"{base_url}/sign/template/{self.id}/edit",
            "target": "self",
        }

    def action_use_template(self):
        self.ensure_one()
        if not self.pdf_document:
            raise UserError("Please upload a PDF document first.")
        return {
            "type": "ir.actions.act_window",
            "name": f"Send: {self.name}",
            "res_model": "sign.template.send.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_template_id": self.id},
        }

    def action_view_requests(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Requests",
            "res_model": "sign.request",
            "view_mode": "list,form",
            "domain": [("template_id", "=", self.id)],
        }
