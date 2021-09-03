# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Twikey Integration',
    'category': 'Payment',
    'summary': 'Twikey Integration',
    'version': '1.0',
    'author': "TechUltra Solutions",
    'website': "https://www.techultrasolutions.com/",
    'description': """ """,
    'depends': ['sale_management', 'account', 'product', 'contacts'],
    'data': [
        'data/schedulers.xml',
        'data/mail_template.xml',
        'data/product_data.xml',
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/res_partner_view.xml',
        'views/contract_template.xml',
        'wizard/wizard_cancel_reason.xml',
        'wizard/success_message_wizard.xml',
        'wizard/contract_template_wizard.xml',
        'wizard/sale_make_invoice_advance.xml',
        'views/mandate_details.xml',
        'views/account_move.xml',
        'report/report_account_invoice.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'OEEL-1',
}
