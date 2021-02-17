# -*- coding: utf-8 -*-

from odoo import models, fields, api
import requests
import json
import base64
from odoo.exceptions import UserError, ValidationError, AccessError

InvoiceStatus = {
    'BOOKED': 'draft',
    'PENDING': 'draft',
    'PAID': 'posted',
    'EXPIRED': 'cancel',
    'ARCHIVED': 'cancel',
}

TwikeyInvoiceStatus = {
    'draft': 'booked',
    'posted': 'booked',
    'cancel': 'archived',
}


class AccountInvoice(models.Model):
    _inherit = 'account.move'

    twikey_url = fields.Char(string="Twikey Invoice URL")
    twikey_invoice_id = fields.Char(string="Twikey Invoice ID")

    def update_invoice_feed(self):
        authorization_token   = self.env['ir.config_parameter'].sudo().get_param(
            'twikey_integration.authorization_token')
        if authorization_token:
            try:
              response = requests.get("https://api.beta.twikey.com/creditor/invoice?include=customer&include=meta",
                                    headers={'authorization': authorization_token})
              resp_obj = json.loads(response.text)
              if response.status_code == 200:
                  if resp_obj.get('Invoices') and resp_obj.get('Invoices')[0] and resp_obj.get('Invoices')[0] != []:
                      for data in resp_obj.get('Invoices'):
                          if data.get('customer'):
                              customer_id = data.get('customer')
                              country_id = self.env['res.country'].search(
                                  [('code', '=', customer_id.get('country'))])
                              if customer_id.get('companyName') and customer_id.get('companyName') != '':
                                  customer_name = customer_id.get('companyName')
                                  company_type = 'company'
                              else:
                                  customer_name = str(customer_id.get(
                                      'firstname') + customer_id.get('lastname'))
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
                                  partner_id = self.env['res.partner'].search(
                                      [('twikey_reference', '=', customer_id.get('customerNumber'))])
                                  if partner_id:
                                      partner_id.write(values)
                                  else:
                                      partner_id = self.env['res.partner'].create(
                                          values)
                              else:
                                  partner_id = self.env['res.partner'].create(values)
                          invoice_id = self.env['account.move'].search(
                              [('twikey_invoice_id', '=', data.get('id'))])
                          if not invoice_id:
                              invoice_id = self.env['account.move'].create({'twikey_invoice_id': data.get('id'),
                                                                            'name': data.get('title'),
                                                                            'partner_id': partner_id.id,
                                                                            'invoice_date_due': data.get('duedate'),
                                                                            'invoice_date': data.get('date'),
                                                                            'amount_total': data.get('amount'),
                                                                            'twikey_url': data.get('url'),
                                                                            'state': InvoiceStatus[data.get('state')]
                                                                            })
                              if invoice_id:
                                  invoice_account = self.env['account.account'].search(
                                      [('user_type_id', '=', self.env.ref('account.data_account_type_receivable').id)], limit=1).id
                                  invoice_lines = self.env['account.move.line'].create({'product_id': self.env.ref('twikey_integration.product_product_twikey_invoice').id,
                                                                                        'quantity': 1.0,
                                                                                        'price_unit': data.get('amount'),
                                                                                        'move_id': invoice_id.id,
                                                                                        'name': 'Twikey Invoice Product',
                                                                                        'account_id': invoice_account,
                                                                                        })

                          if data.get('state') == 'PAID' and invoice_id.state != 'posted':
                              invoice_id.action_post()
                              inv_ref = invoice_id._get_invoice_computed_reference()
                              if invoice_id.state == 'draft':
                                  journal_id = self.env['account.journal'].search(
                                      [('type', '=', 'bank')],limit=1)
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
                                                                                   'date': fields.Date.context_today(self),
                                                                                   'ref': inv_ref
                                                                                  
                                                                                   })
                                  payment_id.action_post()
                                  credit_aml_id = self.env['account.move.line'].search(
                                      [('payment_id', '=', payment_id.id), ('credit', '!=', 0)])
                                  if credit_aml_id:
                                      invoice_id.js_assign_outstanding_line(
                                          credit_aml_id.id)
                              invoice_id.write({'name': data.get('number'),
                                                'partner_id': partner_id.id,
                                                'invoice_date_due': data.get('duedate'),
                                                'invoice_date': data.get('date'),
                                                'payment_reference': inv_ref if inv_ref else '',
                                                'amount_total': data.get('amount'),
                                                'twikey_url': data.get('url'),
                                                'state': InvoiceStatus[data.get('state')],
                                                'payment_state': 'paid'
                                                })
              
            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                raise exceptions.AccessError(
                    _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                )

    def write(self, values):
        res = super(AccountInvoice, self).write(values)
        authorization_token = self.env['ir.config_parameter'].sudo().get_param(
            'twikey_integration.authorization_token')
        if authorization_token:
          for rec in self:
              if rec.twikey_invoice_id:
                  pdf = self.env.ref(
                      'account.account_invoices')._render_qweb_pdf([rec.id])[0]
                  report_file = base64.b64encode(pdf)
                  report_file_decode = report_file.decode('utf-8')
                  data = """{"title" : "INV_%(Title)s",
                             "date" : "%(InvoiceDate)s",
                             "duedate" : "%(DueDate)s",
                             "pdf" : "%(ReportFile)s" 
                      }""" % {'Title': rec.id,
                              'InvoiceDate': values.get('invoice_date') if values.get('invoice_date') else rec.invoice_date,
                              'DueDate': values.get('invoice_date_due') if values.get('invoice_date_due') else rec.invoice_date_due,
                              'ReportFile': report_file_decode,
                              }
                  try:
                    response = requests.put('https://api.beta.twikey.com/creditor/invoice/%s' % rec.twikey_invoice_id,
                                            data=data, headers={'authorization': authorization_token, 'Content-Type': 'application/json'})
                    resp_obj = json.loads(response.text)
                  except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                      raise exceptions.AccessError(
                          _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                      )
        return res

    def js_assign_outstanding_line(self, line_id):
        res = super(AccountInvoice, self).js_assign_outstanding_line(line_id)
        if self.payment_state == "paid":
            authorization_token = self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.authorization_token')
            if authorization_token:
              pdf = self.env.ref(
                  'account.account_invoices')._render_qweb_pdf([self.id])[0]
              report_file = base64.b64encode(pdf)
              report_file_decode = report_file.decode('utf-8')
              data = """{"title" : "INV_%(Title)s",
                         "date" : "%(InvoiceDate)s",
                         "duedate" : "%(DueDate)s",
                         "pdf" : "%(ReportFile)s",
                         "status" : "%(state)s" 
                  }""" % {'Title': self.id,
                          'InvoiceDate': self.invoice_date,
                          'DueDate': self.invoice_date_due,
                          'ReportFile': report_file_decode,
                          'state': "paid"
                          }
              try:
                response = requests.put('https://api.beta.twikey.com/creditor/invoice/%s' % self.twikey_invoice_id,
                                        data=data, headers={'authorization': authorization_token, 'Content-Type': 'application/json'})
                resp_obj = json.loads(response.text)
              except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                  raise exceptions.AccessError(
                      _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                  )              
        return res

   

