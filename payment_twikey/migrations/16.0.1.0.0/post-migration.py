from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Update code of noupdate cron record."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.ref("payment_twikey.twikey_invoice_sender").write({
        "code": "model.send_invoices(cron=True)",
    })
