from odoo import _, exceptions, models, tools

from .. import twikey


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @tools.ormcache("company")
    def get_twikey_client(self, company):
        """
        Cache automatically cleared because of the ir.config_parameter model
        """
        if company:
            api_key = company.twikey_api_key
            base_url = company.twikey_base_url
            if not api_key or not base_url:
                raise exceptions.UserError(message=_("Twikey not configured!"))
            return twikey.client.TwikeyClient(api_key, base_url, "twikey-odoo-15/v0.1.0")
        else:
            raise exceptions.UserError(_("No company set!"))
