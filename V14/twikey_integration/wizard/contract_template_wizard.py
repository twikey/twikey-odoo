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
    template_id = fields.Many2one('contract.template', string="Contract Template")
    attribute_ids = fields.One2many(related="template_id.attribute_ids", readonly=False)
    
    def action_confirm(self):
        context = self._context

        partner_id = self.env['res.partner'].browse(context.get('active_id'))
        language = partner_id.lang
        base_url=self.env['ir.config_parameter'].sudo().get_param(
                    'twikey_integration.base_url')
        authorization_token=self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.authorization_token')
        data = {'ct' : self.template_id.template_id,
            'l': language_dict.get(language),
            'sendInvite' : True,
            'customerNumber' : partner_id.id,
            'mandateNumber': partner_id.id if self.template_id.mandateNumberRequired == False else '',
            'firstname' : partner_id.name.split(' ')[0] if partner_id.name and partner_id.company_type == 'person' else '',
            'lastname' : partner_id.name.split(' ')[1] if partner_id.name and len(partner_id.name.split(' ')) > 1 and partner_id.company_type == 'person' else '',
            'email' : partner_id.email if partner_id.email else '',
            'mobile' : partner_id.mobile if partner_id.mobile else partner_id.phone if partner_id.phone else '',
            'address' : partner_id.street if partner_id.street else '',
            'city' : partner_id.city if partner_id.city else '',
            'zip' : partner_id.zip if partner_id.zip else '',
            'country' : partner_id.country_id.code if partner_id.country_id else '',
            'companyName' : partner_id.name if partner_id.company_type == 'company' else '',
            'vatno' : partner_id.vat if partner_id.company_type == 'company' else ''
        }
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
        print("=======================",get_fields)
        if get_fields:
            template_id = False
            if get_fields[0].get('template_id'):
                template_id = get_fields[0].get('template_id')[0]
            print("=======================", template_id)
            get_template_id = self.env['contract.template'].browse(template_id)
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
            data.update(final_dict)
        try:
            _logger.debug('New mandate creation data: {}'.format(data))
            response = requests.post(base_url+"/creditor/invite", data=data, headers={'Authorization' : authorization_token})
            _logger.info('Creating new mandate with response: %s' % (response.content))
            resp_obj = response.json()
            if response.status_code == 200:
                mandate_id = self.env['mandate.details'].sudo().create({'contract_temp_id' : get_template_id.id,'lang' : partner_id.lang, 'partner_id' : partner_id.id, 'reference' : resp_obj.get('mndtId'), 'url' : resp_obj.get('url')})
                print("====================mandate_id====",mandate_id)
                mandate_id.with_context(update_feed=True).write(get_fields[0])
                print("====================mandate_id====", mandate_id)
                partner_id.with_context(update_feed=True).write({'twikey_reference': str(partner_id.id)})
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
            else:
                raise UserError(_('%s') % (resp_obj.get('message')))
        except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
            _logger.error('Exception raised while creating a new Mandate %s' % (e))
            raise exceptions.AccessError(_('The url that this service requested returned an error. Please check your connection or try after sometime.'))
