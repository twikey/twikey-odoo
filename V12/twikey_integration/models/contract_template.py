# -*- coding: utf-8 -*-

from odoo import api, fields, models ,_


class ContractTemplate(models.Model):
    _name = 'contract.template'
    _description = "Contract Template for Mandate"
    
    name = fields.Char(string="Contract Template", required=True)
    template_id = fields.Integer(string="Template ID")
    active = fields.Boolean(string="Active", default=True)
    type = fields.Selection([('CORE', 'CORE'), ('B2B', 'B2B')], string="Type")
    attribute_ids = fields.One2many('contract.template.attribute', 'contract_template_id', string="Attributes")
    
    
class ContractTemplateAttribute(models.Model):
    _name = 'contract.template.attribute'
    _description = "Attributes for Contract Template"
    
    name = fields.Char(string="Contract Template Attribute")
    contract_template_id = fields.Many2one('contract.template', string="Contract Template")
    type = fields.Selection([('char','Text'),('integer','Number'),('float','Amount'),('selection','Select')])
    value_char = fields.Char(string="Attribute Value")
    value_sel = fields.Selection([('', '')], string="Value")