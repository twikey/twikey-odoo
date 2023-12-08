import base64
import logging
import uuid

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError
import psycopg2

from ..twikey.client import TwikeyError
from ..twikey.invoice import InvoiceFeed
from ..utils import get_twikey_customer, get_error_msg, get_success_msg

F_INCLUDE_PDF_INVOICE = "include_pdf_invoice"
F_AUTO_COLLECT_INVOICE = "auto_collect_invoice"
F_SEND_TO_TWIKEY = "send_to_twikey"

_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = "account.move"

    twikey_invoice_identifier = fields.Char(string="Twikey Invoice ID", help="Invoice ID of Twikey.", readonly=True, index=True, copy=False)
    twikey_template_id = fields.Many2one("twikey.contract.template", string="Twikey Profile")
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
    auto_collect_invoice = fields.Boolean(string="Collect the invoice if possible", readonly=False)
    include_pdf_invoice = fields.Boolean("Include pdf for invoices", help="Also send the invoice pdf to Twikey")

    twikey_url = fields.Char(string="Twikey Invoice URL", help="URL of the Twikey Invoice",
                             store=True, compute="_compute_twikey_url",)
    id_and_link_html = fields.Html(string="Twikey Invoice URL (html)",compute='_compute_link_html')

    is_twikey_eligable = fields.Boolean(
        string="Invoice or Creditnote",
        help="The account move can be sent to Twikey. The user can override this with field 'send_to_twikey'.",
        store=False,
        compute="_compute_twikey_eligable",
    )

    def btn_send_to_twikey(self):
        for record in self:
            if not record.is_twikey_eligable:
                return get_error_msg(f"Invoice {record.name} cannot be send to Twikey")
            record.send_to_twikey = True
        no_invoices = len(self)
        msg = f"Queued {no_invoices} invoices for delivery"
        _logger.info(msg)
        self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Prepare for sending", body = msg)
        return get_success_msg(msg)

    def send_invoices(self):
        """ Collect all invoices to be sent to twikey """
        twikey_client = (self.env["ir.config_parameter"].sudo().get_twikey_client(company=self.env.company))
        if twikey_client:
            # sometimes action_post gets called without an invoice record, in this case we don't try to
            # send anything to Twikey
            to_be_send = self.search([('company_id', '=', self.env.company.id), ('send_to_twikey', '=', True),('twikey_invoice_identifier','=',False),('state','=','posted')])
            if len(to_be_send) > 0:
                # ensure logged in otherwise company of url might not be filled in
                twikey_client.refreshTokenIfRequired()

            to_be_send.transfer_to_twikey(twikey_client)
        else:
            _logger.info("Not sending to Twikey as not configured")

    def transfer_to_twikey(self, twikeyClient):
        """ Actual sending of twikey """
        for invoice in self:

            # Handle as refund
            if invoice.is_purchase_document():
                if invoice.amount_total == 0:
                    invoice.message_post(body="Skipping sending to Twikey as no open amount.")
                    invoice.with_context(update_feed=True).write({"send_to_twikey": False})
                else:
                    partner_id = invoice.partner_id
                    customer_bank_id = partner_id.bank_ids.filtered((lambda p: p.allow_out_payment))
                    if len(customer_bank_id) > 0:
                        iban = customer_bank_id[0].sanitized_acc_number
                        if customer_bank_id[0].sequence != 20:
                            payload = get_twikey_customer(partner_id)
                            payload["iban"] = iban
                            if customer_bank_id[0].bank_id and customer_bank_id[0].bank_id.bic:
                                payload["bic"] = customer_bank_id[0].bank_id.bic
                            twikeyClient.refund.create_beneficiary_account(payload)
                            customer_bank_id[0].write({"sequence":20})
                            partner_id.message_post(body=f"Twikey beneficiary account to {iban} was added")

                        refund = twikeyClient.refund.create(partner_id.id,{
                            "iban": iban,
                            "message": invoice.payment_reference,
                            "amount":  invoice.amount_total,
                            "ref": invoice.name,
                        })

                        # make payment
                        self.env['account.payment.register'].with_context(
                            {"dont_redirect_to_payments":True},
                            active_model='account.move',active_ids=invoice.ids,).create({'payment_date': invoice.date,}).action_create_payments()

                        invoice.with_context(update_feed=True).write({
                            "twikey_invoice_identifier": refund["id"],
                        })
                    else:
                        invoice.message_post(body="Skipping sending to Twikey as no accounts allowing out_payments.")
                        invoice.with_context(update_feed=True).write({"send_to_twikey": False})
                continue

            if invoice.amount_residual == 0:
                invoice.with_context(update_feed=True).write({"send_to_twikey": False})
                invoice.message_post(body="Skipping sending to Twikey as no open amount.")
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
                    "duedate": invoice.invoice_date_due.isoformat() if invoice.invoice_date_due else today,
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
                    "twikey_invoice_state": twikey_invoice.get("state")
                }
                invoice.with_context(update_feed=True).write(new_state)
            except TwikeyError as e:
                errmsg = "Exception raised while sending %s to Twikey :\n%s" % (invoice.name, e)
                invoice.message_post(body=f"Exception raised while sending : {e}")
                self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Invoices",body=errmsg,)
                _logger.error(errmsg)
                return get_error_msg(str(e), 'Exception raised while creating a new Invoice')

    def update_invoice_feed(self, company = None):
        if not company:
            company = self.env.company
        try:
            # set lock on res_company to avoid duplicate calls
            self._cr.execute(f"""SELECT id FROM res_company WHERE id = %s FOR UPDATE NOWAIT""", [company.id], log_exceptions=False)
            _logger.debug(f"Fetching Twikey updates from {company.invoice_feed_pos}")
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=company)
            if twikey_client:
                twikey_client.invoice.feed(OdooInvoiceFeed(self.env,company), company.invoice_feed_pos,"meta","lastpayment")
        except TwikeyError as e:
            if e.error_code != "err_call_in_progress":  # ignore parallel calls
                errmsg = "Exception raised while fetching updates:\n%s" % (e)
                self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Invoices",body=errmsg,)
        except psycopg2.OperationalError:
            _logger.debug("Operation already ongoing")

    def update_twikey_state(self, state):
        try:
            _logger.debug("Updating Twikey of %s to %s" % (self, state))
            twikey_client = self.env["ir.config_parameter"].sudo().get_twikey_client(company=self.env.company)
            if twikey_client:
                twikey_client.invoice.update(self.twikey_invoice_identifier, {"status": state})
        except TwikeyError as ue:
            errmsg = "Error while updating invoice in Twikey: %s" % ue
            _logger.error(errmsg)
            self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Invoices", body=errmsg, )

    @api.model_create_multi
    def create(self, vals_list):
        """Set a default value for 'send_to_twikey' according to the standard rules."""

        for val in vals_list:
            if val.get("company_id"):
                company = self.env["res.company"].browse(val["company_id"])
            else:
                company = self.env.company
            twikey_send_invoice = company.twikey_send_invoice
            twikey_auto_collect = company.twikey_auto_collect
            twikey_send_pdf = company.twikey_send_pdf
            twikey_include_purchase = company.twikey_include_purchase
            if not val.get(F_SEND_TO_TWIKEY):
                val[F_SEND_TO_TWIKEY] =  twikey_send_invoice
            if not val.get(F_AUTO_COLLECT_INVOICE):
                val[F_AUTO_COLLECT_INVOICE] = twikey_auto_collect
            if not val.get(F_INCLUDE_PDF_INVOICE):
                val[F_INCLUDE_PDF_INVOICE] = twikey_send_pdf

            if val.get("move_type"):
                if val.get(F_SEND_TO_TWIKEY) and val.get("move_type") in ["out_invoice", "out_refund"]:
                    val[F_SEND_TO_TWIKEY] = twikey_send_invoice
                elif val.get("move_type") == "in_invoice":
                    val[F_SEND_TO_TWIKEY] = twikey_include_purchase
                else:
                    val[F_SEND_TO_TWIKEY] = False

            # _logger.info("Creating invoice : {}".format(val))
        return super().create(vals_list)

    def write(self, values):
        """
        Set a default value for 'send_to_twikey' according to the standard rules. This
        is only done if move_type is changed into a type that doesn't have to be sent.
        """
        res = super(AccountInvoice, self).write(values)
        # _logger.info("Updating {} : {}".format(self, values))
        if "update_feed" in self._context:
            return res

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
            if move.company_id.twikey_include_purchase:
                move.is_twikey_eligable = move.move_type in ["in_invoice", "out_invoice", "out_refund"]
            else:
                move.is_twikey_eligable = move.move_type in ["out_invoice", "out_refund"]

    @api.depends("twikey_invoice_identifier")
    def _compute_twikey_url(self):
        """
        Calculate the url of the invoice in Twikey.
        """
        try:
            for move in self.filtered("twikey_invoice_identifier"):
                twikey_client = self.env["ir.config_parameter"].sudo().get_twikey_client(company=move.company_id)
                move.twikey_url = twikey_client.invoice.geturl(move.twikey_invoice_identifier)
        except Exception as e:
            _logger.exception(e)

    @api.depends('twikey_invoice_identifier')
    def _compute_link_html(self):
        for record in self:
            # Generate the HTML link
            record.id_and_link_html = (
                f'<a href="{record.twikey_url}" target="twikey">{record.twikey_invoice_identifier}</a>'
                if record.twikey_invoice_identifier else False
            )

