import base64
import logging
import uuid

from odoo import _, api, fields, models
import psycopg2

from odoo.exceptions import UserError
from ..twikey.client import TwikeyError
from .odoo_invoice_feed import OdooInvoiceFeed
from ..utils import get_twikey_customer, get_error_msg, get_success_msg

F_INCLUDE_PDF_INVOICE = "include_pdf_invoice"
F_AUTO_COLLECT_INVOICE = "auto_collect_invoice"
F_SEND_TO_TWIKEY = "send_to_twikey"

_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = "account.move"

    twikey_invoice_identifier = fields.Char(
        string="Twikey Invoice ID",
        help="Invoice ID of Twikey.",
        readonly=True,
        index=True,
        copy=False,
    )
    twikey_template_id = fields.Many2one(
        "twikey.contract.template", string="Twikey Profile"
    )
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

    send_to_twikey = fields.Boolean(string="Send to Twikey", readonly=False)
    auto_collect_invoice = fields.Boolean(
        string="Collect the invoice if possible", readonly=False
    )
    include_pdf_invoice = fields.Boolean(
        "Include pdf for invoices", help="Also send the invoice pdf to Twikey"
    )

    twikey_url = fields.Char(
        string="Twikey Invoice URL",
        help="URL of the Twikey Invoice",
        store=True,
        compute="_compute_twikey_url",
    )
    id_and_link_html = fields.Html(string="HTML link ID", compute="_compute_link_html")

    is_twikey_eligable = fields.Boolean(
        string="Invoice or Creditnote",
        help="The account move can be sent to Twikey. The user can override this with field 'send_to_twikey'.",
        store=False,
        compute="_compute_twikey_eligable",
    )

    def btn_send_to_twikey(self):
        """
        Queued invoices by marking then as to be sent to Twikey.
        They will be sent later on by a job.
        """
        for record in self:
            company = record.company
            if not company.sudo().activate_twikey:
                raise UserError(
                    _("Twikey is not activated for company %s") % company.name
                )
            if not record.is_twikey_eligable:
                return get_error_msg(f"Invoice {record.name} cannot be send to Twikey")
            record.send_to_twikey = True
            record.message_post(body="Queued for delivery to Twikey")
        no_invoices = len(self)
        msg = f"Queued {no_invoices} invoices for delivery"
        _logger.info(msg)
        self.env["discuss.channel"].sudo().search(
            [("name", "=", "twikey")]
        ).message_post(subject="Prepare for sending", body=msg)
        return get_success_msg(msg)

    @api.model
    def send_invoices_by_cron(self):
        companies = self.env["res.company"].search([("activate_twikey", "=", True)])
        for company in companies:
            self.with_company(company).send_invoices(cron=True)

    def send_invoices(self, cron=False):
        """Collect all invoices to be sent to twikey"""
        twikey_client = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_twikey_client(company=self.env.company)
        )
        if twikey_client:
            # sometimes action_post gets called without an invoice record, in this case we don't try to
            # send anything to Twikey
            to_be_send = self.search(
                [
                    ("send_to_twikey", "=", True),
                    ("twikey_invoice_identifier", "=", False),
                    ("state", "=", "posted"),
                ]
            )
            if len(to_be_send) > 0:
                # ensure logged in otherwise company of url might not be filled in
                twikey_client.refreshTokenIfRequired()

            to_be_send.transfer_to_twikey(twikey_client, cron=cron)
        else:
            _logger.info("Not sending to Twikey as not configured")

    def transfer_to_twikey(self, twikeyClient, cron=False):
        """Actual sending of twikey"""
        for invoice in self:
            # Handle as refund
            if invoice.is_purchase_document():
                if invoice.amount_total == 0:
                    invoice.message_post(
                        body="Skipping sending to Twikey as no open amount."
                    )
                    invoice.with_context(update_feed=True).write(
                        {"send_to_twikey": False}
                    )
                else:
                    partner_id = invoice.partner_id
                    customer_banks = partner_id.bank_ids.filtered(
                        lambda p: p.allow_out_payment
                    )
                    if len(customer_banks) > 0:
                        iban = customer_banks[0].sanitized_acc_number
                        if customer_banks[0].sequence != 20:
                            payload = get_twikey_customer(partner_id)
                            payload["iban"] = iban
                            if (
                                customer_banks[0].bank_id
                                and customer_banks[0].bank_id.bic
                            ):
                                payload["bic"] = customer_banks[0].bank_id.bic
                            twikeyClient.refund.create_beneficiary_account(payload)
                            customer_banks[0].write({"sequence": 20})
                            partner_id.message_post(
                                body=f"Twikey beneficiary account to {iban} was added"
                            )

                        refund = twikeyClient.refund.create(
                            partner_id.id,
                            {
                                "iban": iban,
                                "message": invoice.payment_reference,
                                "amount": invoice.amount_total,
                                "ref": invoice.name,
                            },
                        )

                        # make payment
                        payment = (
                            self.env["account.payment.register"]
                            .with_context(
                                {"dont_redirect_to_payments": True},
                                active_model="account.move",
                                active_ids=invoice.ids,
                            )
                            .create(
                                {
                                    "payment_date": invoice.date,
                                }
                            )
                        )
                        payment.action_create_payments()

                        invoice.with_context(update_feed=True).write(
                            {
                                "twikey_invoice_identifier": refund["id"],
                            }
                        )
                    else:
                        invoice.message_post(
                            body="Skipping sending to Twikey as no accounts allowing out_payments."
                        )
                        invoice.with_context(update_feed=True).write(
                            {"send_to_twikey": False}
                        )
                continue

            if invoice.amount_residual == 0:
                invoice.with_context(update_feed=True).write({"send_to_twikey": False})
                invoice.message_post(
                    body="Skipping sending to Twikey as no open amount."
                )
                continue

            invoice_uuid = str(uuid.uuid4())

            report_file = False
            credit_note_for = False
            if invoice.reversed_entry_id:
                amount = -invoice.amount_total
                credit_note_for = invoice.reversed_entry_id.name
                remittance = _("CreditNote for %s") % invoice.reversed_entry_id.name
            else:
                amount = invoice.amount_total
                invoice_report = self.env.ref("account.account_invoices")
                if invoice.include_pdf_invoice:
                    report_file = base64.b64encode(
                        self.env["ir.actions.report"]
                        .sudo()
                        ._render_qweb_pdf(invoice_report, [invoice.id], data=None)[0]
                    )
                remittance = invoice.payment_reference

            try:
                today = invoice.date.isoformat()
                twikey_customer = get_twikey_customer(invoice.partner_id)
                data = {
                    "id": invoice_uuid,
                    "number": invoice.name,
                    "title": invoice.name,
                    "ct": invoice.twikey_template_id.template_id_twikey,
                    "amount": amount,
                    "date": invoice.invoice_date.isoformat(),
                    "duedate": (
                        invoice.invoice_date_due.isoformat()
                        if invoice.invoice_date_due
                        else today
                    ),
                    "remittance": remittance,
                    "ref": invoice.id,
                    "locale": twikey_customer["l"] if twikey_customer else "en",
                    "customer": twikey_customer,
                }

                if not invoice.auto_collect_invoice:
                    data["manual"] = "true"

                if invoice.is_purchase_document():
                    data["refund"] = "try"

                if report_file:
                    data["pdf"] = report_file.decode("utf-8")
                if credit_note_for:
                    data["relatedInvoiceNumber"] = credit_note_for

                twikey_invoice = twikeyClient.invoice.create(data, "Odoo")
                new_state = {
                    "twikey_invoice_identifier": invoice_uuid,
                    "twikey_invoice_state": twikey_invoice.get("state"),
                }

                invoice.message_post(body="Delivered to Twikey")
                invoice.with_context(update_feed=True).write(new_state)
            except TwikeyError as e:
                errmsg = "Exception raised while sending %s to Twikey :\n%s" % (
                    invoice.name,
                    e,
                )
                invoice.message_post(body=f"Exception raised while sending : {e}")
                self.env["discuss.channel"].sudo().search(
                    [("name", "=", "twikey")]
                ).message_post(
                    subject="Invoices",
                    body=errmsg,
                )
                _logger.error(errmsg)
                if not cron:
                    return get_error_msg(
                        str(e), "Exception raised while creating a new Invoice"
                    )

    @api.model
    def update_invoice_feed_by_cron(self):
        companies = self.env["res.company"].search([("activate_twikey", "=", True)])
        for company in companies:
            self.update_invoice_feed(company)

    def update_invoice_feed(self, company=None):
        if not company:
            company = self.env.company
        try:
            # set lock on res_company to avoid duplicate calls
            self._cr.execute(
                """SELECT id FROM res_company WHERE id = %s FOR UPDATE NOWAIT""",
                [company.id],
                log_exceptions=False,
            )
            _logger.debug(
                f"Fetching Twikey updates from {company.sudo().invoice_feed_pos}"
            )
            twikey_client = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_twikey_client(company=company)
            )
            if twikey_client:
                twikey_client.invoice.feed(
                    OdooInvoiceFeed(self.env, company),
                    company.sudo().invoice_feed_pos,
                    "meta",
                    "lastpayment",
                )
        except TwikeyError as e:
            if e.error_code != "err_call_in_progress":  # ignore parallel calls
                errmsg = "Exception raised while fetching updates:\n%s" % (e)
                self.env["discuss.channel"].sudo().search(
                    [("name", "=", "twikey")]
                ).message_post(
                    subject="Invoices",
                    body=errmsg,
                )
        except psycopg2.OperationalError:
            _logger.debug("Operation already ongoing")

    def update_twikey_state(self, state):
        try:
            _logger.debug("Updating Twikey of %s to %s" % (self, state))
            twikey_client = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_twikey_client(company=self.env.company)
            )
            if twikey_client:
                twikey_client.invoice.update(
                    self.twikey_invoice_identifier, {"status": state}
                )
        except TwikeyError as ue:
            errmsg = "Error while updating invoice in Twikey: %s" % ue
            _logger.error(errmsg)
            self.env["discuss.channel"].sudo().search(
                [("name", "=", "twikey")]
            ).message_post(
                subject="Invoices",
                body=errmsg,
            )

    @api.model_create_multi
    def create(self, vals_list):
        """Set a default value for 'send_to_twikey' according to the standard rules."""

        if self.env.company.sudo().activate_twikey:
            twikey_send_invoice = self.env.company.sudo().twikey_send_invoice
            twikey_auto_collect = self.env.company.sudo().twikey_auto_collect
            twikey_send_pdf = self.env.company.sudo().twikey_send_pdf
            twikey_include_purchase = self.env.company.sudo().twikey_include_purchase

            for val in vals_list:
                if not val.get(F_SEND_TO_TWIKEY):
                    val[F_SEND_TO_TWIKEY] = twikey_send_invoice
                if not val.get(F_AUTO_COLLECT_INVOICE):
                    val[F_AUTO_COLLECT_INVOICE] = twikey_auto_collect
                if not val.get(F_INCLUDE_PDF_INVOICE):
                    val[F_INCLUDE_PDF_INVOICE] = twikey_send_pdf

                if val.get("move_type"):
                    if val.get(F_SEND_TO_TWIKEY) and val.get("move_type") in [
                        "out_invoice",
                        "out_refund",
                    ]:
                        val[F_SEND_TO_TWIKEY] = twikey_send_invoice
                    elif val.get("move_type") == "in_invoice":
                        val[F_SEND_TO_TWIKEY] = twikey_include_purchase
                    else:
                        val[F_SEND_TO_TWIKEY] = False
        return super().create(vals_list)

    def write(self, values):
        """
        Set a default value for 'send_to_twikey' according to the standard rules. This
        is only done if move_type is changed into a type that doesn't have to be sent.
        """
        res = super().write(values)
        if (
            not self.env.context.get("update_feed", False)
            and self.env.company.sudo().activate_twikey
        ):
            for record in self:
                if record.twikey_invoice_identifier and values.get("state"):
                    if values.get("state") == "paid":
                        record.update_twikey_state("paid")
                    elif values.get("state") == "cancel":
                        record.update_twikey_state("archived")
        return res

    @api.depends("move_type")
    def _compute_twikey_eligable(self):
        """
        Only certain types of account moves can be sent to Twikey.
        """
        for move in self:
            company = move.company_id or self.env.company
            if not company.sudo().activate_twikey:
                move.is_twikey_eligable = False
            elif move.company_id.sudo().twikey_include_purchase:
                move.is_twikey_eligable = move.move_type in [
                    "in_invoice",
                    "out_invoice",
                    "out_refund",
                ]
            else:
                move.is_twikey_eligable = move.move_type in [
                    "out_invoice",
                    "out_refund",
                ]

    @api.depends("twikey_invoice_identifier")
    def _compute_twikey_url(self):
        """
        Calculate the url of the invoice in Twikey.
        """
        if self.env.company.sudo().activate_twikey:
            try:
                twikey_client = (
                    self.env["ir.config_parameter"]
                    .sudo()
                    .get_twikey_client(company=self.env.company)
                )
                for move in self:
                    if move.twikey_invoice_identifier:
                        move.twikey_url = twikey_client.invoice.geturl(
                            move.twikey_invoice_identifier
                        )
            except Exception as e:
                _logger.exception(e)

    @api.depends("twikey_invoice_identifier")
    def _compute_link_html(self):
        if self.env.company.sudo().activate_twikey:
            for record in self:
                # Generate the HTML link
                record.id_and_link_html = (
                    f'<a href="{record.twikey_url}" '
                    f'target="twikey">{record.twikey_invoice_identifier}</a>'
                )
        else:
            self.id_and_link_html = False
