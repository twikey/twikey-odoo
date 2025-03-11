import logging
from ..twikey.client import TwikeyError
from ..twikey.invoice import InvoiceFeed
from odoo import Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OdooInvoiceFeed(InvoiceFeed):
    def __init__(self, env, company):
        self.env = env
        self.company = company
        self.channel = env["discuss.channel"].search([("name", "=", "twikey")]).sudo()
        self.transaction = self.env["payment.transaction"]
        self.account_move = self.env["account.move"]

    def start(self, position, number_of_invoices):
        _logger.info(
            f"Got new {number_of_invoices} invoice update(s) from start={position}"
        )
        self.company.sudo().update({"invoice_feed_pos": position})

    def get_payment_description(self, last_payment):
        twikey_payment_method = last_payment.get(
            "method"
        )  # sdd/rcc/paylink/reporting/manual
        if twikey_payment_method == "paylink":
            payment_description = "paylink #{}".format(last_payment["link"])
        elif twikey_payment_method in ["sdd", "rcc"]:
            pmtinf = last_payment["pmtinf"]
            e2e = last_payment["e2e"]
            if twikey_payment_method == "sdd":
                payment_description = "Direct Debit pmtinf={} e2e={}".format(
                    pmtinf,
                    e2e,
                )
            else:
                payment_description = "Credit Card pmtinf={} e2e={}".format(
                    pmtinf,
                    e2e,
                )
        elif twikey_payment_method == "transfer":
            payment_description = "Regular transfer rep-{} msg={}".format(
                last_payment.get("id"), last_payment.get("msg")
            )
        elif twikey_payment_method == "manual":
            payment_description = "Manually set as paid msg={}".format(
                last_payment.get("msg")
            )
        else:
            payment_description = "Other"
        return payment_description

    def get_or_create_payment_transaction(self, txdict):
        tx = self.transaction.search(
            [("provider_reference", "=", txdict["provider_reference"])], limit=1
        )
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
                            payment_description = self.get_payment_description(
                                last_payment
                            )

                            invoice_id.message_post(
                                body="Incoming twikey payment via "
                                + payment_description
                            )
                            provider = self.env["payment.provider"].search(
                                [("code", "=", "twikey")]
                            )[0]
                            token_id = False
                            if "mndtId" in last_payment:
                                search_mandate = [
                                    ("provider_code", "=", provider.code),
                                    ("provider_ref", "=", last_payment["mndtId"]),
                                ]
                                token_id = self.env["payment.token"].search(
                                    search_mandate, limit=1
                                )
                            tx = self.get_or_create_payment_transaction(
                                {
                                    "amount": twikey_invoice["amount"],
                                    "currency_id": invoice_id.currency_id.id,
                                    "provider_id": provider.id,
                                    "token_id": token_id.id if token_id else False,
                                    "reference": twikey_invoice["remittance"],
                                    "provider_reference": id,
                                    "operation": "offline",
                                    "partner_id": invoice_id.partner_id.id,
                                }
                            )
                            tx.invoice_ids = [Command.set(invoice_id.ids)]
                            tx._set_done(payment_description)
                            tx._reconcile_after_done()
                            tx._finalize_post_processing()
                        else:
                            invoice_id.message_post(
                                body=f"Unable to register payment as no last "
                                f"payment was found for payment_method={ref_id}"
                            )
                    elif new_state in ["BOOKED", "EXPIRED"]:
                        # Getting here means either a regular expiry or a reversal
                        if last_payment:
                            provider_reference = last_payment["e2e"]
                            tx = self.transaction.search(
                                [("provider_reference", "=", id)]
                            )
                            if tx:
                                errorcode = "Failed with errorcode={}".format(
                                    last_payment["rc"]
                                )
                                tx._set_error(errorcode)
                                refund = tx._create_refund_transaction(
                                    amount_to_refund=tx.amount,
                                    provider_reference=id,
                                    invoice_ids=invoice_id.ids,
                                )
                                # tx._set_error(errorcode) wont work as done can't be reverted
                                refund._set_done(errorcode)
                                refund._reconcile_after_done()
                                refund._finalize_post_processing()
                            else:
                                _logger.warning(
                                    f"payment.transaction with reference={provider_reference} not found"
                                )
                                invoice_id.message_post(
                                    body=f"payment.transaction with reference={provider_reference} not found"
                                )
                        else:
                            invoice_id.message_post(
                                body=f"Unable to unregister payment as no "
                                f"last payment was found for payment_method={ref_id}"
                            )
                else:
                    _logger.debug(f"No invoice found with id={ref_id}")
            else:
                if last_payment:
                    payment_description = self.get_payment_description(last_payment)
                    tx = self.transaction.search(
                        [("provider_reference", "=", id)], limit=1
                    )
                    if tx:
                        if new_state == "PAID":
                            tx._set_done(payment_description)
                            tx._reconcile_after_done()
                            tx._finalize_post_processing()
                        elif new_state in ["BOOKED", "EXPIRED"]:
                            errorcode = "Failed with errorcode={}".format(
                                last_payment["rc"]
                            )
                            tx._set_error(errorcode)
                            refund = tx._create_refund_transaction(
                                provider_reference=id
                            )
                            refund._set_done(errorcode)
                            refund._reconcile_after_done()
                            refund._finalize_post_processing()
                    else:
                        _logger.warning(f"Invalid invoice-ref={ref_id} ignoring")
        except TwikeyError as te:
            self.env.cr.rollback()
            errmsg = "Error while updating invoices :\n%s" % (te)
            self.channel.message_post(
                subject="Twikey problem while updating invoices",
                body=errmsg,
                message_type="comment",
            )
            _logger.error("Error while updating invoices from Twikey: %s" % te)
            return te
        except UserError as ue:
            errmsg = "Skipping error while handing invoice=%s :\n%s" % (ref_id, ue)
            self.channel.message_post(
                subject="Odoo problem while updating invoices",
                body=errmsg,
                message_type="comment",
            )
            _logger.exception(
                "Skipping error while handling invoice with number=%s:\n%s",
                twikey_invoice.get("number"),
                ue,
            )
            return False
        except Exception as ge:
            self.env.cr.rollback()
            errmsg = "Error while handing invoice=%s :\n%s" % (ref_id, ge)
            self.channel.message_post(
                subject="General problem while updating invoices",
                body=errmsg,
                message_type="comment",
            )
            _logger.exception(
                "Error while handling invoice with number=%s:\n%s",
                twikey_invoice.get("number"),
                ge,
            )
            return ge