class OdooInvoiceFeed(InvoiceFeed):
    def __init__(self, env, company):
        self.env = env
        self.company = company
        self.channel = env['mail.channel'].search([('name', '=', 'twikey')])
        self.transaction = self.env['payment.transaction']
        self.account_move = self.env["account.move"]

    def start(self, position, number_of_invoices):
        _logger.info(f"Got new {number_of_invoices} invoice update(s) from start={position}")
        self.company.update({"invoice_feed_pos": position})

    def get_payment_description(self, last_payment):
        twikey_payment_method = last_payment.get("method")  # sdd/rcc/paylink/reporting/manual
        if twikey_payment_method == "paylink":
            payment_description = "paylink #{}".format(last_payment["link"])
        elif twikey_payment_method in ["sdd", "rcc"]:
            pmtinf = last_payment["pmtinf"]
            e2e = last_payment["e2e"]
            if twikey_payment_method == "sdd":
                payment_description = "Direct Debit pmtinf={} e2e={}".format(pmtinf, e2e, )
            else:
                payment_description = "Credit Card pmtinf={} e2e={}".format(pmtinf, e2e, )
        elif twikey_payment_method == "transfer":
            payment_description = "Regular transfer rep-{} msg={}".format(last_payment.get("id"), last_payment.get("msg"))
        elif twikey_payment_method == "manual":
            payment_description = "Manually set as paid msg={}".format(last_payment.get("msg"))
        else:
            payment_description = "Other"
        return payment_description

    def get_or_create_payment_transaction(self, txdict):
        tx = self.transaction.search([("provider_reference", "=", txdict['provider_reference'])], limit=1)
        if tx:
            return tx
        return self.transaction.create(txdict)

    def invoice(self, twikey_invoice):
        id = twikey_invoice.get("id")
        ref_id = twikey_invoice.get("ref")
        new_state = twikey_invoice["state"]
        last_payment = False
        if "lastpayment" in twikey_invoice and len(twikey_invoice["lastpayment"]) > 0:
            last_payment = twikey_invoice.get("lastpayment")[0]

        try:
            if ref_id and ref_id.isnumeric():
                invoice_id = self.account_move.browse(int(ref_id))
                if invoice_id.exists():
                    _logger.info("Processing invoice: " + str(twikey_invoice))
                    invoice_id.twikey_invoice_state = new_state
                    if new_state == "PAID":
                        if last_payment:
                            payment_description = self.get_payment_description(last_payment)

                            invoice_id.message_post(body="Incoming twikey payment via " + payment_description)
                            provider = self.env['payment.provider'].search([('code', '=', 'twikey')])[0]
                            token_id = False
                            if "mndtId" in last_payment:
                                search_mandate = [('provider_code', '=', provider.code),
                                       ('provider_ref', '=', last_payment["mndtId"])]
                                token_id = self.env['payment.token'].search(search_mandate,limit=1)
                            tx = self.get_or_create_payment_transaction({
                                'amount': twikey_invoice["amount"],
                                'currency_id': invoice_id.currency_id.id,
                                'provider_id': provider.id,
                                'token_id': token_id.id if token_id else False,
                                'reference': twikey_invoice["remittance"],
                                'provider_reference': id,
                                'operation': "offline",
                                'partner_id': invoice_id.partner_id.id,
                            })
                            tx.invoice_ids = [Command.set(invoice_id.ids)]
                            tx._set_done(payment_description)
                            tx._reconcile_after_done()
                            tx._finalize_post_processing()
                        else:
                            invoice_id.message_post(body=f"Unable to register payment as no last payment was found for payment_method={ref_id}")
                    elif new_state in ["BOOKED", "EXPIRED"]:
                        # Getting here means either a regular expiry or a reversal
                        if last_payment:
                            provider_reference = last_payment["e2e"]
                            tx = self.transaction.search([('provider_reference','=',id)])
                            if tx:
                                errorcode = "Failed with errorcode={}".format(last_payment["rc"])
                                tx._set_error(errorcode)
                                refund = tx._create_refund_transaction(amount_to_refund= tx.amount,
                                   provider_reference=id,
                                   invoice_ids = invoice_id.ids
                                )
                                # tx._set_error(errorcode) wont work as done can't be reverted
                                refund._set_done(errorcode)
                                refund._reconcile_after_done()
                                refund._finalize_post_processing()
                            else:
                                _logger.warning(f"payment.transaction with reference={provider_reference} not found")
                                invoice_id.message_post(body=f"payment.transaction with reference={provider_reference} not found")
                        else:
                            invoice_id.message_post(body=f"Unable to unregister payment as no last payment was found for payment_method={ref_id}")
                else:
                    _logger.debug(f"No invoice found with id={ref_id}")
            else:
                if last_payment:
                    payment_description = self.get_payment_description(last_payment)
                    tx = self.transaction.search([("provider_reference","=",id)],limit=1)
                    if tx:
                        if new_state == "PAID":
                            tx._set_done(payment_description)
                            tx._reconcile_after_done()
                            tx._finalize_post_processing()
                        elif new_state in ["BOOKED", "EXPIRED"]:
                            errorcode = "Failed with errorcode={}".format(last_payment["rc"])
                            tx._set_error(errorcode)
                            refund = tx._create_refund_transaction(provider_reference=id)
                            refund._set_done(errorcode)
                            refund._reconcile_after_done()
                            refund._finalize_post_processing()
                    else:
                        _logger.warning(f"Invalid invoice-ref={ref_id} ignoring")
        except TwikeyError as te:
            self.env.cr.rollback()
            errmsg = "Error while updating invoices :\n%s" % (te)
            self.channel.message_post(subject="Twikey problem while updating invoices",body=errmsg,message_type="comment")
            _logger.error("Error while updating invoices from Twikey: %s" % te)
            return te
        except UserError as ue:
            errmsg = "Skipping error while handing invoice=%s :\n%s" % (ref_id,ue)
            self.channel.message_post(subject="Odoo problem while updating invoices",body=errmsg,message_type="comment")
            _logger.exception("Skipping error while handling invoice with number=%s:\n%s", twikey_invoice.get("number"), ue)
            return False
        except Exception as ge:
            self.env.cr.rollback()
            errmsg = "Error while handing invoice=%s :\n%s" % (ref_id,ge)
            self.channel.message_post(subject="General problem while updating invoices",body=errmsg,message_type="comment")
            _logger.exception("Error while handling invoice with number=%s:\n%s", twikey_invoice.get("number"), ge)
            return ge
