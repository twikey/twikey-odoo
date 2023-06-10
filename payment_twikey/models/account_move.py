import base64
import logging
import uuid

from odoo import _, api, fields, models,Command
from odoo.exceptions import UserError

from ..twikey.client import TwikeyError
from ..twikey.invoice import InvoiceFeed
from ..utils import get_twikey_customer, get_error_msg, get_success_msg

_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = "account.move"

    twikey_url = fields.Char(string="Twikey Invoice URL", help="URL of the Twikey Invoice", readonly=True)
    twikey_invoice_identifier = fields.Char(string="Twikey Invoice ID", help="Invoice ID of Twikey.", readonly=True)
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

    send_to_twikey = fields.Boolean(string="Send to Twikey",
                                    default=lambda self: self._default_twikey_send, readonly=False)
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

        twikey_client = (self.env["ir.config_parameter"].sudo().get_twikey_client(company=self.env.company))
        if twikey_client:
            for invoice_id in self:
                if invoice_id.is_twikey_eligable and invoice_id.send_to_twikey:

                    # ensure logged in otherwise company of url might not be filled in
                    twikey_client.refreshTokenIfRequired()

                    invoice_uuid = str(uuid.uuid4())
                    url = twikey_client.invoice.geturl(invoice_uuid)

                    report_file = False
                    credit_note_for = False
                    if invoice_id.reversed_entry_id:
                        amount = -invoice_id.amount_total
                        credit_note_for = invoice_id.reversed_entry_id.name
                        remittance = _("CreditNote for %s") % invoice_id.reversed_entry_id.name
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
                        today = invoice_id.date.isoformat()
                        twikey_customer = get_twikey_customer(invoice_id.partner_id)
                        data = {
                            "id": invoice_uuid,
                            "number": invoice_id.name,
                            "title": invoice_id.name,
                            "ct": self.twikey_template_id.template_id_twikey,
                            "amount": amount,
                            "date": invoice_id.invoice_date.isoformat(),
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
            _logger.debug(f"Fetching Twikey updates from {self.env.company.invoice_feed_pos}")
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
            if twikey_client:
                twikey_client.invoice.feed(OdooInvoiceFeed(self.env), self.env.company.invoice_feed_pos)
        except TwikeyError as e:
            if e.error_code != "err_call_in_progress":  # ignore parallel calls
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
            self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Invoices", body=errmsg, )

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
            if not val.get("send_to_twikey"):
                val["send_to_twikey"] = bool(self.get_default("twikey.send.invoice", True))
            if not val.get("auto_collect_invoice"):
                val["auto_collect_invoice"] = bool(self.get_default("twikey.auto_collect", True))
            if not val.get("include_pdf_invoice"):
                val["include_pdf_invoice"] = bool(self.get_default("twikey.send_pdf", False))

            if val.get("move_type"):
                if val.get("send_to_twikey") and val.get("move_type") in ["out_invoice", "out_refund"]:
                    val["send_to_twikey"] = True
                else:
                    val["send_to_twikey"] = False
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

    def start(self, position, number_of_invoices):
        _logger.info(f"Got new {number_of_invoices} invoice update(s) from start={position}")
        self.env.company.update({
            "invoice_feed_pos": position
        })

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
            payment_description = "Regular transfer rep-{} msg={}".format(last_payment["id"], last_payment["msg"])
        elif twikey_payment_method == "manual":
            payment_description = "Manually set as paid msg={}".format(last_payment["msg"])
        else:
            payment_description = "Other"
        return payment_description

    def get_or_create_payment_transaction(self, txdict):
        tx = self.env['payment.transaction'].search([("provider_ref", "=", txdict['provider_ref'])], limit=1)
        if tx:
            return tx
        return self.env['payment.transaction'].create(txdict)

    def invoice(self, twikey_invoice):
        id = twikey_invoice.get("id")
        ref_id = twikey_invoice.get("ref")
        new_state = twikey_invoice["state"]
        last_payment = False
        if "lastpayment" in twikey_invoice and len(twikey_invoice["lastpayment"]) > 0:
            last_payment = twikey_invoice.get("lastpayment")[0]

        try:
            if ref_id.isnumeric():
                invoice_id = self.env["account.move"].browse(int(ref_id))
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
                                token_id = self.env['payment.token'].search([('provider_code', '=', provider.code),('provider_ref', '=', last_payment["mndtId"])])
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
                            tx = self.env['payment.transaction'].search([('provider_reference','=',id)])
                            if tx:
                                errorcode = "Failed with errorcode={}".format(last_payment["rc"])
                                tx._set_error(errorcode)
                                refund = tx._create_refund_transaction(provider_reference=id)
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
                    tx = self.env['payment.transaction'].search([("provider_reference","=",id)],limit=1)
                    if tx:
                        if new_state == "PAID":
                            tx._set_done(payment_description)
                            tx._reconcile_after_done()
                            tx._finalize_post_processing()
                        elif new_state in ["BOOKED", "EXPIRED"]:
                            errorcode = "Failed with errorcode={}".format(last_payment["rc"])
                            tx._set_error(errorcode)
                            refund = tx._create_refund_transaction(acquirer_reference=id)
                            refund._set_done(errorcode)
                            refund._reconcile_after_done()
                            refund._finalize_post_processing()
                    else:
                        _logger.warning(f"Invalid invoice-ref={ref_id} ignoring")
        except TwikeyError as te:
            self.env.cr.rollback()
            errmsg = "Error while updating invoices :\n%s" % (te)
            self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Twikey problem while updating invoices",body=errmsg,message_type="comment")
            _logger.error("Error while updating invoices from Twikey: %s" % te)
            return te
        except UserError as ue:
            errmsg = "Skipping error while handing invoice=%s :\n%s" % (ref_id,ue)
            self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Odoo problem while updating invoices",body=errmsg,message_type="comment")
            _logger.exception("Skipping error while handling invoice with number=%s:\n%s", twikey_invoice.get("number"), ue)
            return False
        except Exception as ge:
            self.env.cr.rollback()
            errmsg = "Error while handing invoice=%s :\n%s" % (ref_id,ge)
            self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="General problem while updating invoices",body=errmsg,message_type="comment")
            _logger.exception("Error while handling invoice with number=%s:\n%s", twikey_invoice.get("number"), ge)
            return ge
