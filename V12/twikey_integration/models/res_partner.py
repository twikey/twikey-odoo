# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, exceptions, _
import requests
import json
from odoo.exceptions import UserError

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


class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    twikey_reference = fields.Char(string="Twikey Reference", copy = False, help="Twikey Customer Number will be save in this field.")
    mandate_ids = fields.One2many('mandate.details', 'partner_id', string="Mandates")
    twikey_inv_ids = fields.One2many('account.invoice', 'partner_id', readonly=True, copy=False,
                                  compute='_compute_invoice_ids')

    def _compute_invoice_ids(self):
        for res in self:
            flt_invoice = res.invoice_ids.filtered(lambda x: x.type == 'out_invoice' and x.twikey_invoice_id != False)
            res.twikey_inv_ids = [(6, 0, [x.id for x in flt_invoice])]

    def action_invite_customer(self):
        module_twikey = self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.module_twikey')
        if module_twikey:
            authorization_token=self.env['ir.config_parameter'].sudo().get_param(
                    'twikey_integration.authorization_token')
            base_url=self.env['ir.config_parameter'].sudo().get_param(
                    'twikey_integration.base_url')
            if authorization_token:
                try:
                    response = requests.get(base_url+"/creditor/template", headers={'Authorization' : authorization_token})
                    if response.status_code == 200:
                        resp_obj = response.json()
                        twikey_temp_list = []
                        template_ids = self.env['contract.template'].search([('active', 'in', [True, False])])
                        temp_list = []
                        _logger.info("Retrieved %d templates from Twikey",len(resp_obj))
                        for temp in template_ids:
                            temp_list.append(temp.template_id)
                        for resp in resp_obj:
                            twikey_temp_list.append(resp.get('id'))
                            template_id = self.env['contract.template'].search([('template_id', '=', resp.get('id')),('active', 'in', [True, False])])
                            if not template_id:
                                template_id = self.env['contract.template'].create({'template_id' : resp.get('id'), 'name' : resp.get('name'), 'active' : resp.get('active'), 'type' : resp.get('type'),'mandateNumberRequired': resp.get('mandateNumberRequired')})
                            if resp.get('Attributes') != []:
                                fields_list = []
                                mandate_field_list = []
                                for attr in resp.get('Attributes'):
                                    select_list = []
                                    field_type = attr.get('type')
                                    if field_type == 'select':
                                        if attr.get('Options') != []:
                                            for select in attr.get('Options'):
                                                select_list.append((str(select),str(select)))
                                        else:
                                            _logger.warn("Skipping attribute %s as selection without options",attr.get('name'))
                                            continue
                                    model_id = self.env['ir.model'].search([('model', '=', 'contract.template.wizard')])
                                    mandate_model_id = self.env['ir.model'].search([('model', '=', 'mandate.details')])
                                    search_fields = self.env['ir.model.fields'].sudo().search([('name', '=', 'x_' + attr.get('name')+'_'+str(resp.get('id'))), ('model_id', '=', model_id.id)])
                                    search_mandate_fields = self.env['ir.model.fields'].sudo().search([('name', '=', 'x_' + attr.get('name')+'_'+str(resp.get('id'))), ('model_id', '=', mandate_model_id.id)])
                                    if not search_fields and field_type != 'iban':
                                        ir_fields = self.env['ir.model.fields'].sudo().create({'name': 'x_' + attr.get('name')+'_'+str(resp.get('id')),
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
                                        mandate_fields = self.env['ir.model.fields'].sudo().create({'name': 'x_' + attr.get('name')+'_'+str(resp.get('id')),
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
                                inherit_id = self.env.ref('twikey_integration.contract_template_wizard_view_twikey_form')
                                if fields_list != []:
                                    arch_base = _('<?xml version="1.0"?>'
                                                 '<data>'
                                                 '<field name="template_id" position="after">')
                                    for f in fields_list:
                                        if attr.get('mandatory'):
                                            arch_base += '''<field name="%s" attrs="{'invisible': [('template_id', '!=', %s)], 'required': [('template_id', '=', %s)]}"/>''' %(f.name, template_id.id, template_id.id)
                                        else:
                                            arch_base += '''<field name="%s" attrs="{'invisible': [('template_id', '!=', %s)]}"/>''' %(f.name, template_id.id)
                                        
    
                                    arch_base += _('</field>'
                                                '</data>')
                                    view = self.env['ir.ui.view'].sudo().create({'name': 'attribute.dynamic.fields.',
                                                                         'type': 'form',
                                                                         'model': 'contract.template.wizard',
                                                                         'mode': 'extension',
                                                                         'inherit_id': inherit_id.id,
                                                                         'arch_base': arch_base,
                                                                         'active': True})
    
                                inherit_mandate_id = self.env.ref('twikey_integration.mandate_details_view_twikey_form')
                                if mandate_field_list != []:
                                    mandate_arch_base = _('<?xml version="1.0"?>'
                                                 '<data>'
                                                 '<field name="url" position="after">')
                                    for m in mandate_field_list:
                                        if attr.get('mandatory'):
                                            mandate_arch_base += '''<field name="%s" attrs="{'invisible': [('contract_temp_id', '!=', %s)], 'required': [('contract_temp_id', '=', %s)]}"/>''' % (m.name, template_id.id, template_id.id)
                                        else:
                                            mandate_arch_base += '''<field name="%s" attrs="{'invisible': [('contract_temp_id', '!=', %s)]}"/>''' % (m.name, template_id.id)
                                    mandate_arch_base += _('</field>'
                                                '</data>')
                                    view = self.env['ir.ui.view'].sudo().create({'name': 'mandate.dynamic.fields.',
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
                                        template_ids = self.env['contract.template'].search([('template_id','=',a),('active', 'in', [True, False])])
                                        if template_ids:
                                            template_ids.unlink()
    
                    action = self.env.ref('twikey_integration.contract_template_wizard_action').read()[0]
                    return action
                except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
                    requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                    _logger.error("Error retrieving template",e)
                    raise exceptions.AccessError(
                        _(
                            'The url that this service requested returned an error. Please check your connection or try after sometime.')
                    )
            else:
                raise UserError(_("Authorization Token Not Found, Please Run Authenticate Twikey Scheduled Actions Manually!!!"))
        else:
            raise UserError(_('Please enable Twikey integration from Settings.'))
    
    @api.multi
    def write(self, values):
        res = super(ResPartner, self).write(values)
        authorization_token = self.env['ir.config_parameter'].sudo().get_param(
            'twikey_integration.authorization_token')
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'twikey_integration.base_url')

        customer_name = ''
        if self.company_type == 'person':
            if values.get('name'):
                customer_name = values.get('name').split(' ')
            else:
                customer_name = self.name.split(' ')
        country_id = False
        if values.get('country_id'):
            country_id = self.env['res.country'].browse(values.get('country_id'))

        data = {
                'email': values.get('email') if values.get('email') else self.email if self.email else '',
                'firstname': customer_name[0] if customer_name and self.company_type == 'person' else '',
                'lastname': customer_name[1] if customer_name and len(
                    customer_name) > 1 and self.company_type == 'person' else '',
                'companyName': values.get('name') if values.get(
                    'name') and self.company_type == 'company' else self.name if self.company_type == 'company' else '',
                'vatno': values.get('vat') if values.get(
                    'vat') and self.company_type == 'company' else self.vat if self.vat and self.company_type == 'company' else '',
                'customerNumber': int(values.get('twikey_reference')) if values.get('twikey_reference') else int(
                    self.twikey_reference) if self.twikey_reference else '',
                'address': values.get('street') if values.get('street') else self.street if self.street else '',
                'city': values.get('city') if values.get('city') else self.city if self.city else '',
                'zip': values.get('zip') if values.get('zip') else self.zip if self.zip else '',
                'country': country_id.code if country_id != False else self.country_id.code if self.country_id else ''
                }
        if self.mandate_ids:
            mandate_id = self.mandate_ids[0]
            data.update({'mndtId': mandate_id.reference})
            try:
                response = requests.post(base_url + "/creditor/mandate/update", data=data,
                                         headers={'Authorization': authorization_token})
                if response.status_code != 204:
                    raise UserError(_('%s')
                                    % (response.json().get('message')))
            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
                    requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                raise exceptions.AccessError(
                    _(
                        'The url that this service requested returned an error. Please check your connection or try after sometime.')
                )
        # else:
        #     if self.twikey_inv_ids:
        #         twikey_inv_id = self.twikey_inv_ids[0]
        #         try:
        #             response = requests.put(base_url+'/creditor/invoice/%s'%twikey_inv_id.twikey_invoice_id, data=data, headers={'authorization' : authorization_token, 'Content-Type': 'application/json'})
        #             if response.status_code != 200:
        #                 raise UserError(_('%s')
        #                                 % (response.json().get('message')))
        #         except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
        #                 requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
        #             raise exceptions.AccessError(
        #                 _(
        #                     'The url that this service requested returned an error. Please check your connection or try after sometime.')
        #             )
        return res
