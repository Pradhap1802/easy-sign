from odoo import fields, models

FIELD_TYPES = [
    ("signature", "Signature"),
    ("initial", "Initial"),
    ("name", "Full Name"),
    ("date", "Date"),
    ("email", "Email"),
    ("text", "Text"),
    ("checkbox", "Checkbox"),
]

FIELD_TYPE_ICONS = {
    "signature": "✍️",
    "initial": "🅐",
    "name": "👤",
    "date": "📅",
    "email": "✉️",
    "text": "Ⅰ",
    "checkbox": "☐",
}


class SignTemplateField(models.Model):
    _name = "sign.template.field"
    _description = "Sign Template Field Placement"
    _order = "page asc, pos_y asc, pos_x asc"

    template_id = fields.Many2one(
        "sign.template", required=True, ondelete="cascade", index=True
    )
    field_type = fields.Selection(
        FIELD_TYPES, string="Field Type", required=True, default="signature"
    )
    page = fields.Integer(string="Page", default=1, required=True)
    # Position and size as percentage of page dimensions (0-100)
    pos_x = fields.Float(string="Position X (%)", default=10.0)
    pos_y = fields.Float(string="Position Y (%)", default=10.0)
    width = fields.Float(string="Width (%)", default=20.0)
    height = fields.Float(string="Height (%)", default=8.0)
    required = fields.Boolean(string="Required", default=True)
    placeholder = fields.Char(string="Placeholder / Label")
    # Which signer fills this field (1-based index)
    signer_index = fields.Integer(
        string="Assigned to Signer #",
        default=1,
        help="1 = first signer, 2 = second signer, etc.",
    )

    def get_label(self):
        """Return human-readable label for this field."""
        self.ensure_one()
        type_label = dict(FIELD_TYPES).get(self.field_type, self.field_type)
        return self.placeholder or f"{type_label} (Signer {self.signer_index})"
