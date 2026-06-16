from odoo import fields, models


class SignRequestFieldValue(models.Model):
    """Stores the value a signer filled in for a template field."""

    _name = "sign.request.field.value"
    _description = "Sign Request Field Value"
    _order = "request_item_id, template_field_id"

    request_id = fields.Many2one(
        "sign.request", required=True, ondelete="cascade", index=True
    )
    request_item_id = fields.Many2one(
        "sign.request.item", required=True, ondelete="cascade", index=True
    )
    template_field_id = fields.Many2one(
        "sign.template.field", required=True, ondelete="cascade", index=True
    )
    # field_type mirrors template_field_id.field_type for easy filtering
    field_type = fields.Selection(
        related="template_field_id.field_type", store=True, readonly=True
    )
    page = fields.Integer(related="template_field_id.page", store=True, readonly=True)
    pos_x = fields.Float(related="template_field_id.pos_x", store=True, readonly=True)
    pos_y = fields.Float(related="template_field_id.pos_y", store=True, readonly=True)
    width = fields.Float(related="template_field_id.width", store=True, readonly=True)
    height = fields.Float(related="template_field_id.height", store=True, readonly=True)
    signer_index = fields.Integer(
        related="template_field_id.signer_index", store=True, readonly=True
    )
    # The actual value provided by the signer
    value = fields.Text(string="Value")  # text, name, date, email, checkbox
    signature_value = fields.Binary(
        string="Signature Image", attachment=True
    )  # signature/initial
