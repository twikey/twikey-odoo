# -*- coding: utf-8 -*-
from odoo import api, fields, models, exceptions,_
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

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
            # ensure a correct context for the _get_default_journal method and company-dependent fields
            self = self.with_context(default_company_id=self.company_id.id, force_company=self.company_id.id)
            journal = self.env['account.move'].with_context(default_type='out_invoice')._get_default_journal()
            if not journal:
                raise UserError(_('Please define an accounting sales journal for the company %s (%s).') % (self.company_id.name, self.company_id.id))

            invoice_vals = {
                'ref': self.client_order_ref or '',
                'type': 'out_invoice',
                'template_id': template_id.id,
                'narration': self.note,
                'currency_id': self.pricelist_id.currency_id.id,
                'campaign_id': self.campaign_id.id,
                'medium_id': self.medium_id.id,
                'source_id': self.source_id.id,
                'invoice_user_id': self.user_id and self.user_id.id,
                'team_id': self.team_id.id,
                'partner_id': self.partner_invoice_id.id,
                'partner_shipping_id': self.partner_shipping_id.id,
                'invoice_partner_bank_id': self.company_id.partner_id.bank_ids[:1].id,
                'fiscal_position_id': self.fiscal_position_id.id or self.partner_invoice_id.property_account_position_id.id,
                'journal_id': journal.id,  # company comes from the journal
                'invoice_origin': self.name,
                'invoice_payment_term_id': self.payment_term_id.id,
                'invoice_payment_ref': self.reference,
                'transaction_ids': [(6, 0, self.transaction_ids.ids)],
                'invoice_line_ids': [],
                'company_id': self.company_id.id,
            }
            return invoice_vals
        else:
            return super(SaleOrder, self)._prepare_invoice()
