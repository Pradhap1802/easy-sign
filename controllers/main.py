# -*- coding: utf-8 -*-
from odoo.http import content_disposition
import base64
import io
import json
import logging
from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError, UserError
from markupsafe import Markup

_logger = logging.getLogger(__name__)


class SignController(http.Controller):
    @http.route('/sign/template/<int:template_id>/pdf', type='http', auth='user', website=False)
    def sign_template_pdf(self, template_id, **kwargs):
        template = request.env['sign.template'].sudo().browse(template_id)
        if not template or not template.datas:
            return request.not_found()
        datas = template.sudo().datas
        if not datas:
            return request.not_found()
        pdf_bytes = base64.b64decode(datas)
        return request.make_response(
            pdf_bytes,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', 'inline; filename="%s"' % (template.name or 'document.pdf')),
                ('X-Frame-Options', 'SAMEORIGIN'),
                ('Cache-Control', 'no-cache, no-store, must-revalidate'),
            ]
        )

    @http.route('/sign/template/<int:template_id>/edit', type='http', auth='user', website=True)
    def sign_template_edit(self, template_id, **kwargs):
        template = request.env['sign.template'].sudo().browse(template_id)
        if not template:
            return request.not_found()
        sign_item_types = request.env['sign.item.type'].sudo().search_read([], ['id', 'name', 'item_type', 'default_width', 'default_height', 'is_mandatory'])
        sign_roles = request.env['sign.item.role'].sudo().search_read([], ['id', 'name', 'color'])
        sign_items = template.sign_item_ids.read([
            'id', 'type_id', 'required', 'responsible_id', 'name', 'page', 'posX', 'posY', 'width', 'height', 'alignment', 'placeholder'
        ])
        
        template_signers = [{
            'role_id': s.role_id.id,
            'partner_id': s.partner_id.id if s.partner_id else False,
            'partner_name': s.partner_id.name if s.partner_id else '',
            'email': s.email or '',
        } for s in template.template_signer_ids]

        # Load all available sign tags and template's current tag IDs
        all_tags = request.env['sign.tag'].sudo().search_read([], ['id', 'name', 'color'])
        template_tag_ids = template.tag_ids.ids

        # Pass PDF data as base64 string directly
        raw_datas = template.sudo().datas
        if raw_datas:
            pdf_b64_str = raw_datas.decode('utf-8') if isinstance(raw_datas, bytes) else str(raw_datas)
        else:
            pdf_b64_str = ''
        return request.render('easy_sign.template_editor', {
            'template': template,
            'sign_item_types': sign_item_types,
            'sign_roles': sign_roles,
            'sign_items': sign_items,
            'sign_item_types_json': Markup(json.dumps(sign_item_types)),
            'sign_roles_json':      Markup(json.dumps(sign_roles)),
            'sign_items_json':      Markup(json.dumps(sign_items)),
            'template_signers_json': Markup(json.dumps(template_signers)),
            'template_name_json':   Markup(json.dumps(template.name or '')),
            'pdf_b64_json':         Markup(json.dumps(pdf_b64_str)),
            'all_tags_json':        Markup(json.dumps(all_tags)),
            'template_tag_ids_json': Markup(json.dumps(template_tag_ids)),
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
    def save_template_items(self, template_id, items, signers=None, **kwargs):
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
                
        # Save template signers mapping
        if signers is not None:
            template.template_signer_ids.unlink()
            for s in signers:
                request.env['sign.template.signer'].sudo().create({
                    'template_id': template.id,
                    'role_id': s.get('role_id'),
                    'partner_id': s.get('partner_id') or False,
                    'email': s.get('email') or '',
                })
        return True

    @http.route('/sign/template/<int:template_id>/save_tags', type='json', auth='user')
    def save_template_tags(self, template_id, tag_ids=None, **kwargs):
        template = request.env['sign.template'].sudo().browse(template_id)
        if not template:
            return False
        if tag_ids is None:
            tag_ids = []
        template.write({'tag_ids': [(6, 0, tag_ids)]})
        return True

    @http.route('/sign/role/get_or_create', type='json', auth='user')
    def get_or_create_role(self, name, **kwargs):
        role = request.env['sign.item.role'].sudo().search([('name', '=', name)], limit=1)
        if not role:
            max_role = request.env['sign.item.role'].sudo().search([], order='sequence desc', limit=1)
            seq = (max_role.sequence + 1) if max_role else 10
            role = request.env['sign.item.role'].sudo().create({
                'name': name,
                'sequence': seq,
                'default': False,
            })
        return {'id': role.id, 'name': role.name, 'color': role.color or 0}

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

        if signers:
            request_signers = []
            for sequence, signer_val in enumerate(signers, start=1):
                email = signer_val.get('email', '').strip()
                name = signer_val.get('name', '').strip() or email
                role_id = signer_val.get('role_id')
                
                partner = request.env['res.partner'].sudo().search([('email', '=', email)], limit=1)
                if not partner:
                    partner = request.env['res.partner'].sudo().create({
                        'name': name,
                        'email': email,
                    })
                request_signers.append({
                    'sign_request_id': sign_request.id,
                    'role_id': role_id,
                    'partner_id': partner.id,
                    'sequence': sequence,
                    'state': 'draft',
                })
            request.env['sign.request.signer'].sudo().create(request_signers)
            sign_request.sudo().action_send_next_signature_request()

        return {
            'success': True,
            'request_id': sign_request.id,
            'url': '/odoo/sign-requests/%d' % sign_request.id,
        }

    @http.route('/sign/document/<int:request_id>/<access_token>', type='http', auth='public', website=True)
    def sign_document_public(self, request_id, access_token, **kwargs):
        signer = request.env['sign.request.signer'].sudo().search([
            ('access_token', '=', access_token),
            ('sign_request_id', '=', request_id)
        ], limit=1)
        
        if signer:
            sign_request = signer.sign_request_id
            if signer.state == 'signed' or sign_request.state != 'sent':
                return request.render('easy_sign.sign_already_signed', {})
            partner = signer.partner_id
            current_role_id = signer.role_id.id
        else:
            sign_request = request.env['sign.request'].sudo().search([
                ('access_token', '=', access_token),
                ('id', '=', request_id)
            ], limit=1)
            if not sign_request:
                return request.not_found()
            if sign_request.state != 'sent':
                return request.render('easy_sign.sign_already_signed', {})
            
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
            current_role_id = 0

        request.env['sign.log'].sudo().create({
            'sign_request_id': sign_request.id,
            'action': 'view',
            'ip_address': request.httprequest.environ.get('REMOTE_ADDR'),
        })

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

        pdf_b64 = sign_request.template_id.sudo().datas or ''
        if isinstance(pdf_b64, bytes):
            pdf_b64 = pdf_b64.decode('utf-8')

        sign_items_data = []
        for item in sign_request.template_id.sign_item_ids:
            sign_items_data.append({
                'id': item.id,
                'type': item.type_id.item_type,
                'name': item.name or '',
                'placeholder': item.placeholder or '',
                'page': item.page,
                'posX': item.posX,
                'posY': item.posY,
                'width': item.width,
                'height': item.height,
                'required': item.required,
                'responsible_id': item.responsible_id.id or 0,
            })

        values_dict = request.env['sign.request.item.value'].sudo().search_read(
            [('sign_request_id', '=', sign_request.id)],
            ['sign_item_id', 'value', 'frame_value']
        )
        item_values = {}
        for v in values_dict:
            item_values[v['sign_item_id']] = {
                'value': v['value'],
                'frame': v['frame_value'],
            }

        signers_list = []
        for s in sign_request.signer_ids:
            signers_list.append({
                'name': s.partner_id.name,
                'state': s.state,
                'role_name': s.role_id.name,
            })

        show_back_button = not request.env.user._is_public() and not request.env.user.share
        values = {
            'sign_request': sign_request,
            'access_token': access_token,
            'signer_info_json': json.dumps(signer_vals),
            'pdf_b64_json': Markup(json.dumps(pdf_b64)),
            'sign_items_json': Markup(json.dumps(sign_items_data)),
            'current_role_id': current_role_id,
            'item_values_json': Markup(json.dumps(item_values)),
            'signers': signers_list,
            'show_back_button': show_back_button,
        }
        return request.render('easy_sign.sign_page', values)

    @http.route('/sign/submit/<int:request_id>/<access_token>', type='http', auth='public', csrf=False, methods=['POST'])
    def sign_submit(self, request_id, access_token, **kwargs):
        signer = request.env['sign.request.signer'].sudo().search([
            ('access_token', '=', access_token),
            ('sign_request_id', '=', request_id)
        ], limit=1)
        
        if signer:
            sign_request = signer.sign_request_id
        else:
            sign_request = request.env['sign.request'].sudo().search([
                ('access_token', '=', access_token),
                ('id', '=', request_id)
            ], limit=1)
            signer = False

        if not sign_request or sign_request.state != 'sent':
            return json.dumps({'success': False})
        try:
            signature_values = {}
            data = json.loads(kwargs.get('data', '{}'))
            for k, v in data.items():
                signature_values[k] = v
            sign_request._sign_with_signer(signature_values, signer)
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

    @http.route('/sign/template/<int:template_id>/share/get_or_create', type='json', auth='user')
    def share_get_or_create(self, template_id, **kwargs):
        template = request.env['sign.template'].sudo().browse(template_id)
        if not template:
            return {'error': 'Template not found'}
        if not template.share_token:
            import uuid
            template.sudo().write({'share_token': str(uuid.uuid4())})
        
        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        share_url = "%s/sign/share/%d/%s" % (base_url, template.id, template.share_token)
        return {
            'share_url': share_url,
            'valid_until': template.valid_until.strftime('%Y-%m-%d') if template.valid_until else ''
        }

    @http.route('/sign/template/<int:template_id>/share/update', type='json', auth='user')
    def share_update(self, template_id, valid_until=None, **kwargs):
        template = request.env['sign.template'].sudo().browse(template_id)
        if not template:
            return {'error': 'Template not found'}
        vals = {}
        if valid_until is not None:
            vals['valid_until'] = valid_until or False
        template.sudo().write(vals)
        return {'success': True}

    @http.route('/sign/template/<int:template_id>/share/stop', type='json', auth='user')
    def share_stop(self, template_id, **kwargs):
        template = request.env['sign.template'].sudo().browse(template_id)
        if not template:
            return {'error': 'Template not found'}
        template.sudo().write({
            'share_token': False,
            'valid_until': False
        })
        return {'success': True}

    @http.route('/sign/share/<int:template_id>/<share_token>', type='http', auth='public', website=True)
    def share_template_page(self, template_id, share_token, **kwargs):
        template = request.env['sign.template'].sudo().search([
            ('id', '=', template_id),
            ('share_token', '=', share_token)
        ], limit=1)
        if not template:
            return request.not_found()
            
        from odoo.fields import Date
        if template.valid_until and template.valid_until < Date.today():
            return request.render('easy_sign.sign_expired_template', {'template': template})
            
        roles = template.sign_item_ids.mapped('responsible_id')
        if not roles:
            default_role = request.env['sign.item.role'].sudo().search([('name', '=', 'Signer 1')], limit=1)
            roles = default_role
            
        return request.render('easy_sign.sign_share_template', {
            'template': template,
            'roles': roles,
        })

    @http.route('/sign/share/<int:template_id>/<share_token>/submit', type='http', auth='public', methods=['POST'], website=True, csrf=True)
    def share_template_submit(self, template_id, share_token, **kwargs):
        template = request.env['sign.template'].sudo().search([
            ('id', '=', template_id),
            ('share_token', '=', share_token)
        ], limit=1)
        if not template:
            return request.not_found()
            
        from odoo.fields import Date
        if template.valid_until and template.valid_until < Date.today():
            return request.render('easy_sign.sign_expired_template', {'template': template})
            
        roles = template.sign_item_ids.mapped('responsible_id')
        if not roles:
            default_role = request.env['sign.item.role'].sudo().search([('name', '=', 'Signer 1')], limit=1)
            roles = default_role
            
        sign_request = request.env['sign.request'].sudo().create({
            'template_id': template.id,
            'reference': "%s (Shared)" % (template.name or 'Document'),
            'state': 'sent'
        })
        
        first_signer = False
        for idx, role in enumerate(roles, start=1):
            name = kwargs.get('name_%d' % role.id, '').strip()
            email = kwargs.get('email_%d' % role.id, '').strip()
            
            partner = request.env['res.partner'].sudo().search([('email', '=', email)], limit=1)
            if not partner and email:
                partner = request.env['res.partner'].sudo().create({
                    'name': name or email,
                    'email': email
                })
                
            import uuid
            signer = request.env['sign.request.signer'].sudo().create({
                'sign_request_id': sign_request.id,
                'role_id': role.id,
                'partner_id': partner.id,
                'sequence': idx,
                'state': 'draft',
                'access_token': str(uuid.uuid4())
            })
            if idx == 1:
                first_signer = signer
                
        sign_request.sudo().action_send_next_signature_request()
        
        if first_signer:
            return request.redirect('/sign/document/%d/%s' % (sign_request.id, first_signer.access_token))
        return request.not_found()

    @http.route('/sign/partners/search', type='json', auth='user')
    def search_partners(self, term, limit=10, **kwargs):
        domain = ['|', ('name', 'ilike', term), ('email', 'ilike', term)]
        partners = request.env['res.partner'].sudo().search_read(domain, ['id', 'name', 'email'], limit=limit)
        return partners


