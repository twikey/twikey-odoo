# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.multi
    def _prepare_invoice(self):
        """
        Prepare the dict of values to create the new invoice for a sales order. This method may be
        overridden to implement custom invoice generation (making sure to call super() to establish
        a clean extension chain).
        """
        context = self._context
        if 'template_id' in context:
            template_id = context.get('template_id')
            self.ensure_one()
            company_id = self.company_id.id
            journal_id = (self.env['account.invoice'].with_context(company_id=company_id or self.env.user.company_id.id)
                .default_get(['journal_id'])['journal_id'])
            if not journal_id:
                raise UserError(_('Please define an accounting sales journal for this company.'))
            vinvoice = self.env['account.invoice'].new({'partner_id': self.partner_invoice_id.id, 'type': 'out_invoice'})
            # Get partner extra fields
            vinvoice._onchange_partner_id()
            invoice_vals = vinvoice._convert_to_write(vinvoice._cache)
            invoice_vals.update({
                'name': (self.client_order_ref or '')[:2000],
                'template_id' : template_id.id,
                'origin': self.name,
                'type': 'out_invoice',
                'account_id': self.partner_invoice_id.property_account_receivable_id.id,
                'partner_shipping_id': self.partner_shipping_id.id,
                'journal_id': journal_id,
                'currency_id': self.pricelist_id.currency_id.id,
                'comment': self.note,
                'payment_term_id': self.payment_term_id.id,
                'fiscal_position_id': self.fiscal_position_id.id or self.partner_invoice_id.property_account_position_id.id,
                'company_id': company_id,
                'user_id': self.user_id and self.user_id.id,
                'team_id': self.team_id.id,
                'transaction_ids': [(6, 0, self.transaction_ids.ids)],
            })
            return invoice_vals
        else:
            return super(SaleOrder, self)._prepare_invoice()