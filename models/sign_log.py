from odoo import api, fields, models


class SignLog(models.Model):
    _name = "sign.log"
    _description = "Signature Audit Log"
    _order = "date desc"
    _rec_name = "action"

    request_id = fields.Many2one(
        "sign.request",
        string="Signature Request",
        ondelete="cascade",
        required=True,
        index=True,
    )
    request_item_id = fields.Many2one(
        "sign.request.item",
        string="Signer",
        ondelete="cascade",
    )
    action = fields.Selection(
        [
            ("sent", "Invitation Sent"),
            ("viewed", "Document Viewed"),
            ("signed", "Document Signed"),
            ("declined", "Document Declined"),
            ("cancelled", "Request Cancelled"),
        ],
        string="Action",
        required=True,
    )
    ip_address = fields.Char(string="IP Address")
    signer_name = fields.Char(
        string="Signer Name",
        related="request_item_id.signer_name",
        store=True,
    )
    signer_email = fields.Char(
        string="Signer Email",
        related="request_item_id.signer_email",
        store=True,
    )
    date = fields.Datetime(
        string="Date & Time",
        default=fields.Datetime.now,
        readonly=True,
    )
    notes = fields.Text(string="Notes")
