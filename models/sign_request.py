import io
import base64
import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SignRequest(models.Model):
    _name = "sign.request"
    _description = "Electronic Signature Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _rec_name = "name"

    name = fields.Char(
        string="Reference",
        readonly=True,
        copy=False,
        default="New",
    )
    document = fields.Binary(
        string="Document (PDF)",
        required=True,
        attachment=True,
    )
    document_name = fields.Char(string="File Name")
    subject = fields.Char(
        string="Email Subject",
        required=True,
        default="Please sign: ",
    )
    message = fields.Html(
        string="Invitation Message",
        default="""<p>Hello,</p>
<p>You have been requested to sign a document. Please click the button below to review and sign it.</p>
<p>Thank you for your prompt attention to this matter.</p>""",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("sent", "Sent"),
            ("signed", "Fully Signed"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        tracking=True,
        readonly=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Requested By",
        default=lambda self: self.env.user,
        tracking=True,
    )
    expiry_date = fields.Date(
        string="Expiry Date",
        tracking=True,
        help="The signing link will stop working after this date.",
    )
    request_item_ids = fields.One2many(
        "sign.request.item",
        "request_id",
        string="Signers",
    )
    log_ids = fields.One2many(
        "sign.log",
        "request_id",
        string="Audit Log",
    )
    signed_document = fields.Binary(
        string="Signed Document",
        attachment=True,
        copy=False,
        readonly=True,
    )
    signed_document_name = fields.Char(
        string="Signed Document Name",
        copy=False,
        readonly=True,
    )
    signers_count = fields.Integer(
        string="Total Signers",
        compute="_compute_signing_progress",
        store=True,
    )
    signed_count = fields.Integer(
        string="Signed",
        compute="_compute_signing_progress",
        store=True,
    )
    all_signed = fields.Boolean(
        string="All Signed",
        compute="_compute_signing_progress",
        store=True,
    )

    @api.depends("request_item_ids.state")
    def _compute_signing_progress(self):
        for rec in self:
            items = rec.request_item_ids.filtered(
                lambda i: i.state != "cancelled"
            )
            rec.signers_count = len(items)
            rec.signed_count = len(items.filtered(lambda i: i.state == "signed"))
            rec.all_signed = (
                rec.signers_count > 0
                and rec.signed_count == rec.signers_count
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "easy_sign.request"
                ) or "New"
        return super().create(vals_list)

    def action_send(self):
        """Send signing invitations to all pending signers."""
        self.ensure_one()
        if not self.request_item_ids:
            raise UserError(
                "Please add at least one signer before sending."
            )
        if not self.document:
            raise UserError(
                "Please upload a PDF document before sending."
            )
        active_items = self.request_item_ids.filtered(
            lambda i: i.state in ("pending", "sent")
        )
        if not active_items:
            raise UserError(
                "All signers have already signed or declined."
            )
        self.write({"state": "sent"})
        for item in active_items:
            self._send_invitation(item)
        return True

    def action_cancel(self):
        """Cancel the request and all pending signing items."""
        self.ensure_one()
        self.write({"state": "cancelled"})
        self.request_item_ids.filtered(
            lambda i: i.state not in ("signed", "declined")
        ).write({"state": "cancelled"})
        self.env["sign.log"].create(
            {
                "request_id": self.id,
                "action": "cancelled",
            }
        )
        self.message_post(
            body="Signature request has been cancelled.",
            message_type="notification",
        )
        return True

    def action_reset_to_draft(self):
        """Reset the request back to draft."""
        self.ensure_one()
        self.write({"state": "draft"})
        return True

    def _send_invitation(self, item):
        """Send the signing invitation email — built directly in Python (no Jinja2 template)."""
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        sign_url = f"{base_url}/sign/view/{item.access_token}"
        company = self.env.company
        doc_name = self.document_name or self.name or "Document"
        requester = self.user_id.name or company.name

        expiry_block = ""
        if self.expiry_date:
            expiry_block = f"""
            <p style="margin:6px 0 0 0;font-size:12px;color:#dc2626;font-weight:600;">
                &#9200; Expires on: <strong>{self.expiry_date}</strong>
            </p>"""

        message_block = ""
        if self.message:
            import re
            msg = re.sub(r'<[^>]+>', '', str(self.message)).strip()
            message_block = f"""
        <div style="background:#fffbf0;border:1px solid #fde68a;padding:16px 20px;border-radius:10px;margin:0 0 24px 0;">
            <p style="margin:0 0 6px 0;font-size:11px;color:#92400e;font-weight:700;text-transform:uppercase;letter-spacing:.5px;">
                Message from sender
            </p>
            <p style="margin:0;font-size:14px;color:#555;line-height:1.6;">{msg}</p>
        </div>"""

        body_html = f"""
<div style="font-family:'Segoe UI',Arial,sans-serif;max-width:620px;margin:0 auto;background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 6px 30px rgba(0,0,0,.10);">

    <div style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 60%,#0f3460 100%);padding:40px 36px;text-align:center;">
        <div style="width:60px;height:60px;background:rgba(255,255,255,.15);border-radius:50%;display:inline-flex;align-items:center;justify-content:center;margin-bottom:16px;font-size:28px;">&#9997;&#65039;</div>
        <h1 style="color:#ffffff;margin:0;font-size:22px;font-weight:700;">Document Signature Request</h1>
        <p style="color:rgba(255,255,255,.65);margin:8px 0 0 0;font-size:13px;">{company.name}</p>
    </div>

    <div style="padding:40px 36px;">
        <p style="font-size:16px;color:#1e293b;margin:0 0 12px 0;">
            Dear <strong>{item.signer_name}</strong>,
        </p>
        <p style="font-size:14px;color:#64748b;line-height:1.7;margin:0 0 24px 0;">
            <strong style="color:#1e293b;">{requester}</strong>
            has requested your electronic signature on the following document:
        </p>

        <div style="background:#f0f4ff;border:1px solid #c7d7fe;border-left:4px solid #2563eb;padding:18px 22px;border-radius:0 10px 10px 0;margin:0 0 24px 0;">
            <p style="margin:0;font-size:15px;color:#1e293b;font-weight:700;">&#128196; {doc_name}</p>
            <p style="margin:8px 0 0 0;font-size:12px;color:#64748b;">Reference: <strong>{self.name}</strong></p>
            {expiry_block}
        </div>

        {message_block}

        <div style="text-align:center;margin:32px 0 24px 0;">
            <a href="{sign_url}"
               style="display:inline-block;background:linear-gradient(135deg,#2563eb,#1d4ed8);color:#ffffff;text-decoration:none;padding:16px 48px;border-radius:10px;font-size:16px;font-weight:700;box-shadow:0 6px 20px rgba(37,99,235,.35);">
                &#9997;&#65039; Review &amp; Sign Document
            </a>
        </div>

        <p style="font-size:12px;color:#94a3b8;text-align:center;margin:0 0 6px 0;">
            If the button does not work, copy this link:
        </p>
        <p style="font-size:11px;text-align:center;margin:0 0 30px 0;word-break:break-all;">
            <a href="{sign_url}" style="color:#2563eb;">{sign_url}</a>
        </p>

        <div style="border-top:1px solid #f1f5f9;padding-top:20px;">
            <p style="font-size:11px;color:#94a3b8;margin:0;line-height:1.6;text-align:center;">
                &#128274; This link is unique to you. Do not share it.<br/>
                By signing, you agree to sign this document electronically.
            </p>
        </div>
    </div>

    <div style="background:#f8fafc;padding:20px 36px;text-align:center;border-top:1px solid #e2e8f0;">
        <p style="margin:0;font-size:11px;color:#94a3b8;">
            Powered by <strong style="color:#1e293b;">Easy Sign</strong> &#8212; Secure Electronic Signatures
        </p>
    </div>
</div>"""

        mail_values = {
            "subject": f"[SIGN] Please sign: {doc_name}",
            "email_from": self.user_id.email_formatted or company.email or "noreply@example.com",
            "email_to": item.signer_email,
            "body_html": body_html,
            "auto_delete": True,
        }
        mail = self.env["mail.mail"].sudo().create(mail_values)
        mail.send()

        item.write({"state": "sent"})
        self.env["sign.log"].sudo().create(
            {
                "request_id": self.id,
                "request_item_id": item.id,
                "action": "sent",
            }
        )

    def _check_all_signed(self):
        self.ensure_one()
        # Re-read the signing progress
        active_items = self.request_item_ids.filtered(
            lambda i: i.state != "cancelled"
        )
        if not active_items:
            return
        signed_items = active_items.filtered(lambda i: i.state == "signed")
        if len(signed_items) == len(active_items):
            self._create_signed_document()
            self.write({"state": "signed"})
            self.message_post(
                body="All signers have signed the document. The signed document is now available.",
                message_type="notification",
            )
            # Notify the requester
            self._notify_all_signed()

    def _build_signature_overlay(self, page_w, page_h, signed_items):
        try:
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib.utils import ImageReader
            from PIL import Image

            buf = io.BytesIO()
            c = rl_canvas.Canvas(buf, pagesize=(page_w, page_h))

            sig_w = 160
            sig_h = 60
            margin_x = 40
            margin_y = 30
            gap = 20
            cols = max(1, int((page_w - 2 * margin_x) / (sig_w + gap)))

            for idx, item in enumerate(signed_items):
                try:
                    sig_bytes = base64.b64decode(item.signature)
                    img = Image.open(io.BytesIO(sig_bytes))

                    if img.mode in ('RGBA', 'LA'):
                        bg = Image.new('RGBA', img.size, (255, 255, 255, 255))
                        bg.paste(img, mask=img.split()[-1])
                        img = bg.convert('RGB')
                    else:
                        img = img.convert('RGB')

                    col = idx % cols
                    row = idx // cols
                    x = margin_x + col * (sig_w + gap)
                    y = margin_y + row * (sig_h + gap + 15)

                    img_reader = ImageReader(img)
                    c.drawImage(img_reader, x, y, width=sig_w, height=sig_h,
                                preserveAspectRatio=True, mask='auto')

                    # Signer name below signature
                    c.setFont("Helvetica", 7)
                    c.setFillColorRGB(0.4, 0.4, 0.4)
                    c.drawString(x, y - 10, item.signer_name or "")
                    if item.signed_date:
                        c.setFont("Helvetica", 6)
                        c.drawString(x, y - 18, str(item.signed_date)[:19])

                    _logger.info("Drew signature of %s at (%s,%s)", item.signer_name, x, y)
                except Exception as ex:
                    _logger.error("Failed to draw signature for %s: %s", item.signer_name, ex)

            c.save()
            buf.seek(0)
            return buf.getvalue()
        except ImportError as e:
            _logger.error("reportlab/PIL not available for signature overlay: %s", e)
            return None

    def _create_signed_document(self):
        self.ensure_one()
        _logger.info("_create_signed_document called for %s", self.name)

        try:
            from odoo.tools.pdf import PdfReader, PdfWriter
        except Exception:
            try:
                from pypdf import PdfReader, PdfWriter
            except ImportError:
                try:
                    from PyPDF2 import PdfReader, PdfWriter
                except ImportError:
                    _logger.warning("No PDF library available — saving original as signed document.")
                    self.write({
                        "signed_document": self.document,
                        "signed_document_name": f"signed_{self.document_name or 'document.pdf'}",
                    })
                    return

        try:
            pdf_bytes = base64.b64decode(self.document)
            reader = PdfReader(io.BytesIO(pdf_bytes))
            writer = PdfWriter()

            for page in reader.pages:
                writer.add_page(page)

            signed_items = self.request_item_ids.filtered(
                lambda i: i.state == 'signed' and i.signature
            )
            _logger.info("Found %d signed items with signatures", len(signed_items))

            if signed_items and len(writer.pages) > 0:
                last_page = writer.pages[-1]
                page_w = float(last_page.mediabox.width)
                page_h = float(last_page.mediabox.height)

                overlay_bytes = self._build_signature_overlay(page_w, page_h, signed_items)

                if overlay_bytes:
                    overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
                    overlay_page = overlay_reader.pages[0]
                    if hasattr(last_page, 'merge_page'):
                        last_page.merge_page(overlay_page)
                    elif hasattr(last_page, 'mergePage'):
                        last_page.mergePage(overlay_page)
                    _logger.info("Signature overlay merged into last page of %s", self.name)
                else:
                    _logger.warning("No overlay generated — signatures will not appear in PDF")

            writer.add_metadata({
                "/Title": self.document_name or self.name,
                "/Subject": f"Signed via Easy Sign - {self.name}",
                "/Creator": "Easy Sign - Odoo 18",
            })

            output = io.BytesIO()
            writer.write(output)
            signed_bytes = output.getvalue()
            _logger.info("Signed PDF size: %d bytes", len(signed_bytes))

            self.write({
                "signed_document": base64.b64encode(signed_bytes),
                "signed_document_name": f"signed_{self.document_name or 'document.pdf'}",
            })

        except Exception as e:
            _logger.error("Error in _create_signed_document for %s: %s", self.name, e, exc_info=True)
            self.write(
                {
                    "signed_document": self.document,
                    "signed_document_name": f"signed_{self.document_name or 'document.pdf'}",
                }
            )

    def _notify_all_signed(self):
        """Notify the requester that all parties have signed."""
        self.ensure_one()
        requester = self.user_id
        if not requester or not requester.email:
            return
        base_url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("web.base.url")
        )
        doc_url = (
            f"{base_url}/web#model=sign.request&id={self.id}&view_type=form"
        )
        signers_html = "".join(
            f"<li>{item.signer_name} &lt;{item.signer_email}&gt; — "
            f"Signed on {item.signed_date.strftime('%Y-%m-%d %H:%M') if item.signed_date else 'N/A'}</li>"
            for item in self.request_item_ids.filtered(lambda i: i.state == "signed")
        )
        body_html = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
  <div style="background: #27ae60; padding: 24px; text-align: center; border-radius: 8px 8px 0 0;">
    <h2 style="color: #ffffff; margin: 0;">Document Fully Signed</h2>
  </div>
  <div style="background: #f9f9f9; padding: 32px; border-radius: 0 0 8px 8px;">
    <p>Great news! All signers have completed signing the document
       <strong>"{self.document_name or self.name}"</strong>.</p>
    <p><strong>Signers:</strong></p>
    <ul>{signers_html}</ul>
    <div style="text-align: center; margin: 32px 0;">
      <a href="{doc_url}" style="
        background: #27ae60;
        color: white;
        padding: 14px 36px;
        text-decoration: none;
        border-radius: 6px;
        font-size: 16px;
        font-weight: bold;
        display: inline-block;
      ">View Signed Document</a>
    </div>
  </div>
