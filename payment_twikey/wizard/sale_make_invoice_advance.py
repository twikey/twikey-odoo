from odoo import fields, models


class SaleAdvancePaymentInv(models.TransientModel):
    _name = "sale.advance.payment.inv"
    _inherit = "sale.advance.payment.inv"

    twikey_template_id = fields.Many2one("twikey.contract.template", string="Twikey Profile")
    auto_collect_invoice = fields.Boolean(string="Auto collect the invoice",
                                          default=lambda self: self._default_auto_collect)
    send_to_twikey = fields.Boolean(string="Send to Twikey",
                                    default=lambda self: self._default_twikey_send)

    def create_invoices(self):
        context = dict(self._context)
        context.update(
            {
                "twikey_template_id": self.twikey_template_id.id,
                "send_to_twikey": self.send_to_twikey,
                "auto_collect_invoice": self.auto_collect_invoice,
            }
        )
        return super(SaleAdvancePaymentInv, self.with_context(**context)).create_invoices()

    def get_default(self, key, _default):
        cfg = self.env['ir.config_parameter'].sudo()
        return cfg.get_param(key, _default)

    def _default_twikey_send(self):
        return bool(self.get_default("twikey.send.invoice", True))

    def _default_auto_collect(self):
        return bool(self.get_default("twikey.auto_collect", True))
