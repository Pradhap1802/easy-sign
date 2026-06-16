from odoo import api, fields, models
from odoo.exceptions import UserError


class SignTemplateSendWizardSigner(models.TransientModel):
    _name = "sign.template.send.wizard.signer"
    _description = "Signer Line in Send Wizard"
    _order = "signer_index"

    wizard_id = fields.Many2one(
        "sign.template.send.wizard", ondelete="cascade", required=True
    )
    signer_index = fields.Integer(string="Signer #", default=1)
    signer_name = fields.Char(string="Name", required=True)
    signer_email = fields.Char(string="Email", required=True)


class SignTemplateSendWizard(models.TransientModel):
    _name = "sign.template.send.wizard"
    _description = "Send Template Wizard"

    template_id = fields.Many2one(
        "sign.template", string="Template", required=True, readonly=True
    )
    signer_line_ids = fields.One2many(
        "sign.template.send.wizard.signer", "wizard_id", string="Signers"
    )
    expiry_date = fields.Date(string="Expiry Date")
    message = fields.Html(
        string="Invitation Message",
        default="<p>Hello,</p><p>Please review and sign the attached document at your earliest convenience.</p><p>Thank you.</p>",
    )
    required_signer_count = fields.Integer(
        compute="_compute_required_signer_count", string="Required Signers"
    )

    @api.depends("template_id.field_ids.signer_index")
    def _compute_required_signer_count(self):
        for rec in self:
            if rec.template_id and rec.template_id.field_ids:
                rec.required_signer_count = max(
                    rec.template_id.field_ids.mapped("signer_index") or [1]
                )
            else:
                rec.required_signer_count = 1

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        template_id = self.env.context.get("default_template_id")
        if template_id:
            template = self.env["sign.template"].browse(template_id)
            if template.exists():
                indices = sorted(
                    set(template.field_ids.mapped("signer_index") or [1])
                )
                lines = []
                for idx in indices:
                    lines.append(
                        (
                            0,
                            0,
                            {
                                "signer_index": idx,
                                "signer_name": f"Signer {idx}",
                                "signer_email": "",
                            },
                        )
                    )
                res["signer_line_ids"] = lines
        return res

    def action_send(self):
        self.ensure_one()
        template = self.template_id

        if not template.pdf_document:
            raise UserError("The template has no PDF document.")

        # Validate all signer lines have name and email
        for line in self.signer_line_ids:
            if not line.signer_name or not line.signer_email:
                raise UserError(
                    f"Please provide name and email for Signer #{line.signer_index}."
                )

        # Build request items
        item_vals = []
        for line in self.signer_line_ids.sorted("signer_index"):
            item_vals.append(
                (
                    0,
                    0,
                    {
                        "signer_name": line.signer_name,
                        "signer_email": line.signer_email,
                        "signer_index": line.signer_index,
                    },
                )
            )

        request = self.env["sign.request"].create(
            {
                "template_id": template.id,
                "document": template.pdf_document,
                "document_name": template.pdf_document_name or f"{template.name}.pdf",
                "subject": f"Please sign: {template.name}",
                "message": self.message or "",
                "expiry_date": self.expiry_date,
                "request_item_ids": item_vals,
            }
        )

        # Send invitations
        request.action_send()

        return {
            "type": "ir.actions.act_window",
            "name": "Signature Request",
            "res_model": "sign.request",
            "res_id": request.id,
            "view_mode": "form",
            "target": "current",
        }
