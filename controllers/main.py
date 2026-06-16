# -*- coding: utf-8 -*-
import base64
import io
import json
import logging
from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.http import content_disposition

_logger = logging.getLogger(__name__)


class SignController(http.Controller):
    @http.route('/sign/template/<int:template_id>/pdf', type='http', auth='public')
    def sign_template_pdf(self, template_id, **kwargs):
        template = request.env['sign.template'].sudo().browse(template_id)
        if not template or not template.attachment_id:
            return request.not_found()
        return request.make_response(
            base64.b64decode(template.attachment_id.datas),
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', content_disposition('%s' % template.attachment_id.name)),
                ('X-Frame-Options', 'SAMEORIGIN'),
            ]
        )

    @http.route('/sign/template/<int:template_id>/edit', type='http', auth='user', website=True)
    def sign_template_edit(self, template_id, **kwargs):
        template = request.env['sign.template'].sudo().browse(template_id)
        if not template:
            return request.not_found()
        return request.render('easy_sign.template_editor', {'template': template})

    @http.route('/sign/document/<int:request_id>/<access_token>', type='http', auth='public', website=True)
    def sign_document_public(self, request_id, access_token, **kwargs):
        SignRequestItem = request.env['sign.request.item'].sudo()
        item = SignRequestItem.search([('access_token', '=', access_token), ('sign_request_id', '=', request_id)], limit=1)
        if not item:
            return request.not_found()
        if item.state not in ['sent', 'viewed']:
            return request.render('easy_sign.sign_already_signed', {})
        if item.state == 'sent':
            item.write({'state': 'viewed'})
            request.env['sign.log'].sudo().create({
                'sign_request_id': item.sign_request_id.id,
                'sign_request_item_id': item.id,
                'action': 'view',
                'ip_address': request.httprequest.environ.get('REMOTE_ADDR'),
            })
        values = {
            'sign_request': item.sign_request_id,
            'access_token': access_token,
            'request_item': item,
        }
        return request.render('easy_sign.sign_page', values)

    @http.route('/sign/submit/<int:request_id>/<access_token>', type='http', auth='public', csrf=False, methods=['POST'])
    def sign_submit(self, request_id, access_token, **kwargs):
        SignRequestItem = request.env['sign.request.item'].sudo()
        item = SignRequestItem.search([('access_token', '=', access_token), ('sign_request_id', '=', request_id)], limit=1)
        if not item or item.state not in ['sent', 'viewed']:
            return json.dumps({'success': False})
        try:
            signature_values = {}
            data = json.loads(kwargs.get('data', '{}'))
            for k, v in data.items():
                signature_values[k] = v
            item._sign(signature_values)
            return json.dumps({'success': True})
        except Exception as e:
            _logger.error(e)
            return json.dumps({'success': False})

    @http.route('/sign/download/<int:request_id>/<access_token>/completed', type='http', auth='public')
    def download_completed(self, request_id, access_token, **kwargs):
        sign_request = request.env['sign.request'].sudo().search([
            ('id', '=', request_id),
            ('access_token', '=', access_token)
        ], limit=1)
        if not sign_request or sign_request.state != 'signed' or not sign_request.completed_document:
            return request.not_found()
        return request.make_response(
            base64.b64decode(sign_request.completed_document),
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', content_disposition('%s.pdf' % sign_request.reference)),
            ]
        )
