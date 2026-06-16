import base64
import json
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class EasySignController(http.Controller):

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    def _get_item_by_token(self, token):
        return (
            request.env["sign.request.item"]
            .sudo()
            .search([("access_token", "=", token)], limit=1)
        )

    def _is_expired(self, sign_request):
        if not sign_request.expiry_date:
            return False
        return sign_request.expiry_date < fields.Date.today()

    # ──────────────────────────────────────────────
    # Public signing routes
    # ──────────────────────────────────────────────

    @http.route(
        "/sign/view/<string:token>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def sign_view(self, token, **kwargs):
        item = self._get_item_by_token(token)

        if not item:
            return request.render("easy-sign.sign_invalid", {
                "error_title": "Invalid Link",
                "error_message": "This signing link is invalid or does not exist.",
            })

        sign_request = item.request_id

        if sign_request.state == "cancelled" or item.state == "cancelled":
            return request.render("easy-sign.sign_invalid", {
                "error_title": "Request Cancelled",
                "error_message": "This signature request has been cancelled.",
            })

        if self._is_expired(sign_request):
            sign_request.sudo().write({"state": "expired"})
            return request.render("easy-sign.sign_invalid", {
                "error_title": "Link Expired",
                "error_message": f"This signing link expired on {sign_request.expiry_date}.",
            })

        if item.state == "signed":
            return request.render("easy-sign.sign_success", {
                "item": item,
                "sign_request": sign_request,
                "already_done": True,
            })

        if item.state == "declined":
            return request.render("easy-sign.sign_declined", {
                "item": item,
                "sign_request": sign_request,
                "already_done": True,
            })

        if item.state == "sent":
            item.write({"state": "viewed"})
            request.env["sign.log"].sudo().create({
                "request_id": sign_request.id,
                "request_item_id": item.id,
                "action": "viewed",
                "ip_address": request.httprequest.remote_addr,
            })

        # Build field data for this signer if the request has a template
        template_fields_json = "[]"
        has_fields = False
        if sign_request.template_id and sign_request.template_id.field_ids:
            signer_fields = sign_request.template_id.field_ids.filtered(
                lambda f: f.signer_index == item.signer_index
            )
            if signer_fields:
                has_fields = True
                fields_data = []
                for tf in signer_fields:
                    # Check if already filled
                    existing = item.field_value_ids.filtered(
                        lambda v: v.template_field_id.id == tf.id
                    )
                    fields_data.append({
                        "id": tf.id,
                        "field_type": tf.field_type,
                        "page": tf.page,
                        "pos_x": tf.pos_x,
                        "pos_y": tf.pos_y,
                        "width": tf.width,
                        "height": tf.height,
                        "required": tf.required,
                        "placeholder": tf.placeholder or "",
                        "signer_index": tf.signer_index,
                        "value": existing[0].value if existing else "",
                    })
                template_fields_json = json.dumps(fields_data)

        return request.render("easy-sign.sign_page", {
            "item": item,
            "sign_request": sign_request,
            "token": token,
            "document_url": f"/sign/document/{token}",
            "has_fields": has_fields,
            "template_fields_json": template_fields_json,
        })

    @http.route(
        "/sign/document/<string:token>",
        type="http",
        auth="public",
        sitemap=False,
    )
    def sign_document(self, token, **kwargs):
        item = self._get_item_by_token(token)
        if not item or not item.request_id.document:
            return request.not_found()

        sign_request = item.request_id

        if sign_request.state == "cancelled" or item.state == "cancelled":
            return request.not_found()
        if self._is_expired(sign_request):
            return request.not_found()

        try:
            pdf_bytes = base64.b64decode(sign_request.document)
        except Exception:
            return request.not_found()

        filename = sign_request.document_name or "document.pdf"
        return request.make_response(
            pdf_bytes,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Disposition", f'inline; filename="{filename}"'),
                ("Content-Length", str(len(pdf_bytes))),
                ("X-Frame-Options", "SAMEORIGIN"),
            ],
        )

    @http.route(
        "/sign/submit/<string:token>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        sitemap=False,
    )
    def sign_submit(self, token, **kwargs):
        item = self._get_item_by_token(token)
        if not item:
            return request.make_response(
                json.dumps({"success": False, "error": "Invalid token"}),
                headers=[("Content-Type", "application/json")],
                status=404,
            )

        sign_request = item.request_id

        if sign_request.state == "cancelled" or item.state == "cancelled":
            return request.make_response(
                json.dumps({"success": False, "error": "Request is cancelled"}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )

        if self._is_expired(sign_request):
            return request.make_response(
                json.dumps({"success": False, "error": "Request has expired"}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )

        if item.state == "signed":
            return request.make_response(
                json.dumps({"success": False, "error": "Already signed"}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )

        post_data = request.httprequest.form
        ip_address = request.httprequest.remote_addr

        try:
            # ── Template field values ────────────────────────────
            if sign_request.template_id and sign_request.template_id.field_ids:
                signer_fields = sign_request.template_id.field_ids.filtered(
                    lambda f: f.signer_index == item.signer_index
                )
                for tf in signer_fields:
                    fkey_val = f"field_{tf.id}_value"
                    fkey_sig = f"field_{tf.id}_signature"

                    val = post_data.get(fkey_val, "")
                    sig_b64 = post_data.get(fkey_sig, "")

                    # Validate required fields
                    if tf.required and not val and not sig_b64:
                        return request.make_response(
                            json.dumps({"success": False, "error": f"Field '{tf.placeholder or tf.field_type}' is required."}),
                            headers=[("Content-Type", "application/json")],
                            status=400,
                        )

                    # Remove old value if exists
                    item.field_value_ids.filtered(
                        lambda v: v.template_field_id.id == tf.id
                    ).unlink()

                    sig_binary = None
                    if sig_b64 and "," in sig_b64:
                        sig_b64 = sig_b64.split(",", 1)[1]
                    if sig_b64:
                        sig_binary = base64.b64decode(sig_b64)

                    request.env["sign.request.field.value"].sudo().create({
                        "request_id": sign_request.id,
                        "request_item_id": item.id,
                        "template_field_id": tf.id,
                        "value": val,
                        "signature_value": base64.b64encode(sig_binary) if sig_binary else False,
                    })

                # Use the main signature field's data as the item.signature
                sig_fields = signer_fields.filtered(lambda f: f.field_type in ("signature", "initial"))
                if sig_fields:
                    main_sig_key = f"field_{sig_fields[0].id}_signature"
                    sig_data_url = post_data.get(main_sig_key, "")
                    if sig_data_url:
                        if "," in sig_data_url:
                            sig_data_url = sig_data_url.split(",", 1)[1]
                        item.action_sign(sig_data_url, ip_address=ip_address)
                    else:
                        # No signature drawn but other fields filled — still mark as signed
                        item.action_sign("", ip_address=ip_address)
                else:
                    # No signature field type — mark as signed with empty
                    item.action_sign("", ip_address=ip_address)

            else:
                # ── Legacy: plain signature canvas ──────────────
                signature_data_url = post_data.get("signature", "")
                if not signature_data_url:
                    return request.make_response(
                        json.dumps({"success": False, "error": "No signature provided"}),
                        headers=[("Content-Type", "application/json")],
                        status=400,
                    )
                if "," in signature_data_url:
                    signature_b64 = signature_data_url.split(",", 1)[1]
                else:
                    signature_b64 = signature_data_url
                base64.b64decode(signature_b64)
                item.action_sign(signature_b64, ip_address=ip_address)

            return request.make_response(
                json.dumps({"success": True}),
                headers=[("Content-Type", "application/json")],
            )

        except Exception as e:
            _logger.error("Error saving signature for token %s: %s", token, e)
            return request.make_response(
                json.dumps({"success": False, "error": str(e)}),
                headers=[("Content-Type", "application/json")],
                status=500,
            )

    @http.route(
        "/sign/decline/<string:token>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        sitemap=False,
    )
    def sign_decline(self, token, **kwargs):
        item = self._get_item_by_token(token)
        if not item:
            return request.make_response(
                json.dumps({"success": False, "error": "Invalid token"}),
                headers=[("Content-Type", "application/json")],
                status=404,
            )

        sign_request = item.request_id

        if sign_request.state == "cancelled" or item.state == "cancelled":
            return request.make_response(
                json.dumps({"success": False, "error": "Request is cancelled"}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )

        if item.state in ("signed", "declined"):
            return request.make_response(
                json.dumps({"success": False, "error": f"Already {item.state}"}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )

        try:
            post_data = request.httprequest.form
            reason = post_data.get("reason", "")
            ip_address = request.httprequest.remote_addr
            item.action_decline(reason=reason, ip_address=ip_address)
            return request.make_response(
                json.dumps({"success": True}),
                headers=[("Content-Type", "application/json")],
            )
        except Exception as e:
            _logger.error("Error declining for token %s: %s", token, e)
            return request.make_response(
                json.dumps({"success": False, "error": str(e)}),
                headers=[("Content-Type", "application/json")],
                status=500,
            )

    # ──────────────────────────────────────────────
    # Template Editor Routes (authenticated)
    # ──────────────────────────────────────────────

    @http.route(
        "/sign/template/<int:template_id>/edit",
        type="http",
        auth="user",
        sitemap=False,
    )
    def template_editor(self, template_id, **kwargs):
        template = request.env["sign.template"].browse(template_id)
        if not template.exists():
            return request.not_found()

        # Serialize existing field placements as JSON
        fields_data = []
        for tf in template.field_ids:
            fields_data.append({
                "id": tf.id,
                "field_type": tf.field_type,
                "page": tf.page,
                "pos_x": tf.pos_x,
                "pos_y": tf.pos_y,
                "width": tf.width,
                "height": tf.height,
                "required": tf.required,
                "placeholder": tf.placeholder or "",
                "signer_index": tf.signer_index,
            })

        return request.render("easy-sign.template_editor", {
            "template": template,
            "fields_json": json.dumps(fields_data),
        })

    @http.route(
        "/sign/template/<int:template_id>/pdf",
        type="http",
        auth="user",
        sitemap=False,
    )
    def template_pdf(self, template_id, **kwargs):
        template = request.env["sign.template"].sudo().browse(template_id)
        if not template.exists() or not template.pdf_document:
            return request.not_found()
        try:
            pdf_bytes = base64.b64decode(template.pdf_document)
        except Exception:
            return request.not_found()
        filename = template.pdf_document_name or "template.pdf"
        return request.make_response(
            pdf_bytes,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Disposition", f'inline; filename="{filename}"'),
                ("Content-Length", str(len(pdf_bytes))),
            ],
        )

    @http.route(
        "/sign/template/<int:template_id>/save_fields",
        type="json",
        auth="user",
        methods=["POST"],
        sitemap=False,
    )
    def save_template_fields(self, template_id, fields_data=None, signer_count=None, **kwargs):
        template = request.env["sign.template"].browse(template_id)
        if not template.exists():
            return {"error": "Template not found"}
        if fields_data is None:
            fields_data = []
        try:
            if signer_count is not None:
                template.signer_count = int(signer_count)

            # Remove existing placements
            template.field_ids.unlink()
            # Create new ones
            for fd in fields_data:
                request.env["sign.template.field"].create({
                    "template_id": template.id,
                    "field_type":   fd.get("field_type", "signature"),
                    "page":         int(fd.get("page", 1)),
                    "pos_x":        float(fd.get("pos_x", 0)),
                    "pos_y":        float(fd.get("pos_y", 0)),
                    "width":        float(fd.get("width", 20)),
                    "height":       float(fd.get("height", 8)),
                    "required":     bool(fd.get("required", True)),
                    "placeholder":  fd.get("placeholder", "") or "",
                    "signer_index": int(fd.get("signer_index", 1)),
                })
            return {"success": True, "count": len(fields_data)}
        except Exception as e:
            _logger.error("save_template_fields error: %s", e)
            return {"error": str(e)}
