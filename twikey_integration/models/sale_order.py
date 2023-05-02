from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _prepare_invoice(self):
        res = super(SaleOrder, self)._prepare_invoice()
        if "twikey_template_id" in self._context:
            res["twikey_template_id"] = self._context.get("twikey_template_id")
        if "default_send_to_twikey" in self._context:
            res["send_to_twikey"] = self._context.get("default_send_to_twikey")
        if "default_auto_collect_invoice" in self._context:
            res["auto_collect_invoice"] = self._context.get("default_auto_collect_invoice")
        return res
