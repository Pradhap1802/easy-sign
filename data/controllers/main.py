import base64
import json
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class EasySignController(http.Controller):

    def _get_item_by_token(self, token):
        item = (
            request.env["sign.request.item"]
            .sudo()
            .search([("access_token", "=", token)], limit=1)
        )
        return item

    def _is_expired(self, sign_request):
        if not sign_request.expiry_date:
            return False
        today = fields.Date.today()
        return sign_request.expiry_date < today



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
            return request.render("easy_sign.sign_invalid", {
                "error_title": "Invalid Link",
                "error_message": "This signing link is invalid or does not exist.",
            })

        sign_request = item.request_id

        if sign_request.state == "cancelled" or item.state == "cancelled":
            return request.render("easy_sign.sign_invalid", {
                "error_title": "Request Cancelled",
                "error_message": "This signature request has been cancelled.",
            })

        if self._is_expired(sign_request):
            sign_request.sudo().write({"state": "expired"})
            return request.render("easy_sign.sign_invalid", {
                "error_title": "Link Expired",
                "error_message": f"This signing link expired on {sign_request.expiry_date}.",
            })

        if item.state == "signed":
            return request.render("easy_sign.sign_success", {
                "item": item,
                "sign_request": sign_request,
                "already_done": True,
            })

        if item.state == "declined":
            return request.render("easy_sign.sign_declined", {
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

        return request.render("easy_sign.sign_page", {
            "item": item,
            "sign_request": sign_request,
            "token": token,
            "document_url": f"/sign/document/{token}",
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
        signature_data_url = post_data.get("signature", "")

        if not signature_data_url:
            return request.make_response(
                json.dumps({"success": False, "error": "No signature provided"}),
                headers=[("Content-Type", "application/json")],
                status=400,
            )

        try:
            if "," in signature_data_url:
                signature_b64 = signature_data_url.split(",", 1)[1]
            else:
                signature_b64 = signature_data_url

            base64.b64decode(signature_b64)

            ip_address = request.httprequest.remote_addr
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
                json.dumps(
                    {"success": False, "error": f"Already {item.state}"}
                ),
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
