{
    "name": "Easy Sign",
    "version": "18.0.2.0.0",
    "summary": "Self-hosted electronic signature with PDF template editor and field placement",
    "description": """
Easy Sign - Electronic Signature for Odoo 18
=============================================

A complete self-hosted electronic signature solution with:

* PDF Document Templates — upload once, reuse forever
* Visual Template Editor — drag-and-drop fields onto PDF pages
* Field Types: Signature, Initial, Full Name, Date, Email, Text, Checkbox
* Per-signer field assignment (Signer 1 fills their own fields)
* Clients fill the PDF with interactive overlaid widgets
* Signed PDF embeds all values at their exact positions
* Full audit trail with IP addresses and timestamps
* Expiry date support and Decline with reason
    """,
    "category": "Tools/Sign",
    "license": "LGPL-3",
    "depends": ["mail", "web"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "data/mail_template.xml",
        "views/sign_template_views.xml",
        "views/sign_template_send_wizard_views.xml",
        "views/sign_request_views.xml",
        "views/menus.xml",
        "templates/sign_page.xml",
        "templates/template_editor.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "easy-sign/static/src/css/sign_public.css",
            "easy-sign/static/src/js/sign_public.js",
        ],
    },
    "images": [
        "static/description/main_screenshot.png",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
