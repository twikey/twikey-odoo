# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    "name": "Payment Provider: Twikey",
    "version": "18.0.0.0",
    "category": "Accounting/Payment Providers",
    "summary": "focus on recurring payments",
    "author": "Twikey N.V.",
    "website": "https://www.twikey.com/partner/odoo.html",
    "depends": [
        "payment",
        "account",
        "contacts",
        "sale",
    ],
    "data": [
        "views/payment_twikey_templates.xml",
        # Data
        "data/schedulers.xml",
        "data/mail_template.xml",
        "data/product_data.xml",
        "data/payment_provider_data.xml",
        # Reports
        "report/report_account_invoice.xml",
        # Security
        "security/ir.model.access.csv",
        # Views
        "views/res_config_settings_views.xml",
        "views/res_partner_view.xml",
        "views/contract_template.xml",
        "views/payment_views.xml",
        "views/mandate_details.xml",
        "views/account_move.xml",
        # Wizard
        "wizard/wizard_cancel_reason.xml",
        "wizard/twikey_contract_template_wizard.xml",
    ],
    "application": False,
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "images": ["static/description/icon.png"],
    "auto_install": False,
    "license": "LGPL-3",
}
