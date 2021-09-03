# -*- coding: utf-8 -*-

from odoo import api, fields, models ,_


class ContractTemplate(models.Model):
    _name = 'contract.template'
    _description = "Contract Template for Mandate"
    
    name = fields.Char(string="Contract Template", required=True)
    template_id = fields.Integer(string="Template ID")
    active = fields.Boolean(string="Active", default=True)

    # Avoids err_mandatenumber_required so mandateNumber parameter should be in the invite call
    mandateNumberRequired = fields.Boolean(string="MandateNumberRequired", default=True)
    type = fields.Selection([('CORE', 'CORE'), ('B2B', 'B2B'), ('CODA', 'CODA'), ('CONTRACT', 'CONTRACT'), ('CONSENT', 'CONSENT'), ('IDENT', 'IDENT'), ('CREDITCARD', 'CREDITCARD'), ('WIK', 'WIK'), ('PAYROLL', 'PAYROLL')], string="Type")
    attribute_ids = fields.One2many('contract.template.attribute', 'contract_template_id', string="Attributes")

    _sql_constraints = [('template_id_unique', 'unique(template_id)', 'Already Exist!')]
    
    
class ContractTemplateAttribute(models.Model):
    _name = 'contract.template.attribute'
    _description = "Attributes for Contract Template"
    
    name = fields.Char(string="Contract Template Attribute")
    contract_template_id = fields.Many2one('contract.template', string="Contract Template")
    type = fields.Selection([('char','Text'),('integer','Number'),('boolean','Boolean'),('float','Amount'),('selection','Select')])
