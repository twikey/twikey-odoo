# -*- coding: utf-8 -*-

from odoo import api, fields, models,_
import requests
import json
from odoo.exceptions import UserError


class MandateCancelReason(models.TransientModel):
    _name = 'mandate.cancel.reason'
    
    @api.model
    def default_get(self, fields):
        res = super(MandateCancelReason, self).default_get(fields)
        context = self.env.context
        if 'active_id' in context:
            res.update({'mandate_id' : context.get('active_id')})
        return res
    
    name = fields.Text(string="Reason for Cancellation", required=True)
    mandate_id = fields.Many2one('mandate.details')
    
    def action_cancel_confirm(self):
        context = self.env.context
        host_url = 'https://api.beta.twikey.com/creditor/mandate'
        authorization_token=self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.authorization_token')
        prepared_url = host_url + '?mndtId=' + self.mandate_id.reference + '&rsn=' + self.name
        response = requests.delete(prepared_url, headers={'Authorization' : authorization_token})
        if response.status_code == 200:
            self.mandate_id.write({'state' : 'cancelled', 'description' : self.name})
        else:
            resp_obj = json.loads(response.content)
            raise UserError(_('%s')
                        % (resp_obj.get('message')))
