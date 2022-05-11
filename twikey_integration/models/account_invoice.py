# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions,_
import requests
import base64
from odoo.exceptions import UserError
import logging
import uuid
import datetime

from .. import twikey

_logger = logging.getLogger(__name__)

InvoiceStatus = {
    'BOOKED': 'open',
    'PENDING': 'in_payment',
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
    template_id = fields.Many2one('twikey.contract.template', string="Contract Template")
    is_twikey = fields.Boolean(compute='compute_twikey')

    @api.multi
    def action_invoice_open(self):
        res = super(AccountInvoice, self).action_invoice_open()
        params = self.env['ir.config_parameter'].sudo()
        module_twikey = params.get_param('twikey_integration.module_twikey')
        if not module_twikey:
            return res

        twikey_client = params.get_twikey_client()
        merchant_id = params.get_param('twikey_integration.merchant_id')
        invoice_id = self
        invoice_uuid = str(uuid.uuid1())

        url = twikey_client.invoice.geturl(invoice_uuid)
        invoice_id.with_context(update_feed=True).write({'twikey_url': url, 'twikey_invoice_id': invoice_uuid})
        pdf = self.env.ref('account.account_invoices').render_qweb_pdf([invoice_id.id])[0]
        report_file = base64.b64encode(pdf)

        sequence = invoice_id.journal_id.sequence_id
        sequence_number = invoice_id.journal_id.sequence_number_next
        if not sequence:
            raise UserError(_('Please define a sequence on your journal.'))

        try:
            customer = invoice_id.partner_id
            partner_name = customer.name.split(' ')
            today = fields.Date.context_today(self).isoformat()
            data = {
                'id': invoice_uuid,
                'number': sequence_number,
                "title": invoice_id.number,
                'ct': self.template_id.template_id,
                'amount': invoice_id.amount_total,
                'date': today,
                'duedate': invoice_id.date_due.isoformat() if invoice_id.date_due else today,
                "pdf": report_file.decode('utf-8'),
                "remittance": invoice_id.reference,
                'locale': customer.lang if customer else 'en',
                "customer": {
                    'locale': customer.lang if customer else 'en',
                    'customerNumber': customer.id if customer else '',
                    'email': customer.email if customer.email else '',
                    'firstname': partner_name[0] if partner_name and customer.company_type == 'person' else 'unknown',
                    'lastname': partner_name[1] if partner_name and len(partner_name) > 1 and customer.company_type == 'person' else 'unknown',
                    'companyName': customer.name if customer and customer.name and customer.company_type == 'company' else '',
                    'coc': customer.vat if customer and customer.vat and customer.company_type == 'company' else '',
                    'address': customer.street if customer and customer.street else '',
                    'city': customer.city if customer and customer.city else '',
                    'zip': customer.zip if customer and customer.zip else '',
                    'country': customer.country_id.code if customer and customer.country_id else '',
                    'mobile': customer.mobile if customer.mobile else customer.phone if customer.phone else '',
                }
            }
            _logger.debug('Creating new Invoice %s' % (data))
            response = twikey_client.invoice.create(data)
            _logger.info('Created new invoice %s' % response)
        except (ValueError, requests.exceptions.RequestException) as e:
            raise exceptions.AccessError(_('The url that this service requested returned an error. Please check your connection or try after sometime.'))

    def compute_twikey(self):
        module_twikey = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.module_twikey')
        if module_twikey:
            self.update({'is_twikey': True})
        else:
            self.update({'is_twikey': False})

    def update_invoice_feed(self):
        try:
            twikey_client = self.env['ir.config_parameter'].get_twikey_client()
            twikey_client.invoice.feed(OdooInvoiceFeed(self.env))
        except UserError as ue:
            _logger.error('Error while updating mandates from Twikey: %s' % ue)
        except (ValueError, requests.exceptions.RequestException) as e:
            _logger.error('Error while updating invoices from Twikey: %s' % e)

    @api.multi
    def write(self, values):
        res = super(AccountInvoice, self).write(values)
        if 'update_feed' in self._context:
            return res
        self.update_invoice_feed()
        return res

    @api.multi
    def action_invoice_re_open(self):
        if self.filtered(lambda inv: inv.state not in ('in_payment', 'paid')):
            raise UserError(_('Invoice must be paid in order to set it to register payment.'))
        if self:
            return self.with_context(update_feed=True).write({'state': 'open'})

class OdooInvoiceFeed(twikey.invoice.InvoiceFeed):

    def __init__(self, env):
        self.env = env

    def invoice(self, _invoice):
        if _invoice.get('customer'):
            try:
                customer_id = _invoice.get('customer')
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
            except (ValueError, requests.exceptions.RequestException) as e:
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
        invoice_id = self.env['account.invoice'].search([('twikey_invoice_id', '=', _invoice.get('id'))])

        _logger.info("Update of %s - %s" % (_invoice.get('title'),_invoice["state"]))
        newState_ = InvoiceStatus[_invoice["state"]]
        if not invoice_id:
            try:
                invoice_id = self.env['account.invoice'].create({'twikey_invoice_id': _invoice.get('id'),
                                                                 'number': _invoice.get('title'),
                                                                 'partner_id': partner_id.id,
                                                                 'date_due': _invoice.get('duedate'),
                                                                 'date_invoice': _invoice.get('date'),
                                                                 'amount_total': _invoice.get('amount'),
                                                                 'twikey_url': _invoice.get('url'),
                                                                 'state': newState_
                                                                 })
            except (ValueError, requests.exceptions.RequestException) as e:
                _logger.error('Error creating invoice in odoo %s' % (e))
                raise exceptions.AccessError(_('Something went wrong.'))
            if invoice_id:
                invoice_account = self.env['account.account'].search([('user_type_id', '=', self.env.ref('account.data_account_type_receivable').id)], limit=1).id
                self.env['account.invoice.line'].create({'product_id': self.env.ref('twikey_integration.product_product_twikey_invoice').id,
                                                         'quantity': 1.0,
                                                         'price_unit': _invoice.get('amount'),
                                                         'invoice_id': invoice_id.id,
                                                         'name': 'Twikey Invoice Product',
                                                         'account_id': invoice_account,
                                                         })
        inv_ref = ''
        if newState_ == 'paid' and invoice_id.state != 'paid':
            try:
                if invoice_id.state == 'draft':
                    invoice_id.with_context(update_feed=True).action_invoice_open()
                if invoice_id.state == 'open':
                    inv_ref = invoice_id.with_context(update_feed=True)._get_computed_reference()
                    journal_id = self.env['account.journal'].search([('type', '=', 'bank')], limit=1)
                    payment_method = self.env.ref('account.account_payment_method_manual_in')
                    journal_payment_methods = journal_id.inbound_payment_method_ids

                    payment_reference = "unknown"
                    if 'lastpayment' in _invoice:
                        payment = _invoice['lastpayment'][0] # first one is the last one happened
                        if payment['method'] == 'paylink':
                            payment_reference = 'paylink #%d' % payment['link']
                        elif payment['method'] == 'sdd':
                            payment_reference = 'sdd pmtinf=%s e2e=%s' % (payment['pmtinf'],payment['e2e'])
                        elif payment['method'] == 'rcc':
                            payment_reference = 'rcc pmtinf=%s e2e=%s' % (payment['pmtinf'],payment['e2e'])
                        elif payment['method'] == 'transfer':
                            payment_reference = 'transfer msg=%s' % (payment['msg'])
                        elif payment['method'] == 'manual':
                            payment_reference = 'manual msg=%s' % (payment['msg'])
                        else:
                            payment_reference = payment['method']

                    payment_id = self.env['account.payment'].with_context(update_feed=True).create({'amount': invoice_id.amount_total,
                                                                                                    'journal_id': journal_id.id,
                                                                                                    'state': 'draft',
                                                                                                    'payment_type': 'inbound',
                                                                                                    'partner_type': 'customer',
                                                                                                    'payment_method_id': journal_payment_methods.id,
                                                                                                    'partner_id': partner_id.id,
                                                                                                    'payment_date': datetime.date.today(),
                                                                                                    'communication': inv_ref,
                                                                                                    'payment_reference': payment_reference
                                                                                                    })
                    payment_id.with_context(update_feed=True).post()
                    credit_aml_id = self.env['account.move.line'].search([('payment_id', '=', payment_id.id), ('credit', '!=', 0)])
                    if credit_aml_id:
                        invoice_id.with_context(update_feed=True).assign_outstanding_credit(credit_aml_id.id)
            except (ValueError, requests.exceptions.RequestException) as e:
                _logger.error('Error marking invoice as paid in odoo %s' % (e))
                raise exceptions.AccessError(_('Something went wrong.'))

        invoice_id.with_context(update_feed=True).write({'number': _invoice.get('number'),
                                                         'partner_id': partner_id.id,
                                                         'date_due': _invoice.get('duedate'),
                                                         'date_invoice': _invoice.get('date'),
                                                         'reference': inv_ref if inv_ref else '',
                                                         'amount_total': _invoice.get('amount'),
                                                         'twikey_url': _invoice.get('url'),
                                                         'state': newState_
                                                         })
