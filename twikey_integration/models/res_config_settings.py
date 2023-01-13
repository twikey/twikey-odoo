import requests

from odoo import _, exceptions, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    twikey_api_key = fields.Char(
        related="company_id.twikey_api_key", help="Add Api Key from Twikey", readonly=False
    )
    twikey_base_url = fields.Char(related="company_id.twikey_base_url", readonly=False)

    def twikey_authenticate(self):
        twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)

        if self.twikey_api_key:
            self.set_values()
            try:
                twikey_client.refreshTokenIfRequired()
                raise UserError(_("Authentication successful!"))
            except (ValueError, requests.exceptions.RequestException) as e:
                raise exceptions.AccessError(
                    _(
                        "The connection to Twikey failed. Please check your connection or try after sometime."
                        "\nError code: "
                    )
                    + str(e)
                )
        else:
            raise UserError(_("API key not set!"))

    def test_twikey_connection(self):
        try:
            self.twikey_authenticate()
            self.set_values()
            self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
            raise UserError(_("Connection succeeded!"))
        except (ValueError, requests.exceptions.RequestException) as e:
            raise exceptions.AccessError(
                _(
                    "The connection to Twikey failed. Please check your connection or try after sometime."
                    "\nError code: "
                )
                + str(e)
            )

    def twikey_sync_contract_template(self):
        self.env["sync.contract.templates"].twikey_sync_contract_templates()
