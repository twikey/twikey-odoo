# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions, _
import logging
import requests
import json
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def _lang_get(self):
    return self.env['res.lang'].get_installed()


class MandateDetails(models.Model):
    _name = 'mandate.details'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = "Mandate details of Twikey"
    _rec_name = 'partner_id'

    partner_id = fields.Many2one('res.partner', string="Customer")
    state = fields.Selection(
        [('pending', 'Pending'), ('signed', 'Signed'), ('suspended', 'Suspended'), ('cancelled', 'Cancelled')],
        track_visibility='onchange', default='pending')
    creditor_id = fields.Many2one('res.partner', string="Creditor-ID")
    reference = fields.Char(string="Mandate Reference", required=True)
    iban = fields.Char(string="IBAN")
    bic = fields.Char(string="BIC")
    contract_temp_id = fields.Many2one(comodel_name="contract.template", string="Contract Template")
    description = fields.Text(string="Description")
    lang = fields.Selection(_lang_get, string='Language')
    url = fields.Char(string="URL")

    def update_feed(self):
        authorization_token = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.authorization_token')
        base_url = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.base_url')
        if authorization_token:
            try:
                response = requests.get(base_url + "/creditor/mandate", headers={'Authorization': authorization_token})
                _logger.info('Fetching all mandate data from twikey %s' % (response.content))
                resp_obj = response.json()
                if response.status_code == 200:
                    _logger.debug('Response status_code.. %s' % (response))
                    if resp_obj.get('Messages') and resp_obj.get('Messages')[0] and resp_obj.get('Messages')[0] != []:
                        _logger.info('Received %d document updates' % (len(resp_obj.get('Messages'))))
                        for data in resp_obj.get('Messages'):
                            if data.get('AmdmntRsn'):
                                mandateNumber = data.get('OrgnlMndtId')
                                partner_id = False
                                state = False
                                if data.get('AmdmntRsn').get('Rsn') and data.get('AmdmntRsn').get(
                                        'Rsn') == 'uncollectable|user':
                                    state = 'suspended'
                                else:
                                    state = 'signed'
                                _logger.info('Response AmdmntRsn.. %s - %s' % (mandateNumber, data.get('AmdmntRsn')))
                                if data.get('Mndt') and data.get('Mndt').get('Dbtr') and data.get('Mndt').get(
                                        'Dbtr').get('CtctDtls') and data.get('Mndt').get('Dbtr').get('CtctDtls').get(
                                    'Othr'):
                                    partner_id = self.env['res.partner'].search([('twikey_reference', '=',
                                                                                  data.get('Mndt').get('Dbtr').get(
                                                                                      'CtctDtls').get(
                                                                                      'Othr') if data.get(
                                                                                      'Mndt') and data.get('Mndt').get(
                                                                                      'Dbtr') and data.get('Mndt').get(
                                                                                      'Dbtr').get(
                                                                                      'CtctDtls') and data.get(
                                                                                      'Mndt').get('Dbtr').get(
                                                                                      'CtctDtls').get('Othr') else '')])
                                if not partner_id:
                                    if data.get('Mndt').get('Dbtr').get('Nm'):
                                        partner_id = self.env['res.partner'].search(
                                            [('name', '=', data.get('Mndt').get('Dbtr').get('Nm'))])
                                    if not partner_id:
                                        partner_id = self.env['res.partner'].create(
                                            {'name': data.get('Mndt').get('Dbtr').get('Nm')})
                                mandate_id = self.env['mandate.details'].search([('reference', '=', mandateNumber)])
                                lst = data.get('Mndt').get('SplmtryData')
                                field_dict = {}
                                lang = False
                                temp_id = False
                                for ls in lst:
                                    if ls.get('Key') == 'Language':
                                        lang = ls.get('Value')
                                    if ls.get('Key') == 'TemplateId':
                                        temp_id = ls.get('Value')
                                lang_id = self.env['res.lang'].search([('iso_code', '=', lang)])
                                contract_temp_id = self.env['contract.template'].search([('template_id', '=', temp_id)],
                                                                                        limit=1)
                                if contract_temp_id:
                                    for ls in lst:
                                        if ls.get('Key') in contract_temp_id.attribute_ids.mapped('name'):
                                            value = ls.get('Value')
                                            field_name = 'x_' + ls.get('Key') + '_' + str(temp_id)
                                            field_dict.update({field_name: value})


                                if mandate_id:
                                    mandate_vals = {'reference': data.get('Mndt').get('MndtId') if data.get('Mndt').get(
                                        'MndtId') else False,
                                                    'partner_id': partner_id.id if partner_id else False,
                                                    'state': state,
                                                    'contract_temp_id': contract_temp_id.id,
                                                    'iban': data.get('Mndt').get('DbtrAcct') if data.get('Mndt').get(
                                                        'DbtrAcct') else False,
                                                    'bic': data.get('Mndt').get('DbtrAgt').get('FinInstnId').get(
                                                        'BICFI') if data.get('Mndt').get('DbtrAgt') and data.get(
                                                        'Mndt').get('DbtrAgt').get('FinInstnId') and data.get(
                                                        'Mndt').get(
                                                        'DbtrAgt').get('FinInstnId').get('BICFI') else False,
                                                    'lang': lang_id.code if lang_id else False
                                                    }
                                    mandate_vals.update(field_dict)
                                    mandate_id.with_context(update_feed=True).write(mandate_vals)
                                    if partner_id:
                                        address = False
                                        zip = False
                                        city = False
                                        country_id = False
                                        if data.get('Mndt').get('Dbtr') and data.get('Mndt').get('Dbtr').get('PstlAdr'):
                                            address_line = data.get('Mndt').get('Dbtr').get('PstlAdr')
                                            address = address_line.get('AdrLine') if address_line.get(
                                                'AdrLine') else False
                                            zip = address_line.get('PstCd') if address_line.get('PstCd') else False
                                            city = address_line.get('TwnNm') if address_line.get('TwnNm') else False
                                            country_id = self.env['res.country'].search(
                                                [('code', '=', address_line.get('Ctry'))])
                                        partner_id.with_context(update_feed=True).write({'street': address,
                                                                                         'name': data.get('Mndt').get(
                                                                                             'Dbtr').get('Nm'),
                                                                                         'zip': zip,
                                                                                         'twikey_reference': data.get(
                                                                                             'Mndt').get('Dbtr').get(
                                                                                             'CtctDtls').get(
                                                                                             'Othr') if data.get(
                                                                                             'Mndt') and data.get(
                                                                                             'Mndt').get(
                                                                                             'Dbtr') and data.get(
                                                                                             'Mndt').get('Dbtr').get(
                                                                                             'CtctDtls') and data.get(
                                                                                             'Mndt').get('Dbtr').get(
                                                                                             'CtctDtls').get(
                                                                                             'Othr') else '',
                                                                                         'city': city,
                                                                                         'country_id': country_id.id if country_id else False,
                                                                                         'lang': lang_id.code if lang_id else False,
                                                                                         'email': data.get('Mndt').get(
                                                                                             'Dbtr').get(
                                                                                             'CtctDtls').get(
                                                                                             'EmailAdr') if data.get(
                                                                                             'Mndt').get(
                                                                                             'Dbtr') and data.get(
                                                                                             'Mndt').get('Dbtr').get(
                                                                                             'CtctDtls') and data.get(
                                                                                             'Mndt').get('Dbtr').get(
                                                                                             'CtctDtls').get(
                                                                                             'EmailAdr') else False})

                                    # if creditor_id:
                                    #     address = False
                                    #     zip = False
                                    #     city = False
                                    #     country_id = False
                                    #     if data.get('Mndt').get('Cdtr') and data.get('Mndt').get('Cdtr').get('PstlAdr'):
                                    #         address_line = data.get('Mndt').get('Cdtr').get('PstlAdr')
                                    #         address = address_line.get('AdrLine') if address_line.get('AdrLine') else False
                                    #         zip = address_line.get('PstCd') if address_line.get('PstCd') else False
                                    #         city = address_line.get('TwnNm') if address_line.get('TwnNm') else False
                                    #         country_id = self.env['res.country'].search([('code', '=', address_line.get('Ctry'))])
                                    #     creditor_id.write({'street' : address,
                                    #                       'zip' : zip,
                                    #                       'city' : city,
                                    #                       'country_id' : country_id.id if country_id else False,
                                    #                       'email' : data.get('Mndt').get('Cdtr').get('CtctDtls').get('EmailAdr') if data.get('Mndt').get('Cdtr') and data.get('Mndt').get('Cdtr').get('CtctDtls') and data.get('Mndt').get('Cdtr').get('CtctDtls').get('EmailAdr') else False})
                                if not mandate_id:
                                    mandate_vals = {'partner_id': partner_id.id if partner_id else False,
                                                    'reference': data.get('Mndt').get('MndtId'),
                                                    'state': state,
                                                    'lang': lang_id.code if lang_id else False,
                                                    'contract_temp_id': contract_temp_id.id,
                                                    'iban': data.get('Mndt').get('DbtrAcct') if data.get('Mndt').get(
                                                        'DbtrAcct') else False,
                                                    'bic': data.get('Mndt').get('DbtrAgt').get('FinInstnId').get(
                                                        'BICFI') if data.get('Mndt').get('DbtrAgt') and data.get(
                                                        'Mndt').get('DbtrAgt').get('FinInstnId') and data.get(
                                                        'Mndt').get('DbtrAgt').get('FinInstnId').get(
                                                        'BICFI') else False,
                                                    }
                                    mandate_vals.update(field_dict)
                                    self.env['mandate.details'].sudo().create(mandate_vals)

                                # Rsn': 'uncollectable|user' -> Suspended
                                # Rsn': 'collectable|user' -> Resumed / signed
                                #  _T50, // AccountChanged,
                                #  _T51, // AddressChanged,
                                #  _T52, // MandateNumberChanged
                                #  _T53, // Name changed
                                #  _T54, // Email changed
                                #  _T55, // Mobile changed
                                #  _T56, // Language changed
                                #  _T57, // Owner Mandate changed

                                # creditor_id = self.env['res.partner'].search([('name', '=', data.get('Mndt').get('Cdtr').get('Nm'))])
                                # if not creditor_id:
                                #     creditor_id = self.env['res.partner'].create({'name' : data.get('Mndt').get('Cdtr').get('Nm')})

                            elif data.get('CxlRsn'):
                                mandateNumber = data.get('OrgnlMndtId')
                                rsn = data.get('CxlRsn').get('Rsn')
                                _logger.info('Response CxlRsn.. %s - %s' % (mandateNumber, rsn))
                                mandate_id = self.env['mandate.details'].search(
                                    [('reference', '=', data.get('OrgnlMndtId'))])
                                if mandate_id:
                                    mandate_id.with_context(update_feed=True).write(
                                        {'state': 'cancelled', 'description': rsn})
                                else:
                                    mandate_id = self.env['mandate.details'].sudo().create({
                                        'reference': data.get('OrgnlMndtId'),
                                        'state': 'cancelled'
                                    })
                            elif data.get('Mndt'):
                                mandateNumber = data.get('Mndt').get('MndtId')
                                _logger.info('New mandate.. %s' % (mandateNumber))
                                mandate_id = self.env['mandate.details'].search([('reference', '=', mandateNumber)])
                                lst = data.get('Mndt').get('SplmtryData')
                                lang = False
                                temp_id = False
                                field_dict = {}
                                for ls in lst:
                                    if ls.get('Key') == 'Language':
                                        lang = ls.get('Value')
                                    if ls.get('Key') == 'TemplateId':
                                        temp_id = ls.get('Value')
                                lang_id = self.env['res.lang'].search([('iso_code', '=', lang)])
                                contract_temp_id = self.env['contract.template'].search([('template_id', '=', temp_id)],
                                                                                        limit=1)
                                if contract_temp_id:
                                    for ls in lst:
                                        if ls.get('Key') in contract_temp_id.attribute_ids.mapped('name'):
                                            value = ls.get('Value')
                                            field_name = 'x_' + ls.get('Key') + '_' + str(temp_id)
                                            field_dict.update({field_name: value})
                                if data.get('Mndt') and data.get('Mndt').get('Dbtr') and data.get('Mndt').get(
                                        'Dbtr').get('CtctDtls') and data.get('Mndt').get('Dbtr').get('CtctDtls').get(
                                    'Othr'):
                                    partner_id = self.env['res.partner'].search([('twikey_reference', '=',
                                                                                  data.get('Mndt').get('Dbtr').get(
                                                                                      'CtctDtls').get(
                                                                                      'Othr') if data.get(
                                                                                      'Mndt') and data.get('Mndt').get(
                                                                                      'Dbtr') and data.get('Mndt').get(
                                                                                      'Dbtr').get(
                                                                                      'CtctDtls') and data.get(
                                                                                      'Mndt').get('Dbtr').get(
                                                                                      'CtctDtls').get('Othr') else '')])
                                if not partner_id:
                                    if data.get('Mndt').get('Dbtr').get('Nm'):
                                        partner_id = self.env['res.partner'].search(
                                            [('name', '=', data.get('Mndt').get('Dbtr').get('Nm'))])
                                    if not partner_id:
                                        partner_id = self.env['res.partner'].create(
                                            {'name': data.get('Mndt').get('Dbtr').get('Nm')})
                                if not mandate_id:
                                    mandate_vals = {'partner_id': partner_id.id if partner_id else False,
                                                    'reference': data.get('Mndt').get('MndtId'), 'state': 'signed',
                                                    'contract_temp_id': contract_temp_id.id,
                                                    'lang': lang_id.code if lang_id else False}
                                    mandate_vals.update(field_dict)
                                    mandate_id = self.env['mandate.details'].sudo().create(mandate_vals)
                                if partner_id:
                                    address = False
                                    zip = False
                                    city = False
                                    country_id = False
                                    if data.get('Mndt').get('Dbtr') and data.get('Mndt').get('Dbtr').get('PstlAdr'):
                                        address_line = data.get('Mndt').get('Dbtr').get('PstlAdr')
                                        address = address_line.get('AdrLine') if address_line.get('AdrLine') else False
                                        zip = address_line.get('PstCd') if address_line.get('PstCd') else False
                                        city = address_line.get('TwnNm') if address_line.get('TwnNm') else False
                                        country_id = self.env['res.country'].search(
                                            [('code', '=', address_line.get('Ctry'))])
                                    partner_id.with_context(update_feed=True).write({'street': address,
                                                                                     'name': data.get('Mndt').get(
                                                                                         'Dbtr').get('Nm') if data.get(
                                                                                         'Mndt').get('Dbtr').get(
                                                                                         'Nm') else False,
                                                                                     'zip': zip,
                                                                                     'twikey_reference': data.get(
                                                                                         'Mndt').get('Dbtr').get(
                                                                                         'CtctDtls').get(
                                                                                         'Othr') if data.get(
                                                                                         'Mndt') and data.get(
                                                                                         'Mndt').get(
                                                                                         'Dbtr') and data.get(
                                                                                         'Mndt').get('Dbtr').get(
                                                                                         'CtctDtls') and data.get(
                                                                                         'Mndt').get('Dbtr').get(
                                                                                         'CtctDtls').get(
                                                                                         'Othr') else '',
                                                                                     'city': city,
                                                                                     'country_id': country_id.id if country_id else False,
                                                                                     'email': data.get('Mndt').get(
                                                                                         'Dbtr').get('CtctDtls').get(
                                                                                         'EmailAdr') if data.get(
                                                                                         'Mndt').get(
                                                                                         'Dbtr') and data.get(
                                                                                         'Mndt').get('Dbtr').get(
                                                                                         'CtctDtls') and data.get(
                                                                                         'Mndt').get('Dbtr').get(
                                                                                         'CtctDtls').get(
                                                                                         'EmailAdr') else False})

                                # creditor_id = self.env['res.partner'].search([('name', '=', data.get('Mndt').get('Cdtr').get('Nm'))])
                                # if not creditor_id:
                                #     creditor_id = self.env['res.partner'].create({'name' : data.get('Mndt').get('Cdtr').get('Nm')})

                                if mandate_id:
                                    mandate_vals = {'state': 'signed',
                                                    'contract_temp_id': contract_temp_id.id,
                                                    'partner_id': partner_id.id if partner_id else False,
                                                    'iban': data.get('Mndt').get('DbtrAcct') if data.get('Mndt').get('DbtrAcct') else False,
                                                    'bic': data.get('Mndt').get('DbtrAgt').get('FinInstnId').get('BICFI') if data.get('Mndt').get('DbtrAgt') and data.get('Mndt').get('DbtrAgt').get('FinInstnId') and data.get('Mndt').get('DbtrAgt').get('FinInstnId').get('BICFI') else False,
                                                    'lang': lang_id.code if lang_id else False,
                                                    }
                                    mandate_vals.update(field_dict)
                                    mandate_id.with_context(update_feed=True).write(mandate_vals)
            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
                    requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                _logger.error('Update Feed Exception %s' % (e))
                raise exceptions.AccessError(
                    _('The url that this service requested returned an error. Please check your connection or try after sometime.'))

    #
    # def cancel_or_delete_mandate(self):
    #     authorization_token = self.env['ir.config_parameter'].sudo().get_param(
    #         'twikey_integration.authorization_token')
    #     base_url = self.env['ir.config_parameter'].sudo().get_param(
    #         'twikey_integration.base_url')
    #     if authorization_token:
    #         data = {'mndtId': self.reference,
    #                 # 'rsn': self.rsn if self.rsn else 'No reason given'
    #                 'rsn': 'No reason given'
    #                 }
    #         try:
    #             response = requests.delete(base_url + "/creditor/mandate", data=data,
    #                                        headers={'Authorization': authorization_token})
    #             if response.status_code == 200:
    #                 _logger.info('Record Successfully Deleted.. %s' % (response.status_code))
    #         except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
    #                 requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
    #             raise exceptions.AccessError(
    #                 _(
    #                     'The url that this service requested returned an error. Please check your connection or try after sometime.')
    #             )

    def write(self, values):
        res = super(MandateDetails, self).write(values)
        if not self._context.get('update_feed'):
            authorization_token = self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.authorization_token')
            base_url = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.base_url')
            data = {}
            if authorization_token and self.state != 'signed':
                #             if values.get('partner_id'):
                #                 customer_name = values.get('partner_id').name.split(' ')
                #             else:
                #                 customer_name = self.partner_id.name.split(' ')
                #                 if 'reference' in values:
                data['mndtId'] = values.get('reference') if values.get('reference') else self.reference
                if 'iban' in values:
                    data['iban'] = values.get('iban') or ''
                if 'bic' in values:
                    data['bic'] = values.get('bic')
                if 'lang' in values:
                    data['l'] = values.get('lang')
                #                 data = {'mndtId' : values.get('reference') if values.get('reference') else self.reference,
                #                         'iban' : values.get('iban') if values.get('iban') else self.iban if self.iban else '',
                #                         'bic' : values.get('bic') if values.get('bic') else self.bic if self.bic else '',
                #                         'l' : values.get('lang') if values.get('lang') else self.lang if self.lang else ''
                #                     }
                #                     'state' : values.get('state') if values.get('state') else self.state
                #                     'email' : self.partner_id.email if self.partner_id and self.partner_id.email else '',
                #                     'firstname' : customer_name[0] if customer_name and self.partner_id.company_type == 'person' else '',
                #                     'lastname' : customer_name[1] if customer_name and len(customer_name) > 1 and self.partner_id.company_type == 'person' else '',
                #                     'companyName' : values.get('partner_id').name if values.get('partner_id') else self.partner_id.name if self.partner_id and self.partner_id.name and self.partner_id.company_type == 'company' else '',
                #                     'vatno' : self.partner_id.vat if self.partner_id and self.partner_id.vat and self.partner_id.company_type == 'company' else '',
                #                     'customerNumber' : self.id,
                #                     'address' : self.partner_id.street if self.partner_id and self.partner_id.street else '',
                #                     'city' : self.partner_id.city if self.partner_id and self.partner_id.city else '',
                #                     'zip' : self.partner_id.zip if self.partner_id and self.partner_id.zip else '',
                #                     'country' : self.partner_id.country_id.code if self.partner_id and self.partner_id.country_id else ''
                #                     }
                try:
                    if data != {}:
                        response = requests.post(base_url + "/creditor/mandate/update", data=data,
                                                 headers={'Authorization': authorization_token})
                        _logger.info('Updating mandate data to Twikey %s -> %d' % (data, response.status_code))
                        if response.status_code != 204:
                            resp_obj = response.json()
                            raise UserError(_('%s') % (resp_obj.get('message')))
                except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
                        requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                    _logger.error('Mandate Write Exception %s' % (e))
                    raise exceptions.AccessError(
                        _('The url that this service requested returned an error. Please check your connection or try after sometime.'))
        return res

    def unlink(self):
        context = self._context
        if not context.get('update_feed'):
            self.update_feed()
            base_url = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.base_url')
            authorization_token = self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.authorization_token')
            if self.state in ['signed', 'cancelled']:
                raise UserError(_('This mandate is in already signed or cancelled. It can not be deleted.'))
            elif self.state == 'pending' and authorization_token:
                prepared_url = base_url + '/creditor/mandate' + '?mndtId=' + self.reference + '&rsn=' + 'Deleted from odoo'
                response = requests.delete(prepared_url, headers={'Authorization': authorization_token})
                _logger.info('Deleting mandate %s -> %d' % (self.reference, response.status_code))
                return super(MandateDetails, self).unlink()
            else:
                return super(MandateDetails, self).unlink()
        else:
            return super(MandateDetails, self).unlink()
