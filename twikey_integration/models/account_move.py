import base64
import logging
import uuid

import requests

from odoo import SUPERUSER_ID, _, exceptions, fields, models
from odoo.exceptions import UserError

from .. import twikey

_logger = logging.getLogger(__name__)

InvoiceStatus = {
    "BOOKED": "posted",
    "PENDING": "posted",
    "PAID": "posted",
    "EXPIRED": "cancel",
    "ARCHIVED": "cancel",
}


class AccountInvoice(models.Model):
    _inherit = "account.move"

    twikey_url = fields.Char(
        string="Twikey Invoice URL", help="URL of the Twikey Invoice", readonly=True
    )
    twikey_invoice_identifier = fields.Char(
        string="Twikey Invoice ID", help="Invoice ID of Twikey.", readonly=True
    )
    twikey_template_id = fields.Many2one("twikey.contract.template", string="Contract Template")
    twikey_invoice_state = fields.Selection(
        selection=[
            ("BOOKED", "Booked"),
            ("PENDING", "Pending"),
            ("PAID", "Paid"),
            ("EXPIRED", "Expired"),
            ("ARCHIVED", "Archived"),
        ],
        readonly=True,
        default="BOOKED",
    )

    def action_post(self):
        res = super(AccountInvoice, self).action_post()

        # sometimes action_post gets called without an invoice record, in this case we don't try to
        # send anything to Twikey
        if not self:
            return res

        twikey_client = (
            self.env["ir.config_parameter"].sudo().get_twikey_client(company=self.env.company)
        )
        if twikey_client:
            invoice_id = self
            invoice_uuid = str(uuid.uuid4())

            url = twikey_client.invoice.geturl(invoice_uuid)
            invoice_id.with_context(update_feed=True).write(
                {"twikey_url": url, "twikey_invoice_identifier": invoice_uuid}
            )
            pdf = (
                self.env.ref("account.account_invoices")
                .with_user(SUPERUSER_ID)
                ._render_qweb_pdf([invoice_id.id])[0]
            )
            report_file = base64.b64encode(pdf)
            try:
                customer = invoice_id.partner_id
                today = fields.Date.context_today(self).isoformat()
                current_id = customer.id
                if customer.parent_id:
                    current_id = customer.parent_id.id
                invoice_customer = {
                    "locale": customer.lang if customer else "en",
                    "customerNumber": current_id,
                    "address": customer.street if customer and customer.street else "",
                    "city": customer.city if customer and customer.city else "",
                    "zip": customer.zip if customer and customer.zip else "",
                    "country": customer.country_id.code if customer and customer.country_id else "",
                    "mobile": customer.mobile if customer.mobile else "",
                }
                if customer.email:
                    invoice_customer["email"] = customer.email
                if customer.company_type == "company" and customer.name:
                    invoice_customer["companyName"] = customer.name
                    invoice_customer["coc"] = customer.vat
                elif customer.name:  # 'person'
                    customer_name = customer.name.split(" ")
                    if customer_name and len(customer_name) > 1:
                        invoice_customer["firstname"] = customer_name[0]
                        invoice_customer["lastname"] = " ".join(customer_name[1:])
                    else:
                        invoice_customer["firstname"] = customer.name

                data = {
                    "id": invoice_uuid,
                    "number": invoice_id.name,
                    "title": invoice_id.name,
                    "ct": self.twikey_template_id.template_id_twikey,
                    "amount": invoice_id.amount_total,
                    "date": today,
                    "duedate": invoice_id.invoice_date_due.isoformat()
                    if invoice_id.invoice_date_due
                    else today,
                    "pdf": report_file.decode("utf-8"),
                    "remittance": invoice_id.payment_reference,
                    "ref": invoice_id.id,
                    "locale": customer.lang if customer else "en",
                    "customer": invoice_customer,
                }

                twikey_client.invoice.create(data)

            except (ValueError, requests.exceptions.RequestException) as e:
                raise exceptions.AccessError from e
        return res

    def update_invoice_feed(self):
        try:
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(
                company=self.env.company
            )
            if twikey_client:
                twikey_client.invoice.feed(OdooInvoiceFeed(self.env))
        except (ValueError, requests.exceptions.RequestException) as e:
            raise UserError from e

    def write(self, values):
        res = super(AccountInvoice, self).write(values)
        if "update_feed" in self._context:
            return res

        self.update_invoice_feed()
        return res