class AccountPayment(models.TransientModel):
    _inherit = 'account.payment.register'



    def action_create_payments(self):
        res = super(AccountPayment, self).action_create_payments()
        for rec in self:
            invoice_id = self.env['account.move'].search([('id','=',self.env.context.get('active_id'))])
            if invoice_id:
                if invoice_id.payment_state == "paid":
                    authorization_token = self.env['ir.config_parameter'].sudo().get_param(
                        'twikey_integration.authorization_token')
                    if authorization_token:
                      pdf = self.env.ref(
                          'account.account_invoices')._render_qweb_pdf([invoice_id.id])[0]
                      report_file = base64.b64encode(pdf)
                      report_file_decode = report_file.decode('utf-8')
                      data = """{"title" : "INV_%(Title)s",
                         "date" : "%(InvoiceDate)s",
                         "duedate" : "%(DueDate)s",
                         "pdf" : "%(ReportFile)s",
                         "status" : "%(state)s" 
                  }""" % {'Title': invoice_id.id,
                          'InvoiceDate': invoice_id.invoice_date,
                          'DueDate': invoice_id.invoice_date_due,
                          'ReportFile': report_file_decode,
                          'state': "paid"
                          }
                      try:
                        response = requests.put('https://api.beta.twikey.com/creditor/invoice/%s' % invoice_id.twikey_invoice_id,
                                                data=data, headers={'authorization': authorization_token, 'Content-Type': 'application/json'})
                        resp_obj = json.loads(response.text)
                      except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                        raise exceptions.AccessError(
                            _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                        )                       
        return res
