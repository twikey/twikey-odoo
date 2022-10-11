# -*- coding: utf-8 -*-

from odoo import models, fields,exceptions,_
import requests
import base64
from odoo.exceptions import UserError
import logging
import uuid

from .. import twikey

_logger = logging.getLogger(__name__)

InvoiceStatus = {
    'BOOKED': 'posted',
    'PENDING': 'posted',
    'PAID': 'posted',
    'EXPIRED': 'cancel',
    'ARCHIVED': 'cancel',
}

TwikeyInvoiceStatus = {
    'draft': 'booked',
    'posted': 'booked',
    'in_payment': 'booked',
    'paid': 'paid',
    'cancel': 'archived'
}

class AccountInvoice(models.Model):
    _inherit = 'account.move'

    twikey_url = fields.Char(string="Twikey Invoice URL", help="URL of the Twikey Invoice",readonly=True)
    twikey_invoice_id = fields.Char(string="Twikey Invoice ID", help="Invoice ID of Twikey.",readonly=True)
    template_id = fields.Many2one('twikey.contract.template', string="Contract Template")
    is_twikey = fields.Boolean(compute='compute_twikey')

    def action_post(self):
        res = super(AccountInvoice, self).action_post()
        params = self.env['ir.config_parameter'].sudo()
        module_twikey = params.get_param('twikey_integration.module_twikey')
        if not module_twikey:
            return res

        twikey_client = params.get_twikey_client()
        invoice_id = self
        invoice_uuid = str(uuid.uuid1())

        url = twikey_client.invoice.geturl(invoice_uuid)
        invoice_id.with_context(update_feed=True).write({'twikey_url': url, 'twikey_invoice_id': invoice_uuid})
        pdf = self.env.ref('account.account_invoices')._render_qweb_pdf([invoice_id.id])[0]
        report_file = base64.b64encode(pdf)
        try:
            customer = invoice_id.partner_id
            today = fields.Date.context_today(self).isoformat()
            id = customer.id
            if customer.parent_id:
                id = customer.parent_id.id
            invoiceCustomer = {
                'locale': customer.lang if customer else 'en',
                'customerNumber': id,
                'address': customer.street if customer and customer.street else '',
                'city': customer.city if customer and customer.city else '',
                'zip': customer.zip if customer and customer.zip else '',
                'country': customer.country_id.code if customer and customer.country_id else '',
                'mobile': customer.mobile if customer.mobile else '',
            }
            if customer.email:
                invoiceCustomer["email"] = customer.email
            if customer.company_type == 'company' and customer.name:
                invoiceCustomer["companyName"] = customer.name
                invoiceCustomer["coc"] = customer.vat
            elif customer.name: # 'person'
                customer_name = customer.name.split(' ')
                if customer_name and len(customer_name) > 1:
                    invoiceCustomer["firstname"] = customer_name[0]
                    invoiceCustomer["lastname"] = ' '.join(customer_name[1:])
                else:
                    invoiceCustomer["firstname"] = customer.name

            data = {
                'id': invoice_uuid,
                'number': invoice_id.name,
                "title": invoice_id.name,
                'ct': self.template_id.template_id,
                'amount': invoice_id.amount_total,
                'date': today,
                'duedate': invoice_id.invoice_date_due.isoformat() if invoice_id.invoice_date_due else today,
                "pdf": report_file.decode('utf-8'),
                "remittance": invoice_id.payment_reference,
                "ref": invoice_id.id,
                'locale': customer.lang if customer else 'en',
                "customer": invoiceCustomer
            }
            _logger.debug('Creating new Invoice %s' % (data))
            response = twikey_client.invoice.create(data)
            _logger.info('Created new invoice %s' % response)

        except (ValueError, requests.exceptions.RequestException) as e:
            raise exceptions.AccessError(
                _('The url that this service requested returned an error. Please check your connection or try after sometime.'))
        except twikey.client.TwikeyError as e:
            raise UserError(('An error occurred calling twikey: %s (%s)' % (e.error,e.error_code)))
        return res

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
            _logger.error('Error while updating invoice from Twikey: %s' % ue)
        except (ValueError, requests.exceptions.RequestException) as e:
            _logger.error('Error while updating invoices from Twikey: %s' % e)


    def write(self, values):
        res = super(AccountInvoice, self).write(values)
        if 'update_feed' in self._context:
            return res

        self.update_invoice_feed()
        return res

## Note this class merely serves the purpose of adding a note to a paid invoice awaiting coda files from the bank
## which will use the matching logic of Odoo
class OdooInvoiceFeed(twikey.invoice.InvoiceFeed):

    def __init__(self, env):
        self.env = env

    def invoice(self, _invoice):

        odoo_invoice_id = _invoice.get('ref')
        new_state = _invoice["state"]
        odoo_state = InvoiceStatus[new_state]

        try:
            lookup_id = int(odoo_invoice_id)
            _logger.debug("Got update for %d",lookup_id)
            invoice_id = self.env['account.move'].browse(lookup_id)
            if invoice_id:
                # Only when changed
                if odoo_state == 'paid' and invoice_id.state != 'paid':
                    try:
                        if invoice_id.state == 'draft':
                            invoice_id.with_context(update_feed=True).action_invoice_open()
                        if invoice_id.state == 'open':
                            inv_ref = invoice_id.with_context(update_feed=True)._get_computed_reference()

                        payment_reference = "unknown"
                        if 'lastpayment' in _invoice:
                            payment = _invoice['lastpayment'][0] # first one is the last one happened
                            twikey_payment_method = payment['method']
                            if twikey_payment_method == 'paylink':
                                payment_reference = 'paylink #%d' % payment['link']
                            elif twikey_payment_method == 'sdd':
                                payment_reference = 'Sepa Direct Debit pmtinf=%s e2e=%s' % (payment['pmtinf'],payment['e2e'])
                            elif twikey_payment_method == 'rcc':
                                payment_reference = 'Recurring Credit Card pmtinf=%s e2e=%s' % (payment['pmtinf'],payment['e2e'])
                            elif twikey_payment_method == 'transfer':
                                payment_reference = 'Regular transfer msg=%s' % (payment['msg'])
                            elif twikey_payment_method == 'manual':
                                payment_reference = 'Manually set as paid msg=%s' % (payment['msg'])
                            else:
                                payment_reference = 'Other'

                        invoice_id.message_post(body='Twikey payment via '+payment_reference)

                    except (ValueError, requests.exceptions.RequestException) as e:
                        _logger.error('Error marking invoice as paid in odoo %s' % (e))
                        raise exceptions.AccessError(_('Something went wrong.'))
                    else:
                        _logger.info("Unknown invoice update of %s - %s" % (_invoice.get('title'), new_state))
                invoice_id.with_context(update_feed=True).write({'state': odoo_state})
        except Exception as ue:
            _logger.error('Error while updating invoices from Twikey: %s' % ue)
