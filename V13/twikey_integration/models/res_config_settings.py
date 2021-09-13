# -*- coding: utf-8 -*-

from odoo import api, fields, models,exceptions,_
from odoo.exceptions import UserError
import logging
import requests
import json

_logger = logging.getLogger(__name__)

Field_Type = {'text': 'char',
              'number': 'integer',
              'amount': 'float',
              'select': 'selection',
              'plan': 'char',
              'email': 'char',
              'url': 'char',
              'checkbox': 'boolean',
              'iban': 'char',
              'multi': 'char'
              }

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    api_key = fields.Char(string="API Key", help="Add Api Key from Twikey")
    test = fields.Boolean(string="Test", help="Use Twikey Test environment")
    merchant_id = fields.Integer(string="Twikey ID", help="Your Twikey customer ID", readonly=True)
    module_twikey = fields.Boolean(string="Enable Twikey Integration", helgrp="Use for enable Twikey Integration")
    authorization_token = fields.Char(string="Authorization Token", help="Get from Twikey Authentication Scheduler and use for other APIs.")

    def authenticate(self, api_key=False):
        if not api_key:
            api_key = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.api_key')
        if api_key:
            base_url = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.base_url')
            _logger.debug('Authenticating to Twikey on %s with %s', base_url, api_key)
            try:
                response = requests.post(base_url + "/creditor", data={'apiToken': api_key})
                param = self.env['ir.config_parameter'].sudo()
                if response.headers['Authorization']:
                    param.set_param('twikey_integration.authorization_token', response.headers['Authorization'])
                    param.set_param('twikey_integration.merchant_id', response.headers['X-MERCHANT-ID'])
                    _logger.info(
                        'Authenticated to Twikey on %s twikey=%s' % (base_url, response.headers['X-MERCHANT-ID']))
                else:
                    _logger.error('Failed authenticating to Twikey on %s error=%s for apikey=%s' % (
                    base_url, response.headers['ApiError'], api_key))
            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
                    requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                _logger.error('Exception raised during Authentication %s' % (e))
                raise exceptions.AccessError(
                    _('The url that this service requested returned an error. Please check your connection or try after sometime.'))
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
                'twikey_integration.base_url') != 'https://api.twikey.com',
            # authorization_token=self.env['ir.config_parameter'].sudo().get_param(
            #     'twikey_integration.authorization_token'),
        )
        return res

    def set_values(self, test=True):
        super(ResConfigSettings, self).set_values()
        param = self.env['ir.config_parameter'].sudo()

        api_key = self.api_key or False
        testmode = self.test or False
        module_twikey = self.module_twikey or False
        # authorization_token = self.authorization_token or False

        base_url = 'https://api.twikey.com'
        if testmode:
            base_url = 'https://api.beta.twikey.com'

        param.set_param('twikey_integration.api_key', api_key)
        param.set_param('twikey_integration.base_url', base_url)
        param.set_param('twikey_integration.module_twikey', module_twikey)
        # param.set_param('twikey_integration.authorization_token', authorization_token)

    @api.model
    def create(self, values):
        res = super(ResConfigSettings, self).create(values)

        if res and values.get('api_key'):
            self.authenticate(values.get('api_key'))
        res.set_values(values['test'])
        return res

    def sync_contract_template(self):
        module_twikey = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.module_twikey')
        if module_twikey:
            authorization_token = self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.authorization_token')
            base_url = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.base_url')
            if authorization_token:
                try:
                    response = requests.get(base_url + "/creditor/template",
                                            headers={'Authorization': authorization_token})
                    _logger.debug('Fetching contract template data %s' % (response.content))
                    if response.status_code == 200:
                        resp_obj = response.json()
                        twikey_temp_list = []
                        template_ids = self.env['contract.template'].search([('active', 'in', [True, False])])
                        temp_list = []
                        _logger.info("Retrieved %d templates from Twikey", len(resp_obj))
                        for temp in template_ids:
                            temp_list.append(temp.template_id)
                        for resp in resp_obj:
                            twikey_temp_list.append(resp.get('id'))
                            template_id = self.env['contract.template'].search(
                                [('template_id', '=', resp.get('id')), ('active', 'in', [True, False])])
                            if not template_id:
                                template_id = self.env['contract.template'].create(
                                    {'template_id': resp.get('id'), 'name': resp.get('name'),
                                     'active': resp.get('active'), 'type': resp.get('type'),
                                     'mandateNumberRequired': resp.get('mandateNumberRequired')})
                            if resp.get('Attributes') != []:
                                fields_list = []
                                mandate_field_list = []
                                for attr in resp.get('Attributes'):
                                    select_list = []
                                    field_type = attr.get('type')
                                    if field_type == 'select':
                                        if attr.get('Options') != []:
                                            for select in attr.get('Options'):
                                                select_list.append((str(select), str(select)))
                                        else:
                                            _logger.warning("Skipping attribute %s as selection without options",
                                                            attr.get('name'))
                                            continue
                                    model_id = self.env['ir.model'].search(
                                        [('model', '=', 'contract.template.wizard')])
                                    mandate_model_id = self.env['ir.model'].search(
                                        [('model', '=', 'mandate.details')])
                                    search_fields = self.env['ir.model.fields'].sudo().search(
                                        [('name', '=', 'x_' + attr.get('name') + '_' + str(resp.get('id'))),
                                         ('model_id', '=', model_id.id)])
                                    search_mandate_fields = self.env['ir.model.fields'].sudo().search(
                                        [('name', '=', 'x_' + attr.get('name') + '_' + str(resp.get('id'))),
                                         ('model_id', '=', mandate_model_id.id)])
                                    if not search_fields and field_type != 'iban':
                                        ir_fields = self.env['ir.model.fields'].sudo().create(
                                            {'name': 'x_' + attr.get('name') + '_' + str(resp.get('id')),
                                             'field_description': attr.get('description'),
                                             'model_id': model_id.id,
                                             'ttype': Field_Type[field_type],
                                             #                                                       'required': attr.get('mandatory'),
                                             'store': True,
                                             'readonly': attr.get('readonly'),
                                             'selection': str(select_list) if select_list != [] else '',
                                             })
                                        fields_list.append(ir_fields)
                                    if not search_mandate_fields and field_type != 'iban':
                                        mandate_fields = self.env['ir.model.fields'].sudo().create(
                                            {'name': 'x_' + attr.get('name') + '_' + str(resp.get('id')),
                                             'field_description': attr.get('description'),
                                             'model_id': mandate_model_id.id,
                                             'ttype': Field_Type[field_type],
                                             #                                                       'required': attr.get('mandatory'),
                                             'store': True,
                                             'readonly': attr.get('readonly'),
                                             'selection': str(select_list) if select_list != [] else '',
                                             })
                                        mandate_field_list.append(mandate_fields)
                                    attr_vals = {'contract_template_id': template_id.template_id,
                                                 'name': attr.get('name'),
                                                 'type': Field_Type[attr.get('type')]}
                                    if template_id.attribute_ids:
                                        # for attrs in template_id.attribute_ids:
                                        if attr.get('name') not in template_id.attribute_ids.mapped('name'):
                                            template_id.write({'attribute_ids': [(0, 0, attr_vals)]})
                                    else:
                                        template_id.write({'attribute_ids': [(0, 0, attr_vals)]})
                                inherit_id = self.env.ref(
                                    'twikey_integration.contract_template_wizard_view_twikey_form')
                                if fields_list != []:
                                    arch_base = _('<?xml version="1.0"?>'
                                                  '<data>'
                                                  '<field name="template_id" position="after">')
                                    for f in fields_list:
                                        if attr.get('mandatory'):
                                            arch_base += '''<field name="%s" attrs="{'invisible': [('template_id', '!=', %s)], 'required': [('template_id', '=', %s)]}"/>''' % (
                                            f.name, template_id.id, template_id.id)
                                        else:
                                            arch_base += '''<field name="%s" attrs="{'invisible': [('template_id', '!=', %s)]}"/>''' % (
                                            f.name, template_id.id)

                                    arch_base += _('</field>'
                                                   '</data>')
                                    self.env['ir.ui.view'].sudo().create({'name': 'attribute.dynamic.fields.',
                                                                          'type': 'form',
                                                                          'model': 'contract.template.wizard',
                                                                          'mode': 'extension',
                                                                          'inherit_id': inherit_id.id,
                                                                          'arch_base': arch_base,
                                                                          'active': True})

                                inherit_mandate_id = self.env.ref(
                                    'twikey_integration.mandate_details_view_twikey_form')
                                if mandate_field_list != []:
                                    mandate_arch_base = _('<?xml version="1.0"?>'
                                                          '<data>'
                                                          '<field name="url" position="after">')
                                    for m in mandate_field_list:
                                        if attr.get('mandatory'):
                                            mandate_arch_base += '''<field name="%s" attrs="{'invisible': [('contract_temp_id', '!=', %s)], 'required': [('contract_temp_id', '=', %s)]}"/>''' % (
                                            m.name, template_id.id, template_id.id)
                                        else:
                                            mandate_arch_base += '''<field name="%s" attrs="{'invisible': [('contract_temp_id', '!=', %s)]}"/>''' % (
                                            m.name, template_id.id)
                                    mandate_arch_base += _('</field>'
                                                           '</data>')
                                    self.env['ir.ui.view'].sudo().create({'name': 'mandate.dynamic.fields.',
                                                                          'type': 'form',
                                                                          'model': 'mandate.details',
                                                                          'mode': 'extension',
                                                                          'inherit_id': inherit_mandate_id.id,
                                                                          'arch_base': mandate_arch_base,
                                                                          'active': True})
                        diff_list = []
                        for temp_diff in temp_list:
                            if temp_diff not in twikey_temp_list:
                                diff_list.append(temp_diff)
                                if diff_list != []:
                                    for a in diff_list:
                                        template_ids = self.env['contract.template'].search(
                                            [('template_id', '=', a), ('active', 'in', [True, False])])
                                        if template_ids:
                                            template_ids.unlink()
                except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
                        requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                    _logger.error('Exception raised while fetching Contract Templates %s' % (e))
                    raise exceptions.AccessError(
                        _('The url that this service requested returned an error. Please check your connection or try after sometime.'))
