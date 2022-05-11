# -*- coding: utf-8 -*-

from odoo import api, fields, models,_
import requests
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class MandateCancelReason(models.TransientModel):
    _name = 'mandate.cancel.reason'
    _description = "Add Reason for select contract template"
    
    @api.model
    def default_get(self, fields):
        res = super(MandateCancelReason, self).default_get(fields)
        context = self.env.context
        if 'active_id' in context:
            res.update({'mandate_id': context.get('active_id')})
        return res
    
    name = fields.Text(string="Reason for Cancellation", required=True)
    mandate_id = fields.Many2one('mandate.details')
    
    def action_cancel_confirm(self):
        twikey_client = self.env['ir.config_parameter'].get_twikey_client()
        twikey_client.document.cancel(self.mandate_id.reference,self.name)
        self.mandate_id.update_feed()

