# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Twikey Integration",
    "category": "Accounting",
    "summary": "Twikey Integration",
    "version": "14.0.1.0.0",
    "author": "Twikey N.V., DynApps NV",
    "website": "https://www.dynapps.be",
    "depends": [
        "account",
        "account_accountant",
        "account_check_printing",
        "contacts",
        "mail",
        "product",
        "sale",
        "sale_management",
        "stock",
        "web_notify",
    ],
    "data": [
        "data/schedulers.xml",
        "data/mail_template.xml",
        "data/product_data.xml",
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/res_partner_view.xml",
        "views/contract_template.xml",
        "wizard/wizard_cancel_reason.xml",
        "wizard/success_message_wizard.xml",
        "wizard/twikey_contract_template_wizard.xml",
        "wizard/sale_make_invoice_advance.xml",
        "views/mandate_details.xml",
        "views/account_move.xml",
        "views/account_journal.xml",
        "report/report_account_invoice.xml",
    ],
    "installable": True,
    "images": ["static/description/icon.png"],
    "auto_install": False,
    "license": "OPL-1",
}
