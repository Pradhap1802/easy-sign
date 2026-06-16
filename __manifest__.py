{
    "name": "Easy Sign - Electronic Signature",
    "version": "18.0.1.0.0",
    "summary": "Self-hosted electronic signature: send PDF documents for signing directly from Odoo",
    "description": """
Easy Sign - Electronic Signature for Odoo 18
=============================================

A complete self-hosted electronic signature solution that works 100% inside Odoo
with no external APIs or third-party services required.

Features:
---------
* Upload PDF documents and add signers (name + email)
* Odoo sends each signer a unique signing link via email
* Signers open the link without needing an Odoo account
* Draw signatures on a canvas (mouse and touch support)
* Automatic signed document creation after all parties sign
* Full audit trail with IP addresses and timestamps
* Expiry date support
* Decline with reason support
* Mobile responsive signing page
    """,
    "category": "Tools/Sign",
    "author": "Ahmed Kamal",
    "website": "https://www.linkedin.com/in/ahmed-kamal-97569316b/",
    "license": "LGPL-3",
    "depends": ["mail", "web"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "data/mail_template.xml",
        "templates/sign_page.xml",
        "views/sign_request_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "easy_sign/static/src/css/sign_public.css",
            "easy_sign/static/src/js/sign_public.js",
        ],
    },
    "images": [
        "static/description/main_screenshot.png",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
