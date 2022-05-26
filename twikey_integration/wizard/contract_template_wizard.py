# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions, _
import requests
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

language_dict = {'en_US':'en', 'fr_FR':'fr', 'nl_NL':'nl', 'de_DE':'de', 'pt_PT':'pt', 'es_ES':'es', 'it_IT':'it'}

class ContractTemplateWizard(models.Model):

    _name = 'contract.template.wizard'
    _description = "Wizard for Select Contract Template"
    
    name = fields.Char(string="Name")
    template_id = fields.Many2one('twikey.contract.template', string="Contract Template")
    attribute_ids = fields.One2many(related="template_id.attribute_ids", readonly=False)
    
    def action_confirm(self):
        context = self._context
        customer = self.env['res.partner'].browse(context.get('active_id'))
        language = customer.lang
        contractData = {
            'ct': self.template_id.template_id,
            'l': language_dict.get(language),
            'customerNumber': customer.id,
            'mandateNumber': customer.id if self.template_id.mandateNumberRequired == False else '',
            'mobile': customer.mobile if customer.mobile else '',
            'address': customer.street if customer.street else '',
            'city': customer.city if customer.city else '',
            'zip': customer.zip if customer.zip else '',
            'country': customer.country_id.code if customer.country_id else '',
        }
        if customer.email:
            contractData["email"] = customer.email
            contractData["sendInvite"] = True
        if customer.company_type == 'company' and customer.name:
            contractData["companyName"] = customer.name
            contractData["coc"] = customer.vat
        elif customer.name: # 'person'
            customer_name = customer.name.split(' ')
            if customer_name and len(customer_name) > 1:
                contractData["firstname"] = customer_name[0]
                contractData["lastname"] = ' '.join(customer_name[1:])
            else:
                contractData["firstname"] = customer.name

        lst =[]
        sp_lst = []
        attr_list = []
        for attr in self.template_id.attribute_ids:
            attr_list.append(attr.name)
            sp_lst.append('x_'+attr.name+ '_' +str(self.template_id.template_id))
        for name,field in self._fields.items():
            if name in sp_lst or name == 'template_id':
                # if name.startswith('x_') or name == 'template_id':
                lst.append(name)
        get_fields = self.read(fields=lst, load='_classic_read')
        if get_fields:
            template_id = False
            if get_fields[0].get('template_id'):
                template_id = get_fields[0].get('template_id')[0]
            get_template_id = self.env['twikey.contract.template'].browse(template_id)
            get_fields[0].pop("id")
            get_fields[0].pop("template_id")
            new_keys = []
            for key,value in get_fields[0].items():
                model_id = self.env['ir.model'].search([('model', '=', 'contract.template.wizard')])
                field_id = self.env['ir.model.fields'].search([('name', '=', key), ('model_id', '=', model_id.id)])
                if field_id.ttype != 'boolean' and value == False:
                    get_fields[0].update({key : ''})
                key_split = key.split('_')
                if len(key_split) > 0:
                    new_keys.append(key_split[1])
            final_dict = dict(zip(new_keys, list(get_fields[0].values())))
            contractData.update(final_dict)
        try:
            _logger.debug('New mandate creation data: {}'.format(contractData))
            twikey_client = self.env['ir.config_parameter'].get_twikey_client()
            twikey_client.refreshTokenIfRequired()
            response = requests.post(
                twikey_client.api_base + "/creditor/invite",
                data=contractData,
                headers=twikey_client.headers()
            )
            _logger.info('Creating new mandate with response: %s' % (response.content))
            resp_obj = response.json()
            if response.status_code != 200:
                raise UserError(_('%s') % (resp_obj.get('message')))
            mandate_id = self.env['mandate.details'].sudo().create({
                'contract_temp_id' : get_template_id.id,
                'lang' : customer.lang,
                'partner_id' : customer.id,
                'reference' : resp_obj.get('mndtId'),
                'url' : resp_obj.get('url')
            })
            mandate_id.with_context(update_feed=True).write(get_fields[0])
            view = self.env.ref('twikey_integration.success_message_wizard')
            context = dict(self._context or {})
            context['message'] = "Mandate Created Successfully."
            return {
                'name': 'Success',
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'success.message.wizard',
                'views': [(view.id, 'form')],
                'view_id': view.id,
                'target': 'new',
                'context': context
            }
        except (ValueError, requests.exceptions.RequestException) as e:
            _logger.error('Exception raised while creating a new Mandate %s' % (e))
            raise exceptions.AccessError(_('The url that this service requested returned an error. Please check your connection or try after sometime.'))
