import base64
import logging
import uuid

from odoo import _, api, exceptions, fields, models
from odoo.exceptions import UserError

from ..twikey.client import TwikeyError
from ..twikey.invoice import InvoiceFeed
from ..utils import get_twikey_customer, get_error_msg, get_success_msg

_logger = logging.getLogger(__name__)

InvoiceStatus = {
    "BOOKED": "posted",
    "PENDING": "posted",
    "PAID": "posted",
    "EXPIRED": "posted",
    "ARCHIVED": "cancel",
}


class AccountInvoice(models.Model):
    _inherit = "account.move"

    twikey_url = fields.Char(string="Twikey Invoice URL", help="URL of the Twikey Invoice", readonly=True)
    twikey_invoice_identifier = fields.Char(string="Twikey Invoice ID", help="Invoice ID of Twikey.", readonly=True)
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
    )

    send_to_twikey = fields.Boolean(string="Send to Twikey",
                                    default=lambda self: self._default_twikey_send,  readonly=False)
    auto_collect_invoice = fields.Boolean(string="Collect the invoice if possible",
                                    default=lambda self: self._default_auto_collect, readonly=False)
    include_pdf_invoice = fields.Boolean("Include pdf for invoices", help="Also send the invoice pdf to Twikey",
                                    default=lambda self: self._default_include_pdf)

    is_twikey_eligable = fields.Boolean(
        string="Invoice or Creditnote",
        help="The account move can be sent to Twikey. The user can override this with field 'send_to_twikey'.",
        compute="_compute_twikey_eligable",
    )

    def get_default(self, key, _default):
        cfg = self.env['ir.config_parameter'].sudo()
        return cfg.get_param(key, _default)

    def action_post(self):
        res = super(AccountInvoice, self).action_post()

        # sometimes action_post gets called without an invoice record, in this case we don't try to
        # send anything to Twikey
        if not self:
            return res

        if self.is_twikey_eligable and self.send_to_twikey:
            twikey_client = (self.env["ir.config_parameter"].sudo().get_twikey_client(company=self.env.company))
            if twikey_client:
                invoice_id = self

                # ensure logged in otherwise company of url might not be filled in
                twikey_client.refreshTokenIfRequired()

                invoice_uuid = str(uuid.uuid4())
                url = twikey_client.invoice.geturl(invoice_uuid)

                report_file = False
                credit_note_for = False
                if self.reversed_entry_id:
                    amount = -invoice_id.amount_total
                    credit_note_for = self.reversed_entry_id.name
                    remittance = _("CreditNote for %s") % self.reversed_entry_id.name
                else:
                    amount = invoice_id.amount_total
                    invoice_report = self.env.ref("account.account_invoices")
                    if self.include_pdf_invoice:
                        report_file = base64.b64encode(
                            self.env["ir.actions.report"]
                            .sudo()
                            ._render_qweb_pdf(invoice_report, [invoice_id.id], data=None)[0]
                        )
                    remittance = invoice_id.payment_reference

                try:
                    today = self.date.isoformat()
                    twikey_customer = get_twikey_customer(invoice_id.partner_id)
                    data = {
                        "id": invoice_uuid,
                        "number": invoice_id.name,
                        "title": invoice_id.name,
                        "ct": self.twikey_template_id.template_id_twikey,
                        "amount": amount,
                        "date": self.invoice_date.isoformat(),
                        "duedate": invoice_id.invoice_date_due.isoformat()
                        if invoice_id.invoice_date_due
                        else today,
                        "remittance": remittance,
                        "ref": invoice_id.id,
                        "locale": twikey_customer["l"] if twikey_customer else "en",
                        "customer": twikey_customer,
                    }

                    if not self.auto_collect_invoice:
                        data["manual"] = "true"

                    if report_file:
                        data["pdf"] = report_file.decode("utf-8")
                    else:
                        data["invoice_ref"] = credit_note_for

                    twikey_invoice = twikey_client.invoice.create(data)
                    invoice_id.with_context(update_feed=True).write({
                        "twikey_url": url,
                        "twikey_invoice_identifier": invoice_uuid,
                        "twikey_invoice_state": twikey_invoice.get("state")
                    })
                    return get_success_msg(f"Send {invoice_id.name} with state={self.twikey_invoice_state}")
                except TwikeyError as e:
                    errmsg = "Exception raised while creating a new Invoice:\n%s" % (e)
                    self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Invoices",body=errmsg,)
                    _logger.error(errmsg)
                    return get_error_msg(str(e), 'Exception raised while creating a new Invoice')
            else:
                _logger.info("Not sending to Twikey %s" % self)
        return res

    def update_invoice_feed(self):
        try:
            _logger.debug("Fetching Twikey updates")
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
            if twikey_client:
                twikey_client.invoice.feed(OdooInvoiceFeed(self.env))
        except TwikeyError as e:
            if e.error_code != "err_call_in_progress": # ignore parallel calls
                errmsg = "Exception raised while fetching updates:\n%s" % (e)
                self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Invoices",body=errmsg,)

    def update_twikey_state(self, state):
        try:
            _logger.debug("Updating Twikey of %s to %s" % (self, state))
            twikey_client = self.env["ir.config_parameter"].sudo().get_twikey_client(company=self.env.company)
            if twikey_client:
                twikey_client.invoice.update(self.twikey_invoice_id, {"status": state})
        except TwikeyError as ue:
            errmsg = "Error while updating invoice in Twikey: %s" % ue
            _logger.error(errmsg)
            self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Invoices",body=errmsg,)

    def write(self, values):
        """
        Set a default value for 'send_to_twikey' according to the standard rules. This
        is only done if move_type is changed into a type that doesn't have to be sent.
        """
        res = super(AccountInvoice, self).write(values)

        if "update_feed" in self._context:
            return res

        for record in self:
            if record.twikey_invoice_identifier and values.get("state"):
                if values.get("state") == "paid":
                    record.update_twikey_state("paid")
                elif values.get("state") == "cancel":
                    record.update_twikey_state("archived")
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """Set a default value for 'send_to_twikey' according to the standard rules."""
        for val in vals_list:
            if (
                val.is_twikey_eligable
                and not self._context.get("default_send_to_twikey")
                and val.get("send_to_twikey")
            ):
                val.send_to_twikey = True
            else:
                val.send_to_twikey = False
        return super().create(vals_list)

    @api.depends("move_type")
    def _compute_twikey_eligable(self):
        """
        Only certain types of account moves can be sent to Twikey.
        """
        for move in self:
            move.is_twikey_eligable = move.move_type in ["out_invoice", "out_refund"]

    def _default_twikey_send(self):
        return bool(self.get_default("twikey.send.invoice", True))

    def _default_include_pdf(self):
        return bool(self.get_default("twikey.send_pdf", False))

    def _default_auto_collect(self):
        return bool(self.get_default("twikey.auto_collect", True))

