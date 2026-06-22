# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import base64

class SignUploadPdfWizard(models.TransientModel):
    _name = 'sign.upload.pdf.wizard'
    _description = 'Upload PDF to Sign'

    # We can also just use a Binary field if we prefer creating the attachment on the fly,
    # but ir.attachment is easier with Odoo's standard binary widget
    file = fields.Binary(string="File", required=True, attachment=False)
    name = fields.Char(string="Filename")

    def action_upload_pdf(self):
        self.ensure_one()
        if not self.file:
            raise UserError(_("Please upload a PDF file."))
        
        # Create ir.attachment manually
        attachment = self.env['ir.attachment'].create({
            'name': self.name or 'Uploaded Document',
            'datas': self.file,
            'mimetype': 'application/pdf',
        })

        # Create a new sign.template
        template = self.env['sign.template'].create({
            'name': self.name or 'Uploaded Document',
            'attachment_id': attachment.id,
        })
        
        # Call the existing method to go to the template editor
        return template.go_to_custom_template()
