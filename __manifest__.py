# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Easy Sign',
    'version': '18.0.1.0',
    'category': 'Sales/Sign',
    'sequence': 105,
    'summary': "Send documents to sign online and handle filled copies",
    'description': """
Easy Sign - Electronic Signature & Document Management
========================================================
Sign and complete your documents easily in Odoo 18. Customize your PDF documents with text, initial, and signature fields and send them to your recipients.

Key Features:
-------------
* Visual Drag & Drop PDF Template Field Editor
* Sequential Multi-Signer Workflow Engine
* Audit Trail Certificate with Cryptographic SHA-256 Checksum Hash
* Real-Time Client Validation & Auto-Fill from Partner Records
* 1-Click Saved Profile Signatures
* Automated Daily Cron Reminders & Manual Send Reminder Action
* Page-Level Document Watermarking
    """,
    'author': 'ProcessDrive',
    'website': 'https://www.processdrive.com',
    'license': 'OPL-1',
    'price': 100.00,
    'currency': 'USD',
    'images': ['static/description/banner.png'],
    'depends': ['mail', 'attachment_indexation', 'portal'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sign_data.xml',
        'data/mail_templates.xml',
        'wizard/sign_send_request_wizard_views.xml',
        'wizard/sign_upload_pdf_wizard_views.xml',
        'wizard/sign_template_share_views.xml',
        'wizard/sign_template_sign_now_wizard_views.xml',
        'views/sign_tag_views.xml',
        'views/sign_template_views.xml',
        'views/sign_request_views.xml',
        'views/sign_log_views.xml',
        'views/sign_item_type_views.xml',
        'views/menus.xml',
        'templates/sign_page.xml',
        'templates/template_editor.xml',
    ],
    'application': True,
    'installable': True,
    'assets': {
        'web.assets_backend': [
            'easy_sign/static/src/scss/sign_common.scss',
            'easy_sign/static/src/scss/sign_backend.scss',
            'easy_sign/static/src/js/sign_request_list.js',
            'easy_sign/static/src/js/sign_request_kanban.js',
            'easy_sign/static/src/xml/sign_request_buttons.xml',
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
