from odoo import _, exceptions, models, tools, service

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
                return False

            server_ver = service.common.exp_version()['server_version']
            module = self.env['ir.module.module'].sudo().search([('name', '=', 'twikey_integration')])
            twikey_ver = module and module.installed_version or ''
            return twikey.client.TwikeyClient(api_key, base_url, f'odoo/{server_ver} twikey/{twikey_ver}')
        else:
            raise exceptions.UserError(_("No company was set to get the Twikey credentials!"))
