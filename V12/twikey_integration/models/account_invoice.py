# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions,_
import requests
import json
import base64
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

InvoiceStatus = {
    'BOOKED': 'draft',
    'PENDING': 'open',
    'PAID': 'paid',
    'EXPIRED': 'cancel',
    'ARCHIVED': 'cancel'
}

TwikeyInvoiceStatus = {
    'draft': 'booked',
    'open': 'booked',
    'in_payment': 'booked',
    'paid': 'paid',
    'cancel': 'archived'
}


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    twikey_url = fields.Char(string="Twikey Invoice URL",
                             help="URL of the Twikey Invoice")
    twikey_invoice_id = fields.Char(
        string="Twikey Invoice ID", help="Invoice ID of Twikey.")
    template_id = fields.Many2one('contract.template', string="Contract Template")
    is_twikey = fields.Boolean(compute='compute_twikey')

    def compute_twikey(self):
        module_twikey = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.module_twikey')
        if module_twikey:
            self.update({'is_twikey': True})
        else:
            self.update({'is_twikey': False})

    def update_invoice_feed(self):
        authorization_token = self.env['ir.config_parameter'].sudo().get_param(
            'twikey_integration.authorization_token')
        base_url=self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.base_url')
        if authorization_token:
            try:
                response = requests.get(base_url+"/creditor/invoice?include=customer&include=meta", headers={'authorization' : authorization_token})
                _logger.info('Fetching Invoices from Twikey %s' % (response.content))
                resp_obj = response.json()
                if response.status_code == 200:
                    if resp_obj.get('Invoices') and resp_obj.get('Invoices')[0] and resp_obj.get('Invoices')[0] != []:
                        for data in resp_obj.get('Invoices'):
                            if data.get('customer'):
                                customer_id = data.get('customer')
                                country_id = self.env['res.country'].search([('code', '=', customer_id.get('country'))])
                                if customer_id.get('companyName') and customer_id.get('companyName') != '':
                                    customer_name = customer_id.get('companyName')
                                    company_type = 'company'
                                else:
                                    customer_name = str(customer_id.get('firstname') + customer_id.get('lastname'))
                                    company_type = 'person'
                                values = {'name': customer_name,
                                          'company_type': company_type,
                                          'email': customer_id.get('email'),
                                          'street': customer_id.get('address'),
                                          'city': customer_id.get('city'),
                                          'zip': customer_id.get('zip'),
                                          'country_id': country_id.id,
                                          'mobile': customer_id.get('mobile'),
                                          'twikey_reference': customer_id.get('customerNumber')
                                          }
                                if customer_id.get('customerNumber') and customer_id.get('customerNumber') != None:
                                    partner_id = self.env['res.partner'].search([('twikey_reference', '=', customer_id.get('customerNumber'))])
                                    if partner_id:
                                        partner_id.write(values)
                                    else:
                                        partner_id = self.env['res.partner'].create(values)
                                else:
                                    partner_id = self.env['res.partner'].create(values)
                                    
                            invoice_id = self.env['account.invoice'].search([('twikey_invoice_id', '=', data.get('id'))])
                            if not invoice_id:
                                invoice_id = self.env['account.invoice'].create({'twikey_invoice_id': data.get('id'),
                                                                                 'number': data.get('title'),
                                                                                 'partner_id': partner_id.id,
                                                                                 'date_due': data.get('duedate'),
                                                                                 'date_invoice': data.get('date'),
                                                                                 'amount_total': data.get('amount'),
                                                                                 'twikey_url': data.get('url'),
                                                                                 'state': InvoiceStatus[data.get('state')]
                                                                                 })
                                if invoice_id:
                                    invoice_account = self.env['account.account'].search([('user_type_id', '=', self.env.ref('account.data_account_type_receivable').id)], limit=1).id
                                    invoice_lines = self.env['account.invoice.line'].create({'product_id': self.env.ref('twikey_integration.product_product_twikey_invoice').id,
                                                                                             'quantity': 1.0,
                                                                                             'price_unit': data.get('amount'),
                                                                                             'invoice_id': invoice_id.id,
                                                                                             'name': 'Twikey Invoice Product',
                                                                                             'account_id': invoice_account,
                                                                                             })
                            inv_ref = ''
                            if data.get('state') == 'PAID' and invoice_id.state != 'paid':
                                if invoice_id.state == 'draft':
                                    invoice_id.action_invoice_open()
                                if invoice_id.state == 'open':
                                    inv_ref = invoice_id._get_computed_reference()
                                    journal_id = self.env['account.journal'].search(
                                        [('type', '=', 'bank')], limit=1)
                                    payment_method = self.env.ref(
                                        'account.account_payment_method_manual_in')
                                    journal_payment_methods = journal_id.inbound_payment_method_ids
                                    payment_id = self.env['account.payment'].create({'amount': invoice_id.amount_total,
                                                                                     'journal_id': journal_id.id,
                                                                                     'state': 'draft',
                                                                                     'payment_type': 'inbound',
                                                                                     'partner_type': 'customer',
                                                                                     'payment_method_id': journal_payment_methods.id,
                                                                                     'partner_id': partner_id.id,
                                                                                     'payment_date': fields.Date.context_today(self),
                                                                                     'communication': inv_ref
                                                                                     })
                                    payment_id.post()
                                    credit_aml_id = self.env['account.move.line'].search([('payment_id', '=', payment_id.id), ('credit', '!=', 0)])
                                    if credit_aml_id:
                                        invoice_id.assign_outstanding_credit(
                                            credit_aml_id.id)
                            invoice_id.with_context(update_invoice=True).write({'number': data.get('number'),
                                              'partner_id': partner_id.id,
                                              'date_due': data.get('duedate'),
                                              'date_invoice': data.get('date'),
                                              'reference': inv_ref if inv_ref else '',
                                              'amount_total': data.get('amount'),
                                              'twikey_url': data.get('url'),
                                              'state': InvoiceStatus[data.get('state')]
                                              })
            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                _logger.info('Exception raised while fetching Invoice data from Twikey %s' % (e))
                raise exceptions.AccessError(
                    _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                )

    def sync_invoice(self):
        authorization_token = self.env['ir.config_parameter'].sudo().get_param(
            'twikey_integration.authorization_token')
        base_url=self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.base_url')
        if authorization_token and self.twikey_invoice_id:
            try:
                response = requests.get(base_url+"/creditor/invoice/"+self.twikey_invoice_id+"?include=customer", headers={'authorization' : authorization_token})
                _logger.info('Fetching Invoice Data from Twikey.. %s' % (response.content))
                if response.status_code == 200:
                    resp_obj = response.json()
                    if resp_obj.get('customer'):
                        customer_id = resp_obj.get('customer')
                        country_id = self.env['res.country'].search([('code', '=', customer_id.get('country'))])
                        if customer_id.get('companyName') and customer_id.get('companyName') != '':
                            customer_name = customer_id.get('companyName')
                            company_type = 'company'
                        else:
                            customer_name = str(customer_id.get('firstname') + customer_id.get('lastname'))
                            company_type = 'person'
                        values = {'name': customer_name,
                                  'company_type': company_type,
                                  'email': customer_id.get('email'),
                                  'street': customer_id.get('address'),
                                  'city': customer_id.get('city'),
                                  'zip': customer_id.get('zip'),
                                  'country_id': country_id.id,
                                  'mobile': customer_id.get('mobile'),
                                  'twikey_reference': customer_id.get('customerNumber')
                                  }
                        if customer_id.get('customerNumber') and customer_id.get('customerNumber') != None:
                            partner_id = self.env['res.partner'].search([('twikey_reference', '=', customer_id.get('customerNumber'))])
                            if partner_id:
                                partner_id.write(values)
                            else:
                                partner_id = self.env['res.partner'].create(values)
                        else:
                            partner_id = self.env['res.partner'].create(values)
                    
                    self.write({'number': resp_obj.get('number'),
                                  'partner_id': partner_id.id if partner_id else False,
                                  'date_due': resp_obj.get('duedate'),
                                  'date_invoice': resp_obj.get('date'),
                                  'amount_total': resp_obj.get('amount'),
                                  'twikey_url': resp_obj.get('url'),
                                  'state': InvoiceStatus[resp_obj.get('state')]
                                      })
            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                _logger.info('Exception raised while syncing Invoice %s' % (e))
                raise exceptions.AccessError(
                    _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                )
            pdf = self.env.ref('account.account_invoices').render_qweb_pdf([self.id])[0]
            report_file = base64.b64encode(pdf)
            report_file_decode = report_file.decode('utf-8')
            data = """{"date" : "%(InvoiceDate)s",
                       "duedate" : "%(DueDate)s",
                       "pdf" : "%(ReportFile)s"
            }""" % {'InvoiceDate': self.date_invoice if self.date_invoice else '',
                    'DueDate': self.date_due if self.date_due else '',
                    'ReportFile': report_file_decode
                    }
            try:
                response = requests.put(base_url+'/creditor/invoice/%s' %self.twikey_invoice_id, data=data, headers={'authorization' : authorization_token, 'Content-Type': 'application/json'})
                _logger.info('Updating pdf to invoice %s' % (response.content))
