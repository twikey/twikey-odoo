# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class success_message_wizard(models.TransientModel):
    _name="success.message.wizard"
    _description = "Message wizard to display warnings, alert ,success messages"
    
    def get_default(self):
        if self.env.context.get("message",False):
            return self.env.context.get("message")
        return False 

    name=fields.Text(string="Message", readonly=True, default=get_default)