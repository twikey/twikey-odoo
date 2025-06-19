import logging

from odoo import _, api, fields, models

from ..twikey.client import TwikeyError
from ..utils import get_error_msg, get_success_msg

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    activate_twikey = fields.Boolean(
        string="Activate Twikey", related="company_id.activate_twikey", readonly=False
    )
    twikey_base_url = fields.Char(
        string=" Twikey API url", related="company_id.twikey_base_url", readonly=False
    )
    twikey_api_key = fields.Char(
        string="Twikey API key",
        related="company_id.twikey_api_key",
        help="Add Api Key from Twikey",
        readonly=False,
        groups="base.group_system",
    )

    twikey_send_invoice = fields.Boolean(
        string="Send all invoices",
        related="company_id.twikey_send_invoice",
        readonly=False,
        default=True,
    )
    twikey_auto_collect = fields.Boolean(
        string="Auto-Collect",
        related="company_id.twikey_auto_collect",
        readonly=False,
        default=True,
    )
    twikey_include_purchase = fields.Boolean(
        string="Send purchase invoices",
        related="company_id.twikey_include_purchase",
        readonly=False,
    )
    twikey_send_pdf = fields.Boolean(
        string="Include PDF", related="company_id.twikey_send_pdf", readonly=False
    )

    @api.onchange("activate_twikey")
    def _onchange_reset_twikey_parameters(self):
        if not self.activate_twikey:
            self.twikey_base_url = False
            self.twikey_api_key = False
            self.twikey_send_invoice = False
            self.twikey_auto_collect = False
            self.twikey_include_purchase = False
            self.twikey_send_pdf = False

    def get_values(self):
        res = super().get_values()
        company = self.env.company.sudo()
        res.update(
            twikey_send_invoice=company.sudo().twikey_send_invoice,
            twikey_auto_collect=company.sudo().twikey_auto_collect,
            twikey_include_purchase=company.sudo().twikey_include_purchase,
            twikey_send_pdf=company.sudo().twikey_send_pdf,
        )
        return res

    @api.model
    def twikey_refresh_credentials_by_cron(self):
        companies = self.env["res.company"].search([("activate_twikey", "=", True)])
        for company in companies:
            self.with_company(company).twikey_refresh_credentials()

    def twikey_refresh_credentials(self):
        try:
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(
                company=self.env.company
            )
            if twikey_client:
                twikey_client.refreshTokenIfRequired()
                self.__send_to_channel(
                    "Token refreshed!",
                )
                self.twikey_sync_contract_template()
            else:
                self.__send_to_channel("Invalid configuration")
        except TwikeyError as e:
            msg = "Error connecting to {} : {}".format(self.twikey_base_url, e.error)
            _logger.exception(msg)
            self.__send_to_channel(msg)

    def test_twikey_connection(self):
        """Button in the settings window"""
        if not self.twikey_api_key:
            return get_error_msg(_("Twikey API key not set!"))
        try:
            self.set_values()
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(
                company=self.env.company
            )
            if twikey_client:
                twikey_client.refreshTokenIfRequired()
                self.__send_to_channel("Connection successful!")
                return get_success_msg(_("Connection successful"))
            else:
                return get_error_msg("Invalid configuration", False)
        except TwikeyError as e:
            msg = "Error connecting to {} : {}".format(self.twikey_base_url, e.error)
            _logger.exception(msg)
            self.__send_to_channel(msg)
            return get_error_msg(msg, True)

    def __send_to_channel(self, msg):
        self.env["discuss.channel"].sudo().search(
            [("name", "=", "twikey")]
        ).message_post(
            subject="Configuration",
            body=msg,
        )

    def twikey_sync_contract_template(self):
        if self.env["twikey.sync.contract.templates"].twikey_sync_contract_templates():
            return get_success_msg(_("Templates refreshed"))
        return get_error_msg(_("Templates NOT refreshed, check config."))
