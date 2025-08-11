import logging

import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..twikey.client import TwikeyError
from .odoo_document_feed import OdooDocumentFeed
from ..utils import field_name_from_attribute

_logger = logging.getLogger(__name__)


def _lang_get(self):
    return self.env["res.lang"].get_installed()


class TwikeyMandateDetails(models.Model):
    _name = "twikey.mandate.details"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Mandate details of Twikey"
    _rec_name = "partner_id"

    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("signed", "Signed"),
            ("suspended", "Suspended"),
            ("cancelled", "Cancelled"),
        ],
        default="pending",
        required=True,
    )
    reference = fields.Char(string="Mandate Reference", index=True)
    iban = fields.Char(string="IBAN")
    bic = fields.Char(string="BIC")
    template_id = fields.Many2one(
        comodel_name="twikey.contract.template", string="Profile", readonly=True
    )
    description = fields.Text()
    lang = fields.Selection(_lang_get, string="Language")
    url = fields.Char(string="URL", readonly=True)

    country_id = fields.Many2one("res.country")
    city = fields.Char()
    zip = fields.Char()
    address = fields.Char()

    def action_cancel_reason(self):
        self.ensure_one()
        wizard = self.env["mandate.cancel.reason"].create({"mandate_id": self.id})
        action = self.env.ref("payment_twikey.mandate_cancel_reason_action").read()[0]
        action["res_id"] = wizard.id
        return action

    @api.model
    def update_feed_by_cron(self):
        companies = self.env["res.company"].search([("activate_twikey", "=", True)])
        for company in companies:
            self.update_feed(company)

    def update_feed(self, company=None):
        if not company:
            company = self.env.company
        try:
            _logger.debug(
                f"Fetching Twikey updates from {company.sudo().mandate_feed_pos}"
            )
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(
                company=company
            )
            if twikey_client:
                twikey_client.document.feed(
                    OdooDocumentFeed(self.env, company), company.sudo().mandate_feed_pos
                )
        except TwikeyError as e:
            if e.error_code != "err_call_in_progress":  # ignore parallel calls
                errmsg = "Exception raised while fetching updates:\n%s" % e
                self.env["discuss.channel"].sudo().search(
                    [("name", "=", "twikey")]
                ).message_post(subject="Mandates", body=errmsg)

    def write(self, values):
        self.ensure_one()
        res = super().write(values)

        try:
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(
                company=self.env.company
            )
            if twikey_client:
                if not self._context.get("update_feed"):
                    data = {}
                    if self.state != "signed":
                        data["mndtId"] = (
                            values.get("reference")
                            if values.get("reference")
                            else self.reference
                        )
                        if "iban" in values:
                            data["iban"] = values.get("iban") or ""
                        if "bic" in values:
                            data["bic"] = values.get("bic")
                        if "lang" in values:
                            data["l"] = values.get("lang")
                        if "email" in values:
                            data["email"] = values.get("email")
                        if "mobile" in values:
                            data["mobile"] = values.get("mobile")

                        try:
                            if data != {}:
                                twikey_client.document.update(data)
                        except (Exception, requests.exceptions.RequestException) as e:
                            raise UserError(_("Error sending update: %s") % (str(e)))
            return res
        except TwikeyError as e:
            raise UserError from e

    def is_signed(self):
        return self.state == "signed"

    def is_creditcard(self):
        return self.template_id and self.template_id.type == "CREDITCARD"

    def get_attribute(self, name):
        ct = self.template_id.ct()
        return self.template_id and self[field_name_from_attribute(name, ct)]
