# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, exceptions, _
import requests
import json
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    twikey_reference = fields.Char(string="Twikey Reference", help="Twikey Customer Number will be save in this field.")
    
    def action_invite_customer(self):
        module_twikey = self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.module_twikey')
        if module_twikey:
            authorization_token=self.env['ir.config_parameter'].sudo().get_param(
                    'twikey_integration.authorization_token')
            data = {'ct' : 2833,
                    'customerNumber' : self.id,
                    'firstname' : self.name.split(' ')[0] if self.name and self.company_type == 'person' else '',
                    'lastname' : self.name.split(' ')[1] if self.name and self.company_type == 'person' else '',
                    'email' : self.email if self.email else '',
                    'mobile' : self.mobile if self.mobile else self.phone if self.phone else '',
                    'address' : self.street if self.street else '',
                    'city' : self.city if self.city else '',
                    'zip' : self.zip if self.zip else '',
                    'country' : self.country_id.name if self.country_id else '',
                    'companyName' : self.name if self.company_type == 'company' else '',
                    'vatno' : self.vat if self.company_type == 'company' else ''
                }
            try:
                response = requests.post("https://api.beta.twikey.com/creditor/invite", data=data, headers={'Authorization' : authorization_token})
                resp_obj = json.loads(response.content)
                if response.status_code == 200:
                    mandate_id = self.env['mandate.details'].sudo().create({'lang' : self.lang, 'partner_id' : self.id, 'reference' : resp_obj.get('mndtId'), 'url' : resp_obj.get('url')})
                    self.write({'twikey_reference' : str(self.id)})
                else:
                    raise UserError(_('%s')
                                % (resp_obj.get('message')))
            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                raise exceptions.AccessError(
                    _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                )
        else:
            raise UserError(_('Please enable Twikey integration from Settings.'))
        
        
        
        