class OdooInvoiceFeed(InvoiceFeed):
    def __init__(self, env):
        self.env = env

    def process_states(self, invoice_id, twikey_invoice, new_state):
        _logger.info("Processing state for invoice: " + str(twikey_invoice))
        invoice_id.twikey_invoice_state = new_state
        if new_state == "PAID" and twikey_invoice["amount"] == invoice_id.amount_total:
            journals = self.env["account.journal"].search([("use_with_twikey", "=", True)])

            if len(journals) == 1:
                payment_method_line_twikey = journals.inbound_payment_method_line_ids.filtered(
                    lambda x: x.name == "Twikey" and x.payment_method_id.code == "manual"
                )

                if not payment_method_line_twikey:
                    payment_method_manual = self.env["account.payment.method"].search(
                        [("code", "=", "manual"), ("payment_type", "=", "inbound")]
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

                if twikey_invoice.get("lastpayment")[0].get("method") in ["sdd", "transfer"]:
                    iban = twikey_invoice.get("lastpayment")[0].get("iban")

                    # if we have an iban (customer might have done the payment twice of regular payment)
                    if twikey_invoice.get("customer") and twikey_invoice.get("customer").get("customerNumber"):
                        customer = self.env["res.partner"].browse(
                            [int(twikey_invoice.get("customer").get("customerNumber"))]
                        )

                        if customer and iban:
                            customer_bank_id = customer.bank_ids.filtered(lambda x: x.acc_number == iban)
                            if not customer_bank_id:
                                _logger.info("Linked customer: " + str(customer.name) + " and iban: " + str(iban))
                                self.env["res.partner.bank"].create({"partner_id": customer.id, "acc_number": iban})
                            else:
                                _logger.debug("Known customer: " + str(customer.name) + " and iban: " + str(iban))
                    else:
                        _logger.info("Unknown customer: " + str(twikey_invoice.get("customer")) )

                payment = (
                    self.env["account.payment.register"]
                    .with_context(active_model="account.move", active_ids=invoice_id.ids)
                    .create(
                        {
                            "journal_id": journals.id,
                            "payment_date": twikey_invoice["paydate"],
                            "payment_method_line_id": payment_method_line_twikey[0].payment_method_id.id,
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
                invoice_id.message_post(body=error_message)
                raise UserError(error_message)

    def invoice(self, _invoice):
        odoo_invoice_id = _invoice.get("ref")
        new_state = _invoice["state"]
        odoo_state = InvoiceStatus[new_state]

        try:
            lookup_id = int(odoo_invoice_id)
            _logger.debug("Got update for invoice=%d", lookup_id)
            invoice_id = self.env["account.move"].browse(lookup_id)
            if invoice_id.exists():
                self.process_states(invoice_id, _invoice, new_state)

                if invoice_id.payment_state == "paid":
                    try:
                        payment_reference = "unknown"
                        if "lastpayment" in _invoice and len(_invoice["lastpayment"]) > 0:
                            payment = _invoice["lastpayment"][0]
                            twikey_payment_method = payment["method"]
                            if twikey_payment_method == "paylink":
                                payment_reference = "paylink #{}".format(payment["link"])
                            elif twikey_payment_method == "sdd":
                                # Can be reversed
                                if "rc" in payment:
                                    payment_reference = "REVERSAL of Sepa Direct Debit pmtinf={} e2e={}".format(
                                        payment["pmtinf"],
                                        payment["e2e"],
                                    )
                                else:
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
                                payment_reference = "Regular transfer msg={}".format(payment["msg"])
                            elif twikey_payment_method == "manual":
                                payment_reference = "Manually set as paid msg={}".format(payment["msg"])
                            else:
                                payment_reference = "Other"

                        invoice_id.message_post(body="Twikey payment via " + payment_reference)
                    except Exception as e:
                        _logger.error("Error marking invoice as paid in odoo {}".format(e))
                        invoice_id.message_post(body=str(e))
                else:
                    number = _invoice.get("title")
                    _logger.info(f"Ignoring invoice update of {number} - {new_state}")

                invoice_id.with_context(update_feed=True).write({"state": odoo_state})
        except TwikeyError as te:
            errmsg = "Error while updating invoices :\n%s" % (te)
            self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Configuration",body=errmsg,)
            _logger.error(errmsg)
        except Exception as ue:
            _logger.error("Error while updating invoices from Twikey: %s" % ue)
