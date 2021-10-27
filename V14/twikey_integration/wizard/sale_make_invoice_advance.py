# -*- coding: utf-8 -*-

from odoo import api, fields, models,exceptions,_
import requests
import base64
from odoo.exceptions import UserError
import logging
import uuid

_logger = logging.getLogger(__name__)

class SaleAdvancePaymentInv(models.TransientModel):
    _name = 'sale.advance.payment.inv'
    _inherit = 'sale.advance.payment.inv'

    template_id = fields.Many2one('contract.template', string="Contract Template")
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

    # def create_invoices(self):
    #     res = super(SaleAdvancePaymentInv, self).create_invoices()
    #     module_twikey = self.env['ir.config_parameter'].sudo().get_param(
    #         'twikey_integration.module_twikey')
    #     if module_twikey:
    #         context = self._context
    #         invoice_ids = []
    #         if 'active_id' in context:
    #             sale_id = self.env['sale.order'].browse(context.get('active_id'))
    #             invoice_id = self.env['account.move'].search([('id', '=', sale_id.invoice_ids[-1].id)])
    #             if invoice_id:
    #                 authorization_token = self.env['ir.config_parameter'].sudo().get_param(
    #                     'twikey_integration.authorization_token')
    #                 if authorization_token:
    #                     invoice_id.invoice_date = fields.Date.context_today(self)
    #                     invoice_id._onchange_invoice_date()
    #                     invoice_number = str(uuid.uuid1())
    #                     data = """{
    #                                 "number" : "%(number)s",
    #                                 "title" : "INV_%(id)s",
    #                                 "ct" : 2833,
    #                                 "amount" : %(Amount)s,
    #                                 "remittance": "INV_%(id)s",
    #                                 "date" : "%(InvoiceDate)s",
    #                                 "duedate" : "%(DueDate)s",
    #                                 "customerByRef" : "%(CustomerByRef)s"
    #                                 }""" % {'id': invoice_id.id,
    #                                         'Amount': invoice_id.amount_total,
    #                                         'InvoiceDate': fields.Date.context_today(self),
    #                                         'DueDate': invoice_id.invoice_date_due if invoice_id.invoice_date_due else fields.Date.context_today(
    #                                             self),
    #                                         'CustomerByRef': invoice_id.partner_id.id,
    #                                         'number': invoice_number[0]
    #                                         }
    #                     try:
    #                         response = requests.post('https://api.beta.twikey.com/creditor/invoice', data=data,
    #                                                  headers={'authorization': authorization_token})
    #                         resp_obj = json.loads(response.text)
    #                         if response.status_code == 400 and resp_obj.get('message') and resp_obj.get(
    #                                 'message') == 'Debtor was not found':
    #                             data = """{
    #                                     "number" : "%(number)s",
    #                                     "title" : "INV_%(id)s",
    #                                     "ct" : 2833,
    #                                     "amount" : %(Amount)s,
    #                                     "date" : "%(InvoiceDate)s",
    #                                     "duedate" : "%(DueDate)s",
    #                                     "customer": {"customerNumber" : "%(CustomerNumber)s",
    #                                              "email" : "%(Email)s",
    #                                              "firstname" : "%(FirstName)s",
    #                                              "lastname" : "%(LastName)s",
    #                                              "companyName" : "%(CompanyName)s",
    #                                              "coc" : "%(Coc)s",
    #                                              "address" : "%(Address)s",
    #                                              "city" : "%(City)s",
    #                                              "zip" : "%(Zip)s",
    #                                              "country" : "%(Country)s",
    #                                              "mobile" : "%(Mobile)s"
    #                                             }
    #                                     }""" % {'number': invoice_number[0],
    #                                             'id': invoice_id.id,
    #                                             'Amount': invoice_id.amount_total,
    #                                             'InvoiceDate': fields.Date.context_today(self),
    #                                             'DueDate': invoice_id.invoice_date_due if invoice_id.invoice_date_due else fields.Date.context_today(
    #                                                 self),
    #                                             'CustomerNumber': invoice_id.partner_id.id if invoice_id.partner_id else '',
    #                                             'Email': invoice_id.partner_id.email if invoice_id.partner_id.email else '',
    #                                             'FirstName': invoice_id.partner_id.name.split(' ')[
    #                                                 0] if invoice_id.partner_id and invoice_id.partner_id.name and invoice_id.partner_id.company_type == 'person' else 'unknown',
    #                                             'LastName': invoice_id.partner_id.name.split(' ')[
    #                                                 1] if invoice_id.partner_id and invoice_id.partner_id.name and invoice_id.partner_id.company_type == 'person' else 'unknown',
    #                                             'CompanyName': invoice_id.partner_id.name if invoice_id.partner_id and invoice_id.partner_id.name and invoice_id.partner_id.company_type == 'company' else '',
    #                                             'Coc': invoice_id.partner_id.vat if invoice_id.partner_id and invoice_id.partner_id.vat and invoice_id.partner_id.company_type == 'company' else '',
    #                                             'Address': invoice_id.partner_id.street if invoice_id.partner_id and invoice_id.partner_id.street else '',
    #                                             'City': invoice_id.partner_id.city if invoice_id.partner_id and invoice_id.partner_id.city else '',
    #                                             'Zip': invoice_id.partner_id.zip if invoice_id.partner_id and invoice_id.partner_id.zip else '',
    #                                             'Country': invoice_id.partner_id.country_id.code if invoice_id.partner_id and invoice_id.partner_id.country_id else '',
    #                                             'Mobile': invoice_id.partner_id.mobile if invoice_id.partner_id.mobile else invoice_id.partner_id.phone if invoice_id.partner_id.phone else ''
    #                                             }
    #                             response = requests.post('https://api.beta.twikey.com/creditor/invoice', data=data,
    #                                                      headers={'authorization': authorization_token})
    #                             resp_obj = json.loads(response.text)
    #                         if response.status_code == 200:
    #                             invoice_id.write(
    #                                 {'twikey_url': resp_obj.get('url'), 'twikey_invoice_id': resp_obj.get('id')})
    #                             #                 update invoice API
    #                             pdf = self.env.ref('account.account_invoices')._render_qweb_pdf([invoice_id.id])[0]
    #                             report_file = base64.b64encode(pdf)
    #                             report_file_decode = report_file.decode('utf-8')
    #                             data = """{"title" : "INV_%(Title)s",
    #                                        "date" : "%(InvoiceDate)s",
    #                                        "duedate" : "%(DueDate)s",
    #                                        "pdf" : "%(ReportFile)s"
    #                                 }""" % {'Title': invoice_id.id,
    #                                         'InvoiceDate': fields.Date.context_today(self),
    #                                         'DueDate': invoice_id.invoice_date_due if invoice_id.invoice_date_due else fields.Date.context_today(
    #                                             self),
    #                                         'ReportFile': report_file_decode
    #                                         }
    #                             update_response = requests.put(
    #                                 'https://api.beta.twikey.com/creditor/invoice/%s' % resp_obj.get('id'), data=data,
    #                                 headers={'authorization': authorization_token, 'Content-Type': 'application/json'})
    #                             resp_obj = json.loads(update_response.content)
    #                     except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
    #                             requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
    #                         raise exceptions.AccessError(
    #                             _('The url that this service requested returned an error. Please check your connection or try after sometime.')
    #                         )
    #     return res

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
        #             # invoice_id.date_invoice = fields.Date.context_today(self)
        #             invoice_id._onchange_invoice_date()
        #             invoice_number =  str(uuid.uuid1())
        # #
        #             url = base_invoice_url + invoice_number
                    # invoice_id.with_context(update_feed=True).write({'twikey_url' : url, 'twikey_invoice_id' : invoice_number, 'template_id': self.template_id.id})
    #                  pdf = self.env.ref('account.account_invoices')._render_qweb_pdf([invoice_id.id])[0]
        #             report_file = base64.b64encode(pdf)
        #
        #             try:
        #                 partner_name = invoice_id.partner_id.name.split(' ')
        #                 data = """{
        #                         "id" : "%(number)s",
        #                         "number" : "%(id)s",
        #                         "title" : "INV_%(id)s",
        #                         "ct" : %(Template)s,
        #                         "amount" : %(Amount)s,
        #                         "date" : "%(InvoiceDate)s",
        #                         "duedate" : "%(DueDate)s",
        #                         "pdf": "%(pdf)s",
        #                         "customer": {"customerNumber" : "%(CustomerNumber)s",
        #                          "email" : "%(Email)s",
        #                          "firstname" : "%(FirstName)s",
        #                          "lastname" : "%(LastName)s",
        #                          "companyName" : "%(CompanyName)s",
        #                          "coc" : "%(Coc)s",
        #                          "address" : "%(Address)s",
        #                          "city" : "%(City)s",
        #                          "zip" : "%(Zip)s",
        #                          "country" : "%(Country)s",
        #                          "mobile" : "%(Mobile)s"
        #                         }
        #                 }""" % {'id' : invoice_id.id,
        #                         'number' : invoice_number,
        #                         'Template' : self.template_id.template_id,
        #                         'Amount' : invoice_id.amount_total,
        #                         'InvoiceDate' : fields.Date.context_today(self),
        #                         'DueDate' : invoice_id.invoice_date_due if invoice_id.invoice_date_due else fields.Date.context_today(self),
        #                         'pdf': report_file.decode('utf-8'),
        #                         'CustomerNumber' : invoice_id.partner_id.id if invoice_id.partner_id else '',
        #                         'Email' : invoice_id.partner_id.email if invoice_id.partner_id.email else '',
        #                         'FirstName' : partner_name[0] if partner_name and invoice_id.partner_id.company_type == 'person' else 'unknown',
        #                         'LastName' : partner_name[1] if partner_name and len(partner_name) > 1 and invoice_id.partner_id.company_type == 'person' else 'unknown',
        #                         'CompanyName' : invoice_id.partner_id.name if invoice_id.partner_id and invoice_id.partner_id.name and invoice_id.partner_id.company_type == 'company' else '',
        #                         'Coc' : invoice_id.partner_id.vat if invoice_id.partner_id and invoice_id.partner_id.vat and invoice_id.partner_id.company_type == 'company' else '',
        #                         'Address' : invoice_id.partner_id.street if invoice_id.partner_id and invoice_id.partner_id.street else '',
        #                         'City' : invoice_id.partner_id.city if invoice_id.partner_id and invoice_id.partner_id.city else '',
        #                         'Zip' : invoice_id.partner_id.zip if invoice_id.partner_id and invoice_id.partner_id.zip else '',
        #                         'Country' : invoice_id.partner_id.country_id.code if invoice_id.partner_id and invoice_id.partner_id.country_id else '',
        #                         'Mobile' : invoice_id.partner_id.mobile if invoice_id.partner_id.mobile else invoice_id.partner_id.phone if invoice_id.partner_id.phone else ''
        #                     }
        #                 try:
        #                     _logger.info('Creating new Invoice %s' % (data))
        #                     response = requests.post(base_url+"/creditor/invoice", data=data, headers={'authorization' : authorization_token})
        #                     _logger.info('Created new invoice %s' % (response.content))
        #                 except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
        #                     raise exceptions.AccessError(_('The url that this service requested returned an error. Please check your connection or try after sometime.'))
        #             except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
        #                 raise exceptions.AccessError(_('The url that this service requested returned an error. Please check your connection or try after sometime.'))
        #     else:
        #         raise UserError(_("Authorization Token Not Found, Please Run Authenticate Twikey Scheduled Actions Manually!!!"))
            if context.get('open_invoices', False):
                    return sale_orders.action_view_invoice()
        else:
            return super(SaleAdvancePaymentInv, self).create_invoices()