</div>
"""
        mail_values = {
            "subject": f"[SIGNED] All parties signed: {self.document_name or self.name}",
            "email_from": self.env.company.email
            or "test@example.com",
            "email_to": requester.email,
            "body_html": body_html,
            "auto_delete": True,
        }
        self.env["mail.mail"].sudo().create(mail_values).send()

    def _notify_declined(self, item):
        self.ensure_one()
        requester = self.user_id
        if not requester or not requester.email:
            return
        body_html = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
  <div style="background: #e74c3c; padding: 24px; text-align: center; border-radius: 8px 8px 0 0;">
    <h2 style="color: #ffffff; margin: 0;">Signing Declined</h2>
  </div>
  <div style="background: #f9f9f9; padding: 32px; border-radius: 0 0 8px 8px;">
    <p><strong>{item.signer_name}</strong> ({item.signer_email}) has declined to sign
       the document <strong>"{self.document_name or self.name}"</strong>.</p>
    {f'<p><strong>Reason:</strong> {item.declined_reason}</p>' if item.declined_reason else ''}
  </div>
</div>
"""
        mail_values = {
            "subject": f"[DECLINED] {item.signer_name} declined to sign: {self.document_name or self.name}",
            "email_from": self.env.company.email
            or "admin@example.com",
            "email_to": requester.email,
            "body_html": body_html,
            "auto_delete": True,
        }
        self.env["mail.mail"].sudo().create(mail_values).send()
        self.message_post(
            body=f"{item.signer_name} has declined to sign the document."
            + (f" Reason: {item.declined_reason}" if item.declined_reason else ""),
            message_type="notification",
        )

    def action_download_signed(self):
        self.ensure_one()
        if not self.signed_document:
            raise UserError("The signed document is not yet available.")
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/sign.request/{self.id}/signed_document/{self.signed_document_name}?download=true",
            "target": "self",
        }
