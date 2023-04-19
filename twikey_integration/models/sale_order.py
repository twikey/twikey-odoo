from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _prepare_invoice(self):
        res = super(SaleOrder, self)._prepare_invoice()
        if "template_id" in self._context:
            res["template_id"] = self._context.get("template_id")

        return res
