# -*- coding: utf-8 -*-
import base64
import io
import json
import logging
from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.http import content_disposition
from markupsafe import Markup

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
        sign_item_types = request.env['sign.item.type'].sudo().search_read([], ['id', 'name', 'item_type', 'default_width', 'default_height'])
        sign_roles = request.env['sign.item.role'].sudo().search_read([], ['id', 'name', 'color'])
        sign_items = template.sign_item_ids.read([
            'id', 'type_id', 'required', 'responsible_id', 'name', 'page', 'posX', 'posY', 'width', 'height', 'alignment', 'placeholder'
        ])
        return request.render('easy_sign.template_editor', {
            'template': template,
            'sign_item_types': sign_item_types,
            'sign_roles': sign_roles,
            'sign_items': sign_items,
            'sign_item_types_json': Markup(json.dumps(sign_item_types)),
            'sign_roles_json':      Markup(json.dumps(sign_roles)),
            'sign_items_json':      Markup(json.dumps(sign_items)),
            'template_name_json':   Markup(json.dumps(template.name or '')),
        })

    @http.route('/sign/template/<int:template_id>/items', type='json', auth='user')
    def get_template_items(self, template_id, **kwargs):
        template = request.env['sign.template'].sudo().browse(template_id)
        if not template:
            return []
        return template.sign_item_ids.read([
            'id', 'type_id', 'required', 'responsible_id', 'name', 'page', 'posX', 'posY', 'width', 'height', 'alignment', 'placeholder'
        ])

    @http.route('/sign/template/<int:template_id>/save', type='json', auth='user')
    def save_template_items(self, template_id, items, **kwargs):
        template = request.env['sign.template'].sudo().browse(template_id)
        if not template:
            return False
        # Delete existing items not in the list
        existing_ids = [item['id'] for item in items if item.get('id') and item['id'] > 0]
        template.sign_item_ids.filtered(lambda x: x.id not in existing_ids).unlink()
        # Update or create items
        for item_data in items:
            item_data['template_id'] = template.id
            if item_data.get('id') and item_data['id'] > 0:
                # Update existing item
                item = request.env['sign.item'].sudo().browse(item_data['id'])
                item.write(item_data)
            else:
                # Create new item
                item_data.pop('id', None)
                request.env['sign.item'].sudo().create(item_data)
        return True

    @http.route('/sign/template/<int:template_id>/send', type='json', auth='user')
    def send_template_for_signing(self, template_id, signers=None, reference='', subject='', **kwargs):
        template = request.env['sign.template'].sudo().browse(template_id)
        if not template:
            return {'error': 'Template not found'}
        if not template.sign_item_ids:
            return {'error': 'Please save at least one field on the template before sending.'}

        sign_request = request.env['sign.request'].sudo().create({
            'template_id': template.id,
            'reference': reference or template.name,
            'subject': subject or ('Signature Request: %s' % template.name),
        })

        return {
            'success': True,
            'request_id': sign_request.id,
            'url': '/odoo/sign-requests/%d' % sign_request.id,
        }

    @http.route('/sign/document/<int:request_id>/<access_token>', type='http', auth='public', website=True)
    def sign_document_public(self, request_id, access_token, **kwargs):
        sign_request = request.env['sign.request'].sudo().search([
            ('access_token', '=', access_token),
            ('id', '=', request_id)
        ], limit=1)
        if not sign_request:
            return request.not_found()
        if sign_request.state != 'sent':
            return request.render('easy_sign.sign_already_signed', {})
        
        request.env['sign.log'].sudo().create({
            'sign_request_id': sign_request.id,
            'action': 'view',
            'ip_address': request.httprequest.environ.get('REMOTE_ADDR'),
        })

        # Dynamically fetch recipient signer details for auto-fill
        partner = None
        if not request.env.user._is_public():
            partner = request.env.user.partner_id
        else:
            last_log = request.env['sign.log'].sudo().search([
                ('sign_request_id', '=', sign_request.id),
                ('action', '=', 'send')
            ], order='id desc', limit=1)
            if last_log and last_log.partner_id:
                partner = last_log.partner_id

        signer_vals = {
            'name': '',
            'email': '',
            'phone': '',
            'company': '',
            'title': '',
            'city': '',
            'zip': '',
            'country': '',
            'state': '',
        }
        if partner:
            signer_vals = {
                'name': partner.name or '',
                'email': partner.email or '',
                'phone': partner.phone or partner.mobile or '',
                'company': partner.commercial_company_name or (partner.parent_id.name if partner.parent_id else '') or (partner.company_id.name if partner.company_id else ''),
                'title': partner.function or '',
                'city': partner.city or '',
                'zip': partner.zip or '',
                'country': partner.country_id.name if partner.country_id else '',
                'state': partner.state_id.name if partner.state_id else '',
            }

        values = {
            'sign_request': sign_request,
            'access_token': access_token,
            'signer_info_json': json.dumps(signer_vals),
        }
        return request.render('easy_sign.sign_page', values)

    @http.route('/sign/submit/<int:request_id>/<access_token>', type='http', auth='public', csrf=False, methods=['POST'])
    def sign_submit(self, request_id, access_token, **kwargs):
        sign_request = request.env['sign.request'].sudo().search([
            ('access_token', '=', access_token),
            ('id', '=', request_id)
        ], limit=1)
        if not sign_request or sign_request.state != 'sent':
            return json.dumps({'success': False})
        try:
            signature_values = {}
            data = json.loads(kwargs.get('data', '{}'))
            for k, v in data.items():
                signature_values[k] = v
            sign_request._sign(signature_values)
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