#                 if response.status_code != 200:
#                     resp_obj = response.json()
#                     raise UserError(_('%s')
#                                 % (resp_obj.get('message')))
            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                _logger.info('Exception raised while updating pdf to invoice %s' % (e))
                raise exceptions.AccessError(
                    _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                )


    @api.multi
    def write(self, values):
        print('==============write================')
        context = self._context
        res = super(AccountInvoice, self).write(values)
        if not 'update_feed' in context and not 'by_controller' in context and not 'update_invoice' in context:
            authorization_token = self.env['ir.config_parameter'].sudo().get_param(
                            'twikey_integration.authorization_token')
            base_url=self.env['ir.config_parameter'].sudo().get_param(
                        'twikey_integration.base_url')
            self.update_invoice_feed()
            if authorization_token:
                for rec in self:
                    if rec.twikey_invoice_id and values.get('state') == 'paid':
                        pdf = self.env.ref('account.account_invoices').render_qweb_pdf([rec.id])[0]
                        report_file = base64.b64encode(pdf)
                        report_file_decode = report_file.decode('utf-8')
                        data = """{"date" : "%(InvoiceDate)s",
                               "duedate" : "%(DueDate)s",
                               "status" : "%(InvoiceStatus)s",
                               "pdf" : "%(ReportFile)s"
                        }""" % {'InvoiceDate': values.get('date_invoice') if values.get('date_invoice') else rec.date_invoice,
                                'DueDate': values.get('date_due') if values.get('date_due') else rec.date_due,
                                'InvoiceStatus': TwikeyInvoiceStatus[values.get('state')] if values.get('state') else TwikeyInvoiceStatus[rec.state],
                                'ReportFile': report_file_decode
                                }
                        try:
                            response = requests.put(base_url+'/creditor/invoice/%s' %rec.twikey_invoice_id, data=data, headers={'authorization' : authorization_token, 'Content-Type': 'application/json'})
                            _logger.info('Updating invoice data to twikey %s' % (response.content))
    #                         if response.status_code != 200:
    #                             resp_obj = response.json()
    #                             raise UserError(_('%s')
    #                                 % (resp_obj.get('message')))
                        except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                            _logger.info('Exception raised while updating invoice data to Twikey %s' % (e))
                            raise exceptions.AccessError(
                                _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                            )
        return res

    @api.multi
    def action_invoice_re_open(self):
        if self.filtered(lambda inv: inv.state not in ('in_payment', 'paid')):
            raise UserError(_('Invoice must be paid in order to set it to register payment.'))
        if self:
            return self.with_context(by_controller=True).write({'state': 'open'})
