# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions,_
from odoo.exceptions import UserError, ValidationError
import requests
import base64
import logging
import uuid

_logger = logging.getLogger(__name__)

class SaleAdvancePaymentInv(models.TransientModel):

    _name = 'sale.advance.payment.inv'
    _inherit = 'sale.advance.payment.inv'
    
    template_id = fields.Many2one('twikey.contract.template', string="Contract Template")
    is_twikey = fields.Boolean()

    @api.model
    def default_get(self, fields):
        res = super(SaleAdvancePaymentInv, self).default_get(fields)
        module_twikey = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.module_twikey')
        if module_twikey:
            res.update({'is_twikey': True})
        else:
            res.update({'is_twikey': False})
        return res

    def _create_invoice(self, order, so_line, amount):
        if (self.advance_payment_method == 'percentage' and self.amount <= 0.00) or (
                self.advance_payment_method == 'fixed' and self.fixed_amount <= 0.00):
            raise UserError(_('The value of the down payment amount must be positive.'))

        amount, name = self._get_advance_details(order)

        invoice_vals = self._prepare_invoice_values(order, name, amount, so_line)

        if order.fiscal_position_id:
            invoice_vals['fiscal_position_id'] = order.fiscal_position_id.id
        invoice = self.env['account.move'].sudo().create(invoice_vals).with_user(self.env.uid)
        invoice.message_post_with_view('mail.message_origin_link',
                                       values={'self': invoice, 'origin': order},
                                       subtype_id=self.env.ref('mail.mt_note').id)
        return invoice

    def create_invoices(self):
        params = self.env['ir.config_parameter'].sudo()
        module_twikey = params.get_param('twikey_integration.module_twikey')
        # if module_twikey:
        #     authorization_token = params.get_param('twikey_integration.authorization_token')
        #     base_url = params.get_param('twikey_integration.base_url')
        #     merchant_id = params.get_param('twikey_integration.merchant_id')
        #     test_mode = params.get_param('twikey_integration.test')
        #     base_invoice_url = "https://app.twikey.com/"+merchant_id+"/"
        #     if test_mode:
        #         base_invoice_url = "https://app.beta.twikey.com/"+merchant_id+"/"
        #     if authorization_token:
        context = dict(self._context)
        context.update({'template_id' : self.template_id})
        sale_orders = self.env['sale.order'].browse(self._context.get('active_ids', []))
        if self.advance_payment_method == 'delivered':
            sale_orders.with_context(context)._create_invoices()
        elif self.advance_payment_method == 'all':
            sale_orders.with_context(context)._create_invoices(final=True)
        else:
            res = super(SaleAdvancePaymentInv, self).create_invoices()
        for sale_id in sale_orders:
            invoice_id = self.env['account.move'].search([('id', '=', sale_id.invoice_ids[-1].id)])
        if invoice_id:
            if context.get('open_invoices', False):
                    return sale_orders.action_view_invoice()
        else:
            return super(SaleAdvancePaymentInv, self).create_invoices()

