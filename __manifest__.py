# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Easy Sign',
    'version': '18.0.1.0',
    'category': 'Sales/Sign',
    'sequence': 105,
    'summary': "Send documents to sign online and handle filled copies",
    'description': """
Sign and complete your documents easily. Customize your documents with text and signature fields and send them to your recipients.
Let your customers follow the signature process easily.
    """,
    'depends': ['mail', 'attachment_indexation', 'portal'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sign_data.xml',
        'data/mail_templates.xml',
        'views/menus.xml',
        'wizard/sign_send_request_wizard_views.xml',
        'views/sign_template_views.xml',
        'views/sign_request_views.xml',
        'views/sign_log_views.xml',
        'templates/sign_page.xml',
        'templates/template_editor.xml',
    ],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
    'assets': {
        'web.assets_backend': [
            'easy_sign/static/src/scss/sign_common.scss',
            'easy_sign/static/src/scss/sign_backend.scss',
        ],
        'web.assets_frontend': [
            'easy_sign/static/src/scss/sign_common.scss',
            'easy_sign/static/src/scss/sign_frontend.scss',
        ],
        'easy_sign.assets_pdf_iframe': [
            'web/static/src/libs/fontawesome/css/font-awesome.css',
            'web/static/lib/bootstrap/scss/_functions.scss',
            'web/static/src/scss/functions.scss',
            'web/static/src/scss/pre_variables.scss',
            'web/static/lib/bootstrap/scss/_variables.scss',
            'web/static/lib/bootstrap/scss/_variables-dark.scss',
            'web/static/lib/bootstrap/scss/_maps.scss',
            'web/static/lib/bootstrap/scss/vendor/_rfs.scss',
            'web/static/lib/bootstrap/scss/mixins/_deprecate.scss',
            'web/static/lib/bootstrap/scss/mixins/_utilities.scss',
            'web/static/lib/bootstrap/scss/mixins/_breakpoints.scss',
            'web/static/lib/bootstrap/scss/mixins/_grid.scss',
            'web/static/lib/bootstrap/scss/_utilities.scss',
            'web/static/src/scss/bs_mixins_overrides.scss',
            'web/static/lib/bootstrap/scss/utilities/_api.scss',
            'web/static/src/scss/utils.scss',
            'web/static/src/scss/primary_variables.scss',
            'web/static/src/scss/secondary_variables.scss',
            'easy_sign/static/src/scss/iframe.scss',
        ],
    }
}