class OdooInvoiceFeed(twikey.invoice.InvoiceFeed):
    def __init__(self, env):
        self.env = env

    def process_states(self, invoice_id, twikey_invoice, new_state):
        _logger.info("Processing state for invoice: " + str(twikey_invoice))
        invoice_id.twikey_invoice_state = new_state
        if new_state == "PAID" and twikey_invoice["amount"] == invoice_id.amount_total:
            journals = self.env["account.journal"].search([("use_with_twikey", "=", True)])

            if len(journals) == 1:
                payment_method_line_twikey = journals.inbound_payment_method_line_ids.filtered(
                    lambda x: x.name == "Twikey" and x.payment_method_id.name == "manual"
                )

                if not payment_method_line_twikey:
                    payment_method_manual = self.env["account.payment.method"].search(
                        [("name", "=", "Manual"), ("payment_type", "=", "inbound")]
                    )
                    if not payment_method_manual:
                        _logger.info("Creating an account payment method")
                        payment_method_manual = self.env["account.payment.method"].create(
                            {
                                "name": "Manual",
                                "payment_type": "inbound",
                                "code": "manual",
                            }
                        )

                    _logger.info("Creating an account payment method line")
                    payment_method_line_twikey = self.env["account.payment.method.line"].create(
                        {
                            "payment_method_id": payment_method_manual[0].id,
                            "name": "Twikey",
                        }
                    )

                iban = False
                if twikey_invoice.get("lastpayment")[0].get("method") in ["sdd", "transfer"]:
                    iban = twikey_invoice.get("lastpayment")[0].get("iban")

                customer = False
                if twikey_invoice.get("customer") and twikey_invoice.get("customer").get(
                    "customerNumber"
                ):
                    customer = self.env["res.partner"].browse(
                        [int(twikey_invoice.get("customer").get("customerNumber"))]
                    )

                _logger.info("Found customer: " + str(customer.name) + " and iban: " + str(iban))

                customer_bank_id = False
                if customer and iban:
                    customer_bank_id = customer.bank_ids.filtered(lambda x: x.acc_number == iban)
                    if not customer_bank_id:
                        customer_bank_id = self.env["res.partner.bank"].create(
                            {"partner_id": customer.id, "acc_number": iban}
                        )

                payment = (
                    self.env["account.payment.register"]
                    .with_context(active_model="account.move", active_ids=invoice_id.ids)
                    .create(
                        {
                            "journal_id": journals.id,
                            "payment_date": twikey_invoice["paydate"],
                            "payment_method_line_id": payment_method_line_twikey[
                                0
                            ].payment_method_id.id,
                            "partner_bank_id": customer_bank_id.id if customer_bank_id else False,
                        }
                    )
                )

                _logger.info("Creating payment")
                payment.action_create_payments()

            elif len(journals) > 1:
                raise UserError(_("It's not allowed to use Twikey in multiple journals!"))
            else:
                error_message = _(
                    "Error while searching for a journal with 'use with Twikey' enabled!"
                )
                invoice_id.message_post(error_message)
                raise UserError(error_message)

    def invoice(self, _invoice):
        odoo_invoice_id = _invoice.get("ref")
        new_state = _invoice["state"]
        odoo_state = InvoiceStatus[new_state]

        try:
            lookup_id = int(odoo_invoice_id)
            _logger.debug("Got update for %d", lookup_id)
            invoice_id = self.env["account.move"].browse(lookup_id)
            if invoice_id.exists():
                self.process_states(invoice_id, _invoice, new_state)

                if invoice_id.payment_state == "paid":
                    try:
                        payment_reference = "unknown"
                        if "lastpayment" in _invoice:
                            payment = _invoice["lastpayment"][0]
                            twikey_payment_method = payment["method"]
                            if twikey_payment_method == "paylink":
                                payment_reference = "paylink #%d" % payment["link"]
                            elif twikey_payment_method == "sdd":
                                payment_reference = "Sepa Direct Debit pmtinf={} e2e={}".format(
                                    payment["pmtinf"],
                                    payment["e2e"],
                                )
                            elif twikey_payment_method == "rcc":
                                payment_reference = "Recurring Credit Card pmtinf={} e2e={}".format(
                                    payment["pmtinf"],
                                    payment["e2e"],
                                )
                            elif twikey_payment_method == "transfer":
                                payment_reference = "Regular transfer msg=%s" % (payment["msg"])
                            elif twikey_payment_method == "manual":
                                payment_reference = "Manually set as paid msg=%s" % (payment["msg"])
                            else:
                                payment_reference = "Other"

                        invoice_id.message_post(body="Twikey payment via " + payment_reference)

                    except (ValueError, requests.exceptions.RequestException) as e:
                        _logger.error("Error marking invoice as paid in odoo %s" % (e))
                        raise exceptions.AccessError from e
                    else:
                        _logger.info(
                            "Unknown invoice update of {} - {}".format(
                                _invoice.get("title"), new_state
                            )
                        )
                invoice_id.with_context(update_feed=True).write({"state": odoo_state})
        except Exception as ue:
            _logger.error("Error while updating invoices from Twikey: %s" % ue)
