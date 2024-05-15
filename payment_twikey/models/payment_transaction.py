# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import datetime

from werkzeug import urls

from odoo import _, models
from odoo.exceptions import UserError, ValidationError

from ..twikey.client import TwikeyError
from ..utils import get_twikey_customer

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_rendering_values(self, processing_values):
        """
        Return a dict of provider-specific values used to render the redirect form.
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'twikey':
            return res

        # _logger.info("Sending transaction request:\n%s", pprint.pformat(payload))

        base_url = self.provider_id.get_base_url()
        twikey_template = self.provider_id.twikey_template_id
        method = self.provider_id.twikey_method

        try:
            customer = self.partner_id
            twikey_client = self.env["ir.config_parameter"].sudo().get_twikey_client(company=self.provider_id.company_id)
            if twikey_client:
                if self.provider_id.allow_tokenization and twikey_template:
                    payload = self._twikey_prepare_token_request_payload(customer, base_url, twikey_template.template_id_twikey, method)
                    mndt = twikey_client.document.sign(payload)
                    # The provider reference is set now to allow fetching the payment status after redirection
                    self.provider_reference = mndt.get('MndtId')
                    url = mndt.get('url')

                    # Store the mandate
                    self.env["twikey.mandate.details"].sudo().create({
                        "contract_temp_id": twikey_template.id,
                        "lang": customer.lang,
                        "partner_id": payload.get("customerNumber"),
                        "reference": self.provider_reference,
                        "url": url,
                        "zip": customer.zip if customer.zip else False,
                        "address": customer.street if customer.street else False,
                        "city": customer.city if customer.city else False,
                        "country_id": customer.country_id.id if customer.country_id else False,
                    })
                else:
                    payload = self._twikey_prepare_payment_request_payload(customer, base_url, twikey_template.template_id_twikey, method)
                    paylink = twikey_client.paylink.create(payload)
                    # The provider reference is set now to allow fetching the payment status after redirection
                    self.provider_reference = paylink.get('id')
                    url = paylink.get('url')

                parsed_url = urls.url_parse(url)
                url_params = urls.url_decode(parsed_url.query)
                # Extract the checkout URL from the payment data and add it with its query parameters to the
                # rendering values. Passing the query parameters separately is necessary to prevent them
                # from being stripped off when redirecting the user to the checkout URL, which can happen
                # when only one payment method is enabled and query parameters are provided.
                return {'api_url': url, 'url_params': url_params, 'reference': self.provider_reference}
            else:
                _logger.warning(f"No configuration found for {self.env.company}")
                raise ValidationError("Configuration not set")
        except TwikeyError as e:
            raise ValidationError("Twikey: " + e.error)

    def _twikey_prepare_payment_request_payload(self, customer, base_url, template, method):
        """
        Create the payload for the payment request based on the transaction values.
        :return: The request payload
        :rtype: dict
        """
        payload = get_twikey_customer(customer)
        payload["redirectUrl"] = urls.url_join(base_url, f'/twikey/status?ref={self.reference}'),
        payload['title'] = self.reference,
        payload['remittance'] = self.reference,
        payload['amount'] = f"{self.amount:.2f}",
        if template:
            payload["ct"] = template
        if method:
            payload["method"] = method

        if self.invoice_ids:
            if len(self.invoice_ids) == 1:
                if self.invoice_ids[0].twikey_invoice_identifier:
                    payload['invoice'] = self.invoice_ids[0].name
                    payload['remittance'] = self.invoice_ids[0].id
                else:
                    _logger.info("Unknown invoice to Twikey, not linking")
            else:
                raise "Unable to combine 2 invoices to the same link for reconciliation reasons"

        return payload

    def _twikey_prepare_token_request_payload(self, customer, base_url, template, method):

        self.tokenize = True
        payload = get_twikey_customer(customer)
        payload["ct"] = template,
        payload["method"] = method,
        payload["redirectUrl"] = urls.url_join(base_url, f'/twikey/status?ref={self.reference}'),
        payload['transactionMessage'] = self.reference,
        payload['transactionRef'] = self.reference,
        payload['transactionAmount'] = f"{self.amount:.2f}",
        if self.invoice_ids:
            if len(self.invoice_ids) == 1:
                if self.invoice_ids[0].twikey_invoice_identifier:
                    payload['invoice'] = self.invoice_ids[0].name
                else:
                    _logger.info("Unknown invoice to Twikey, not linking")
            else:
                raise "Unable to combine 2 invoices to the same link for reconciliation reasons"

        return payload

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        tx = self.search([('reference', '=', notification_data.get('ref')), ('provider_code', '=', 'twikey')])
        if provider_code != 'twikey' or len(tx) == 1:
            return tx
        if not tx:
            raise ValidationError("Twikey: " + _("No transaction found matching reference %s.", notification_data.get('ref')))
        return tx

    def _process_notification_data(self, notification_data):
        """ Override of payment to process the transaction based on webhook data.

        Note: self.ensure_one()

        :param dict notification_data: The notification data sent by the provider
        :return: None
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'twikey':
            return

        payment_status = notification_data.get('status')
        if not payment_status:
            _logger.info("No status update for reference %s, setting to pending", self.reference)
            self._set_pending()
            return

        if self.tokenize:
            # Webhook should have come in with the mandate now being signed
            mandate_id = (self.env["twikey.mandate.details"].search([("reference", "=", self.provider_reference)]))
            if mandate_id.state == 'signed':
                payment_status = 'paid'
                _logger.debug(f"Tokenized redirect, mandate was {mandate_id.state}")
                self.provider_id.token_from_mandate(self.partner_id, mandate_id)
            else:
                _logger.info(f"Tokenized redirect but mandate ({self.provider_reference}) was {mandate_id.state}")

        if payment_status == 'pending':
            self._set_pending()
        elif payment_status == 'authorized':
            self._set_authorized()
        elif payment_status == 'paid':
            self._set_done()
        elif payment_status in ['expired', 'canceled', 'failed']:
            self._set_canceled("Twikey: " + _("Canceled payment with status: %s", payment_status))
        else:
            _logger.info("received data with invalid payment status (%s) for transaction with reference %s",payment_status, self.reference)
            self._set_error("Twikey: " + _("Received data with invalid payment status: %s", payment_status))

    def _get_post_processing_values(self):
        """ Return a dict of values used to display the status of the transaction.

        For a provider to handle transaction status display, it must override this method and
        return a dict of values. Provider-specific values take precedence over those of the dict of
        generic post-processing values.
        """
        values = super()._get_post_processing_values()
        if self.provider_code != 'twikey':
            return values

        if self.tokenize and values.get('state') in ['draft','pending']:
            # Webhook should have come in with the mandate now being signed
            mandate_id = self.env["twikey.mandate.details"].search([("reference", "=", self.provider_reference)])
            if mandate_id and mandate_id.state == 'signed':
                _logger.info(f"Tokenized poll, mandate was {mandate_id.state}")
                self.provider_id.token_from_mandate(self.partner_id, mandate_id)
                self._set_done()
            else:
                _logger.info(f"Mandate ({self.provider_reference}) was in {mandate_id.state} for ref {self.reference}")
        return values

    def _send_payment_request(self):
        """ Override of payment to send a payment request to Twikey.

        Note: self.ensure_one()

        :return: None
        :raise UserError: If the transaction is not linked to a token.
        """
        super()._send_payment_request()
        if self.provider_code != 'twikey':
            return

        # Prepare the payment request to Twikey.
        if not self.token_id:
            raise UserError("Twikey: " + _("The transaction is not linked to a token."))

        twikey_client = self.env["ir.config_parameter"].sudo().get_twikey_client(company=self.provider_id.company_id)
        if twikey_client:
            try:
                super()._send_payment_request()
                if self._context.get('active_model') == 'account.move':
                    invoice_id = self.env['account.move'].browse(self._context.get('active_ids', []))
                    invoice = {
                        "customerByDocument": self.token_id.provider_ref,
                        "number": invoice_id.name,
                        "title": self.reference,
                        "amount": self.amount,
                        "remittance": self.reference,
                        "ref": invoice_id.id,
                        "date": invoice_id.invoice_date.isoformat(),
                        "duedate": invoice_id.invoice_date_due.isoformat(),
                    }
                    twikey_invoice = twikey_client.invoice.create(invoice, "Odoo")
                    template_id = self.env["twikey.contract.template"].search(
                        [("template_id_twikey", "=", twikey_invoice.get("ct"))], limit=1
                    )
                    invoice_id.with_context(update_feed=True).write({
                        "send_to_twikey": True,
                        "twikey_template_id": template_id.id,
                        "twikey_url": twikey_invoice.get("url"),
                        "twikey_invoice_identifier": twikey_invoice.get("id"),
                        "twikey_invoice_state": twikey_invoice.get("state")
                    })
                else:
                    today = datetime.date.today().isoformat()
                    invoice = {
                        "customerByDocument": self.token_id.provider_ref,
                        "number": self.reference,
                        "title": self.reference,
                        "amount": self.amount,
                        "remittance": self.reference,
                        "ref": self.reference,
                        "date": today,
                        "duedate": today,
                    }
                    twikey_invoice = twikey_client.invoice.create(invoice, "Odoo")

                self.provider_reference = twikey_invoice.get("id")
                state = twikey_invoice.get("state")
                self.partner_id.message_post(body=f"Send {self.reference} to Twikey with state={state}")
                self._set_pending(f"Send to Twikey (state={state})")
                # Handle the payment request response.
                _logger.info("Send transaction with reference %s: %s",self.reference, self.provider_reference)
            except TwikeyError as e:
                raise UserError("Twikey: " + e.error)
        else:
            raise UserError("Twikey: " + _("Could not connect to Twikey"))
