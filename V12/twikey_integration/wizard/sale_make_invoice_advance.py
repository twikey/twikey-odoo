# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions,_
import requests
import json
from datetime import datetime
import base64


class SaleAdvancePaymentInv(models.TransientModel):
    _name = 'sale.advance.payment.inv'
    _inherit = 'sale.advance.payment.inv'
    
    @api.multi
    def create_invoices(self):
        res = super(SaleAdvancePaymentInv, self).create_invoices()
        module_twikey = self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.module_twikey')
        if module_twikey:
            context = self._context
            invoice_ids = []
            if 'active_id' in context:
                sale_id = self.env['sale.order'].browse(context.get('active_id'))
                invoice_id = self.env['account.invoice'].search([('id', '=', sale_id.invoice_ids[-1].id)])
                if invoice_id:
                    authorization_token=self.env['ir.config_parameter'].sudo().get_param(
                            'twikey_integration.authorization_token')
                    invoice_id.date_invoice = fields.Date.context_today(self)
                    invoice_id._onchange_payment_term_date_invoice()
                    invoice_number = random.sample(range(10000000,99999999),1)
                    data = """{
                                "number" : "%(id)s",
                                "title" : "INV_%(id)s",
                                "ct" : 2833,
                                "amount" : %(Amount)s,
                                "remittance": "INV_%(id)s",
                                "date" : "%(InvoiceDate)s",
                                "duedate" : "%(DueDate)s",
                                "customerByRef" : "%(CustomerByRef)s"
                                }""" % {'id' : invoice_number[0],
                                        'Amount' : invoice_id.amount_total,
                                        'InvoiceDate' : fields.Date.context_today(self),
                                        'DueDate' : invoice_id.date_due if invoice_id.date_due else fields.Date.context_today(self),
                                        'CustomerByRef' : invoice_id.partner_id.id
                                    }
                    try:
                        response = requests.post('https://api.beta.twikey.com/creditor/invoice', data=data, headers={'authorization' : authorization_token})
                        if response.status_code == 400 and resp_obj.get('message') and resp_obj.get('message') == 'Debtor was not found':
                            data = """{
                                    "number" : "%(id)s",
                                    "title" : "INVOICE_%(id)s",
                                    "ct" : 2833,
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
                                            'Amount' : invoice_id.amount_total,
                                            'InvoiceDate' : fields.Date.context_today(self),
                                            'DueDate' : invoice_id.date_due if invoice_id.date_due else fields.Date.context_today(self),
                                            'CustomerNumber' : invoice_id.partner_id.id if invoice_id.partner_id else '',
                                            'Email' : invoice_id.partner_id.email if invoice_id.partner_id.email else '',
                                            'FirstName' : invoice_id.partner_id.name.split(' ')[0] if invoice_id.partner_id and invoice_id.partner_id.name and invoice_id.partner_id.company_type == 'person' else 'unknown',
                                            'LastName' : invoice_id.partner_id.name.split(' ')[1] if invoice_id.partner_id and invoice_id.partner_id.name and invoice_id.partner_id.company_type == 'person' else 'unknown',
                                            'CompanyName' : invoice_id.partner_id.name if invoice_id.partner_id and invoice_id.partner_id.name and invoice_id.partner_id.company_type == 'company' else '',
                                            'Coc' : invoice_id.partner_id.vat if invoice_id.partner_id and invoice_id.partner_id.vat and invoice_id.partner_id.company_type == 'company' else '',
                                            'Address' : invoice_id.partner_id.street if invoice_id.partner_id and invoice_id.partner_id.street else '',
                                            'City' : invoice_id.partner_id.city if invoice_id.partner_id and invoice_id.partner_id.city else '',
                                            'Zip' : invoice_id.partner_id.zip if invoice_id.partner_id and invoice_id.partner_id.zip else '',
                                            'Country' : invoice_id.partner_id.country_id.code if invoice_id.partner_id and invoice_id.partner_id.country_id else '',
                                            'Mobile' : invoice_id.partner_id.mobile if invoice_id.partner_id.mobile else invoice_id.partner_id.phone if invoice_id.partner_id.phone else ''
                                        }
                            try:
                                response = requests.post('https://api.beta.twikey.com/creditor/invoice', data=data, headers={'authorization' : authorization_token})
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
                            data = """{"title" : "%(Title)s",
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
                                update_response = requests.put('https://api.beta.twikey.com/creditor/invoice/%s' %resp_obj.get('id'), data=data, headers={'authorization' : authorization_token, 'Content-Type': 'application/json'})
                            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                                raise exceptions.AccessError(
                                    _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                                )
                    except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                        raise exceptions.AccessError(
                            _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                        )
        return res










