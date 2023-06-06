import logging

from odoo import _, fields, models

from ..twikey.client import TwikeyError
from ..utils import get_error_msg, get_success_msg

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    twikey_api_key = fields.Char(related="company_id.twikey_api_key", help="Add Api Key from Twikey", readonly=False)
    twikey_base_url = fields.Char(related="company_id.twikey_base_url", readonly=False)

    def twikey_refresh_credentials(self):
        try:
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
            if twikey_client:
                twikey_client.refreshTokenIfRequired()
                self.__send_to_channel("Token refreshed!", )
                self.twikey_sync_contract_template()
            else:
                self.__send_to_channel("Invalid configuration")
        except TwikeyError as e:
            msg = 'Error connecting to {} : {}'.format(self.twikey_base_url, e.error)
            _logger.exception(msg)
            self.__send_to_channel(msg)

    def test_twikey_connection(self):
        """Button in the settings window"""
        if not self.twikey_api_key:
            return get_error_msg(_("Twikey API key not set!"))
        try:
            self.set_values()
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
            if twikey_client:
                twikey_client.refreshTokenIfRequired()
                self.__send_to_channel("Connection successful!")
                return get_success_msg(_('Connection successful'))
            else:
                return get_error_msg("Invalid configuration", False)
        except TwikeyError as e:
            msg = 'Error connecting to {} : {}'.format(self.twikey_base_url, e.error)
            _logger.exception(msg)
            self.__send_to_channel(msg)
            return get_error_msg(msg, True)

    def __send_to_channel(self, msg):
        self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Configuration", body=msg, )

    def twikey_sync_contract_template(self):
        if self.env["twikey.sync.contract.templates"].twikey_sync_contract_templates():
            return get_success_msg(_("Templates refreshed"))
        return get_error_msg(_("Templates NOT refreshed, check config."))
