import secrets
from odoo import api, fields, models
from odoo.exceptions import UserError


class SignRequestItem(models.Model):
    _name = "sign.request.item"
    _description = "Signature Request Item (Signer)"
    _order = "id asc"
    _rec_name = "signer_name"

    request_id = fields.Many2one(
        "sign.request",
        string="Signature Request",
        ondelete="cascade",
        required=True,
        index=True,
    )
    signer_name = fields.Char(string="Signer Name", required=True)
    signer_email = fields.Char(string="Signer Email", required=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        help="Optional: link to an existing Odoo contact",
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("sent", "Invitation Sent"),
            ("viewed", "Viewed"),
            ("signed", "Signed"),
            ("declined", "Declined"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="pending",
        tracking=True,
        readonly=True,
    )
    access_token = fields.Char(
        string="Access Token",
        copy=False,
        readonly=True,
        index=True,
    )
    signature = fields.Binary(
        string="Signature Image",
        attachment=True,
        copy=False,
    )
    signed_date = fields.Datetime(
        string="Signed On",
        readonly=True,
        copy=False,
    )
    declined_reason = fields.Text(
        string="Decline Reason",
        copy=False,
    )
    ip_address = fields.Char(
        string="IP Address",
        copy=False,
        readonly=True,
    )
    sign_url = fields.Char(
        string="Signing URL",
        compute="_compute_sign_url",
        store=False,
    )

    @api.depends("access_token")
    def _compute_sign_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for item in self:
            if item.access_token:
                item.sign_url = f"{base_url}/sign/view/{item.access_token}"
            else:
                item.sign_url = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("access_token"):
                vals["access_token"] = secrets.token_urlsafe(32)
        return super().create(vals_list)

    def action_sign(self, signature_b64, ip_address=None):
        self.ensure_one()
        if self.state in ("signed", "declined", "cancelled"):
            raise UserError(
                f"This signing request is already in state: {self.state}"
            )
        self.write(
            {
                "state": "signed",
                "signature": signature_b64,
                "signed_date": fields.Datetime.now(),
                "ip_address": ip_address,
            }
        )
        self.env["sign.log"].sudo().create(
            {
                "request_id": self.request_id.id,
                "request_item_id": self.id,
                "action": "signed",
                "ip_address": ip_address,
            }
        )
        self.request_id.sudo()._check_all_signed()
        return True

    def action_decline(self, reason=None, ip_address=None):
        self.ensure_one()
        if self.state in ("signed", "declined", "cancelled"):
            raise UserError(
                f"This signing request is already in state: {self.state}"
            )
        self.write(
            {
                "state": "declined",
                "declined_reason": reason,
                "ip_address": ip_address,
            }
        )
        self.env["sign.log"].sudo().create(
            {
                "request_id": self.request_id.id,
                "request_item_id": self.id,
                "action": "declined",
                "ip_address": ip_address,
                "notes": reason,
            }
        )
        self.request_id.sudo()._notify_declined(self)
        return True
