# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions,_
import requests
import base64
from odoo.exceptions import UserError
import logging
import uuid

_logger = logging.getLogger(__name__)

InvoiceStatus = {
    'BOOKED': 'open',
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

    twikey_url = fields.Char(string="Twikey Invoice URL", help="URL of the Twikey Invoice")
    twikey_invoice_id = fields.Char(string="Twikey Invoice ID", help="Invoice ID of Twikey.")
    template_id = fields.Many2one('contract.template', string="Contract Template")
    is_twikey = fields.Boolean(compute='compute_twikey')

    @api.multi
    def action_invoice_open(self):
        res = super(AccountInvoice, self).action_invoice_open()
        params = self.env['ir.config_parameter'].sudo()
        module_twikey = params.get_param('twikey_integration.module_twikey')
        if module_twikey:
            authorization_token = params.get_param('twikey_integration.authorization_token')
            base_url = params.get_param('twikey_integration.base_url')
            merchant_id = params.get_param('twikey_integration.merchant_id')
            test_mode = params.get_param('twikey_integration.test')
            base_invoice_url = "https://app.twikey.com/" + merchant_id + "/"
            if test_mode:
                base_invoice_url = "https://app.beta.twikey.com/" + merchant_id + "/"
            if authorization_token:
                invoice_id = self
                invoice_number = str(uuid.uuid1())

                url = base_invoice_url + invoice_number
                invoice_id.with_context(update_feed=True).write(
                    {'twikey_url': url, 'twikey_invoice_id': invoice_number})
                pdf = self.env.ref('account.account_invoices').render_qweb_pdf([invoice_id.id])[0]
                report_file = base64.b64encode(pdf)

                sequence = invoice_id.journal_id.sequence_id
                sequence_number = invoice_id.journal_id.sequence_number_next
                print("==========================", sequence_number)
                if not sequence:
                    raise UserError(_('Please define a sequence on your journal.'))

                try:
                    partner_name = invoice_id.partner_id.name.split(' ')
                    data = """{
                            "id" : "%(number)s",
                            "number" : "%(id)s",
                            "title" : "INV_%(id)s",
                            "ct" : %(Template)s,
                            "amount" : %(Amount)s,
                            "date" : "%(InvoiceDate)s",
                            "duedate" : "%(DueDate)s",
                            "pdf": "%(pdf)s",
                            "remittance": "%(Remittance)s",
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
                    }""" % {'id' : sequence_number,
                            'number' : invoice_number,
                            'Template' : self.template_id.template_id,
                            'Amount' : invoice_id.amount_total,
                            'InvoiceDate' : fields.Date.context_today(self),
                            'DueDate' : invoice_id.date_due if invoice_id.date_due else fields.Date.context_today(self),
                            'pdf': report_file.decode('utf-8'),
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
                            'Mobile' : invoice_id.partner_id.mobile if invoice_id.partner_id.mobile else invoice_id.partner_id.phone if invoice_id.partner_id.phone else '',
                            'Remittance': invoice_id.reference,
                        }
                    try:
                        _logger.info('Creating new Invoice %s' % (data))
                        response = requests.post(base_url + "/creditor/invoice", data=data,
                                                 headers={'authorization': authorization_token})
                        _logger.info('Created new invoice %s' % (response.content))
                    except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
                            requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                        raise exceptions.AccessError(
                            _('The url that this service requested returned an error. Please check your connection or try after sometime.'))
                except (
                        ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
                        requests.exceptions.Timeout,
                        requests.exceptions.HTTPError) as e:
                    raise exceptions.AccessError(
                        _('The url that this service requested returned an error. Please check your connection or try after sometime.'))
            else:
                raise UserError(
                    _("Authorization Token Not Found, Please Run Authenticate Twikey Scheduled Actions Manually!!!"))
        return res

    def compute_twikey(self):
        module_twikey = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.module_twikey')
        if module_twikey:
            self.update({'is_twikey': True})
        else:
            self.update({'is_twikey': False})

    def update_invoice_feed(self):
        authorization_token = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.authorization_token')
        base_url = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.base_url')
        if authorization_token:
            try:
                response = requests.get(base_url+"/creditor/invoice?include=customer&include=meta", headers={'authorization' : authorization_token})
                _logger.debug('Fetching Invoices from Twikey %s' % (response.content))
                resp_obj = response.json()
                if response.status_code == 200:
                    if resp_obj.get('Invoices') and resp_obj.get('Invoices')[0] and resp_obj.get('Invoices')[0] != []:
                        _logger.info('Retrieved %d invoices updates' % (len(resp_obj.get('Invoices'))))
                        for data in resp_obj.get('Invoices'):
                            if data.get('customer'):
                                try:
                                    customer_id = data.get('customer')
                                    country_id = self.env['res.country'].search([('code', '=', customer_id.get('country'))])
                                    if customer_id.get('companyName') and customer_id.get('companyName') != '':
                                        customer_name = customer_id.get('companyName')
                                        company_type = 'company'
                                    else:
                                        customer_name = str(customer_id.get('firstname') + " " + customer_id.get('lastname'))
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
                                except (
                                ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
                                requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                                    _logger.error('Error update customer %s' % (e))
                                    raise exceptions.AccessError(_('Something went wrong.'))

                                if customer_id.get('customerNumber') and customer_id.get('customerNumber') != None:
                                    partner_id = self.env['res.partner'].search([('twikey_reference', '=', customer_id.get('customerNumber'))])
                                    if partner_id:
                                        partner_id.with_context(update_feed=True).write(values)
                                    else:
                                        partner_id = self.env['res.partner'].create(values)
                                else:
                                    partner_id = self.env['res.partner'].create(values)
                                    
                            invoice_id = self.env['account.invoice'].search([('twikey_invoice_id', '=', data.get('id'))])
                            if not invoice_id:
                                try:
                                    invoice_id = self.env['account.invoice'].create({'twikey_invoice_id': data.get('id'),
                                                                                 'number': data.get('title'),
                                                                                 'partner_id': partner_id.id,
                                                                                 'date_due': data.get('duedate'),
                                                                                 'date_invoice': data.get('date'),
                                                                                 'amount_total': data.get('amount'),
                                                                                 'twikey_url': data.get('url'),
                                                                                 'state': InvoiceStatus[data.get('state')]
                                                                                 })
                                except (
                                ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
                                requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                                    _logger.error('Error creating invoice in odoo %s' % (e))
                                    raise exceptions.AccessError(_('Something went wrong.'))
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
                                try:
                                    if invoice_id.state == 'draft':
                                        invoice_id.with_context(update_feed=True).action_invoice_open()
                                    if invoice_id.state == 'open':
                                        inv_ref = invoice_id.with_context(update_feed=True)._get_computed_reference()
                                        journal_id = self.env['account.journal'].search([('type', '=', 'bank')], limit=1)
                                        payment_method = self.env.ref('account.account_payment_method_manual_in')
                                        journal_payment_methods = journal_id.inbound_payment_method_ids
                                        payment_id = self.env['account.payment'].with_context(update_feed=True).create({'amount': invoice_id.amount_total,
                                                                                         'journal_id': journal_id.id,
                                                                                         'state': 'draft',
                                                                                         'payment_type': 'inbound',
                                                                                         'partner_type': 'customer',
                                                                                         'payment_method_id': journal_payment_methods.id,
                                                                                         'partner_id': partner_id.id,
                                                                                         'payment_date': fields.Date.context_today(self),
                                                                                         'communication': inv_ref
                                                                                         })
                                        payment_id.with_context(update_feed=True).post()
                                        credit_aml_id = self.env['account.move.line'].search([('payment_id', '=', payment_id.id), ('credit', '!=', 0)])
                                        if credit_aml_id:
                                            invoice_id.with_context(update_feed=True).assign_outstanding_credit(credit_aml_id.id)
                                except (
                                ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
                                requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                                    _logger.error('Error marking invoice as paid in odoo %s' % (e))
                                    raise exceptions.AccessError(_('Something went wrong.')
                                    )
                            invoice_id.with_context(update_feed=True).write({'number': data.get('number'),
                                              'partner_id': partner_id.id,
                                              'date_due': data.get('duedate'),
                                              'date_invoice': data.get('date'),
                                              'reference': inv_ref if inv_ref else '',
                                              'amount_total': data.get('amount'),
                                              'twikey_url': data.get('url'),
                                              'state': InvoiceStatus[data.get('state')]
                                              })
            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                _logger.error('Exception raised while fetching Invoice data from Twikey %s' % (e))
                raise exceptions.AccessError(_('The url that this service requested returned an error. Please check your connection or try after sometime.'))



    @api.multi
    def write(self, values):
        context = self._context
        res = super(AccountInvoice, self).write(values)
        if not 'update_feed' in context:
            authorization_token = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.authorization_token')
            base_url=self.env['ir.config_parameter'].sudo().get_param('twikey_integration.base_url')
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
                            _logger.error('Exception raised while updating invoice data to Twikey %s' % (e))
                            raise exceptions.AccessError(
                                _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                            )
        return res

    @api.multi
    def action_invoice_re_open(self):
        if self.filtered(lambda inv: inv.state not in ('in_payment', 'paid')):
            raise UserError(_('Invoice must be paid in order to set it to register payment.'))
        if self:
            return self.with_context(update_feed=True).write({'state': 'open'})
