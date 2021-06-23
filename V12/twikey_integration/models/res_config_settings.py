# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions,_
from odoo.exceptions import UserError
import requests
import json
import logging

_logger = logging.getLogger(__name__)

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    api_key = fields.Char(string="API Key", help="Add Api Key from Twikey")
    test = fields.Boolean(string="Test", help="Use Twikey Test environment")
    module_twikey = fields.Boolean(string="Enable Twikey Integration", help="Use for enable Twikey Integration")
    authorization_token = fields.Char(string="Authorization Token", help="Get from Twikey Authentication Scheduler and use for other APIs.")

    def authenticate(self, api_key=False):
        if not api_key:
            api_key = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.api_key')
        if api_key:
            base_url = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.base_url')
            _logger.info('Authenticating to Twikey on %s with %s',base_url, api_key)
            try:
                response = requests.post(base_url+"/creditor", data={'apiToken':api_key})
                _logger.info('Response from Authentication %s' % (response.content))
                param = self.env['ir.config_parameter'].sudo()
                if response.status_code == 200:
                    param.set_param('twikey_integration.authorization_token', json.loads(response.text).get('Authorization'))
            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                _logger.info('Exception raised during Authentication %s' % (e))
                raise exceptions.AccessError(
                _('The url that this service requested returned an error. Please check your connection or try after sometime.')
            )        
        else:
            raise UserError('Please Add Twikey Api Key from Settings.')

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        res.update(
            api_key=self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.api_key'),
            module_twikey=self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.module_twikey'),
            test=self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.test'),
        )
        return res

    def set_values(self, test=True):
        super(ResConfigSettings, self).set_values()
        param = self.env['ir.config_parameter'].sudo()
        api_key = self.api_key or False
        testmode = test
        module_twikey = self.module_twikey or False
        authorization_token = self.authorization_token or False

        base_url = 'https://api.twikey.com'
        if testmode:
            base_url = 'https://api.beta.twikey.com'

        param.set_param('twikey_integration.api_key', api_key)
        param.set_param('twikey_integration.test', testmode)
        param.set_param('twikey_integration.base_url', base_url)
        param.set_param('twikey_integration.module_twikey', module_twikey)


    @api.model
    def create(self, values):
        res = super(ResConfigSettings, self).create(values)
        self.set_values(values['test'])
        if res and values.get('api_key'):
            self.authenticate(values.get('api_key'))
        return res
