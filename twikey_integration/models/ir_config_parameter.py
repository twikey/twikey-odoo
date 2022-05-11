from odoo import models, exceptions,_

from .. import twikey

_twikey_client = None


class IrConfigParameter(models.Model):

    _inherit = 'ir.config_parameter'

    def get_twikey_api_key(self):
        icp_sudo = self.sudo()
        api_key = icp_sudo.get_param('twikey_integration.api_key')
        if not api_key:
            raise exceptions.UserError(_('Please configure Twikey first'))
        return api_key

    def get_twikey_client(self, force=False):
        global _twikey_client
        if not _twikey_client or force:
            icp_sudo = self.sudo()
            api_key = self.get_twikey_api_key()
            base_url = icp_sudo.get_param('twikey_integration.base_url')
            _twikey_client = twikey.client.TwikeyClient(api_key, base_url, "twikey-odoo-12/v0.1.0")
        return _twikey_client
