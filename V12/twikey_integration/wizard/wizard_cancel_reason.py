# -*- coding: utf-8 -*-

from odoo import api, fields, models,_
import requests
import json
from odoo.exceptions import UserError


class MandateCancelReason(models.TransientModel):
    _name = 'mandate.cancel.reason'
    _description = "Add Reason for select contract template"
    
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
        base_url=self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.base_url')
        authorization_token=self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.authorization_token')
        if authorization_token:
            prepared_url = base_url + '/creditor/mandate' + '?mndtId=' + self.mandate_id.reference + '&rsn=' + self.name
            self.mandate_id.update_feed()
            if self.mandate_id.state != 'cancelled':
                response = requests.delete(prepared_url, headers={'Authorization' : authorization_token})
                if response.status_code == 200:
    #                 self.mandate_id.update_feed()
                    if self.mandate_id.state == 'signed':
                        self.mandate_id.write({'state' : 'cancelled', 'description' : self.name})
                    if self.mandate_id.state == 'pending':
                        self.mandate_id.unlink()
                        return self.env.ref('twikey_integration.mandate_details_action').read()[0]
                else:
                    resp_obj = response.json()
                    raise UserError(_('%s')
                                % (resp_obj.get('message')))
