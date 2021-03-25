# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions,_
from odoo.exceptions import UserError, ValidationError
import requests
import json
from datetime import datetime
import base64
import random

class SaleAdvancePaymentInv(models.TransientModel):
    _name = 'sale.advance.payment.inv'
    _inherit = 'sale.advance.payment.inv'
    
    template_id = fields.Many2one('contract.template', string="Contract Template")
    is_twikey = fields.Boolean()

    @api.model
    def default_get(self, fields):
        res = super(SaleAdvancePaymentInv, self).default_get(fields)
        module_twikey = self.env['ir.config_parameter'].sudo().get_param(
            'twikey_integration.module_twikey')
        if module_twikey:
            res.update({'is_twikey': True})
        else:
            res.update({'is_twikey': False})
        return res
    
    @api.multi
    def _create_invoice(self, order, so_line, amount):
        print ("\n\n\n\n\n >>>>>>>>>_create_invoice>>>>>>>>", order, so_line, amount)
        inv_obj = self.env['account.invoice']
        ir_property_obj = self.env['ir.property']

        account_id = False
        if self.product_id.id:
            account_id = order.fiscal_position_id.map_account(self.product_id.property_account_income_id or self.product_id.categ_id.property_account_income_categ_id).id
        if not account_id:
            inc_acc = ir_property_obj.get('property_account_income_categ_id', 'product.category')
            account_id = order.fiscal_position_id.map_account(inc_acc).id if inc_acc else False
        if not account_id:
            raise UserError(
                _('There is no income account defined for this product: "%s". You may have to install a chart of account from Accounting app, settings menu.') %
                (self.product_id.name,))

        if self.amount <= 0.00:
            raise UserError(_('The value of the down payment amount must be positive.'))
        context = {'lang': order.partner_id.lang}
        if self.advance_payment_method == 'percentage':
            amount = order.amount_untaxed * self.amount / 100
            name = _("Down payment of %s%%") % (self.amount,)
        else:
            amount = self.amount
            name = _('Down Payment')
        del context
        taxes = self.product_id.taxes_id.filtered(lambda r: not order.company_id or r.company_id == order.company_id)
        if order.fiscal_position_id and taxes:
            tax_ids = order.fiscal_position_id.map_tax(taxes, self.product_id, order.partner_shipping_id).ids
        else:
            tax_ids = taxes.ids

        invoice = inv_obj.create({
            'name': order.client_order_ref or order.name,
            'origin': order.name,
            'template_id' : self.template_id.id,
            'type': 'out_invoice',
            'reference': False,
            'account_id': order.partner_id.property_account_receivable_id.id,
            'partner_id': order.partner_invoice_id.id,
            'partner_shipping_id': order.partner_shipping_id.id,
            'invoice_line_ids': [(0, 0, {
                'name': name,
                'origin': order.name,
                'account_id': account_id,
                'price_unit': amount,
                'quantity': 1.0,
                'discount': 0.0,
                'uom_id': self.product_id.uom_id.id,
                'product_id': self.product_id.id,
                'sale_line_ids': [(6, 0, [so_line.id])],
                'invoice_line_tax_ids': [(6, 0, tax_ids)],
                'analytic_tag_ids': [(6, 0, so_line.analytic_tag_ids.ids)],
                'account_analytic_id': order.analytic_account_id.id or False,
            })],
            'currency_id': order.pricelist_id.currency_id.id,
            'payment_term_id': order.payment_term_id.id,
            'fiscal_position_id': order.fiscal_position_id.id or order.partner_id.property_account_position_id.id,
            'team_id': order.team_id.id,
            'user_id': order.user_id.id,
            'company_id': order.company_id.id,
            'comment': order.note,
        })
        invoice.compute_taxes()
        invoice.message_post_with_view('mail.message_origin_link',
                    values={'self': invoice, 'origin': order},
                    subtype_id=self.env.ref('mail.mt_note').id)
        return invoice
    
    @api.multi
    def create_invoices(self):
        module_twikey = self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.module_twikey')
        if module_twikey:
            authorization_token=self.env['ir.config_parameter'].sudo().get_param(
                    'twikey_integration.authorization_token')
            base_url=self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.base_url')
            if authorization_token:
                context = dict(self._context)
                context.update({'template_id' : self.template_id})
                sale_orders = self.env['sale.order'].browse(self._context.get('active_ids', []))
                if self.advance_payment_method == 'delivered':
                    sale_orders.with_context(context).action_invoice_create()
                elif self.advance_payment_method == 'all':
                    sale_orders.with_context(context).action_invoice_create(final=True)
                else:
                    res = super(SaleAdvancePaymentInv, self).create_invoices()
                invoice_ids = []
                try:
                    response = requests.get(base_url+"/creditor/template", headers={'Authorization' : authorization_token})
                    if response.status_code == 200:
                        resp_obj = response.json()
                        for resp in resp_obj:
                            template_id = self.env['contract.template'].search([('template_id', '=', resp.get('id'))])
                            if not template_id:
                                template_id = self.env['contract.template'].create({'template_id' : resp.get('id'), 'name' : resp.get('name'), 'active' : resp.get('active'), 'type' : resp.get('type')})
                except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                            raise exceptions.AccessError(
                                _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                            )
                for sale_id in sale_orders:
                    invoice_id = self.env['account.invoice'].search([('id', '=', sale_id.invoice_ids[-1].id)])
                if invoice_id:
                    invoice_id.date_invoice = fields.Date.context_today(self)
                    invoice_id._onchange_payment_term_date_invoice()
                    invoice_number = random.sample(range(10000000,99999999),1)
                    data = """{
                                "number" : "%(id)s",
                                "title" : "INV_%(id)s",
                                "ct" : %(Template)s,
                                "amount" : %(Amount)s,
                                "remittance": "INV_%(id)s",
                                "date" : "%(InvoiceDate)s",
                                "duedate" : "%(DueDate)s",
                                "customerByRef" : "%(CustomerByRef)s"
                                }""" % {'id' : invoice_number[0],
                                        'Template' : self.template_id.template_id,
                                        'Amount' : invoice_id.amount_total,
                                        'InvoiceDate' : fields.Date.context_today(self),
                                        'DueDate' : invoice_id.date_due if invoice_id.date_due else fields.Date.context_today(self),
                                        'CustomerByRef' : invoice_id.partner_id.id
                                    }
                    try:
                        response = requests.post(base_url+"/creditor/invoice", data=data, headers={'authorization' : authorization_token})
                        resp_obj = response.json()
                        if response.status_code == 400 and resp_obj.get('message') and resp_obj.get('message') == 'Debtor was not found':
                            partner_name = invoice_id.partner_id.name.split(' ')
                            data = """{
                                    "number" : "%(id)s",
                                    "title" : "INV_%(id)s",
                                    "ct" : %(Template)s,
                                    "amount" : %(Amount)s,
                                    "date" : "%(InvoiceDate)s",
                                    "duedate" : "%(DueDate)s",
                                    "customer": {"customerNumber" : "%(CustomerNumber)s",
                                     "email" : "%(Email)s",
                                     "firstname" : "%(FirstName)s",
                                     "lastname" : "%(LastName)s",
                                     "companyName" : "%(CompanyName)s",
                                     "coc" : "%(Coc)s",
                                     "address" : "%(Address)s",
                                     "city" : "%(City)s",
                                     "zip" : "%(Zip)s",
                                     "country" : "%(Country)s",
                                     "mobile" : "%(Mobile)s"
                                    }
                            }""" % {'id' : invoice_number[0],
                                    'Template' : self.template_id.template_id,
                                    'Amount' : invoice_id.amount_total,
                                    'InvoiceDate' : fields.Date.context_today(self),
                                    'DueDate' : invoice_id.date_due if invoice_id.date_due else fields.Date.context_today(self),
                                    'CustomerNumber' : invoice_id.partner_id.id if invoice_id.partner_id else '',
                                    'Email' : invoice_id.partner_id.email if invoice_id.partner_id.email else '',
                                    'FirstName' : partner_name[0] if partner_name and invoice_id.partner_id.company_type == 'person' else 'unknown',
                                    'LastName' : partner_name[1] if partner_name and len(partner_name) > 1 and invoice_id.partner_id.company_type == 'person' else 'unknown',
                                    'CompanyName' : invoice_id.partner_id.name if invoice_id.partner_id and invoice_id.partner_id.name and invoice_id.partner_id.company_type == 'company' else '',
                                    'Coc' : invoice_id.partner_id.vat if invoice_id.partner_id and invoice_id.partner_id.vat and invoice_id.partner_id.company_type == 'company' else '',
                                    'Address' : invoice_id.partner_id.street if invoice_id.partner_id and invoice_id.partner_id.street else '',
                                    'City' : invoice_id.partner_id.city if invoice_id.partner_id and invoice_id.partner_id.city else '',
                                    'Zip' : invoice_id.partner_id.zip if invoice_id.partner_id and invoice_id.partner_id.zip else '',
                                    'Country' : invoice_id.partner_id.country_id.code if invoice_id.partner_id and invoice_id.partner_id.country_id else '',
                                    'Mobile' : invoice_id.partner_id.mobile if invoice_id.partner_id.mobile else invoice_id.partner_id.phone if invoice_id.partner_id.phone else ''
                                }
                            try:
                                response = requests.post(base_url+"/creditor/invoice", data=data, headers={'authorization' : authorization_token})
                            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                                raise exceptions.AccessError(
                                    _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                                )
                        if response.status_code == 200:
                            invoice_id.write({'twikey_url' : resp_obj.get('url'), 'twikey_invoice_id' : resp_obj.get('id')})
        #                 update invoice API
                            pdf = self.env.ref('account.account_invoices').render_qweb_pdf([invoice_id.id])[0]
                            report_file = base64.b64encode(pdf)
                            report_file_decode = report_file.decode('utf-8')
                            data = """{"title" : "INV_%(Title)s",
                                       "date" : "%(InvoiceDate)s",
                                       "duedate" : "%(DueDate)s",
                                       "status" : "booked",
                                       "pdf" : "%(ReportFile)s"
                                }""" % {'Title' : invoice_number[0],
                                        'InvoiceDate' : fields.Date.context_today(self),
                                        'DueDate' : invoice_id.date_due if invoice_id.date_due else fields.Date.context_today(self),
                                        'ReportFile' : report_file_decode
                                        }
                            try:
                                update_response = requests.put(base_url+"/creditor/invoice/"+resp_obj.get('id'), data=data, headers={'authorization' : authorization_token, 'Content-Type': 'application/json'})
                            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                                raise exceptions.AccessError(
                                    _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                                )
                    except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                        raise exceptions.AccessError(
                            _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                        )
            else:
                raise UserError(_("Authorization Token Not Found, Please Run Authenticate Twikey Scheduled Actions Manually!!!"))
            if context.get('open_invoices', False):
                    return sale_orders.action_view_invoice()
        else:
            return super(SaleAdvancePaymentInv, self).create_invoices()










