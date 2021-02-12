# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions,_
import requests
import json


def _lang_get(self):
    return self.env['res.lang'].get_installed()

class MandateDetails(models.Model):
    _name = 'mandate.details'
    _rec_name = 'partner_id'
    
    partner_id = fields.Many2one('res.partner', string="Customer")
    state = fields.Selection([('pending', 'Pending'), ('signed', 'Signed'), ('suspended', 'Suspended'), ('cancelled', 'Cancelled')], default='pending')
    creditor_id = fields.Many2one('res.partner', string="Creditor-ID")
    reference = fields.Char(tring="Mandate Reference", required=True)
    iban = fields.Char(string="IBAN")
    bic = fields.Char(string="BIC")
    contract = fields.Char(string="Contract")
    description = fields.Text(string="Description")
    lang = fields.Selection(_lang_get, string='Language')
    url = fields.Char(string="URL")
    
    def update_feed(self):
        authorization_token=self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.authorization_token')
        if authorization_token:
            try:
                response = requests.get("https://api.beta.twikey.com/creditor/mandate", headers={'Authorization' : authorization_token})
                resp_obj = json.loads(response.text)
                if response.status_code == 200:
                    if resp_obj.get('Messages') and resp_obj.get('Messages')[0] and resp_obj.get('Messages')[0] != []:
                        for data in resp_obj.get('Messages'):
                            if data.get('AmdmntRsn'):
                                mandate_id = self.env['mandate.details'].search([('reference', '=', data.get('OrgnlMndtId'))])
                                partner_id = self.env['res.partner'].search([('name', '=', data.get('Mndt').get('Dbtr').get('Nm'))])
                                if not partner_id:
                                    partner_id = self.env['res.partner'].create({'name' : data.get('Mndt').get('Dbtr').get('Nm')})
                                creditor_id = self.env['res.partner'].search([('name', '=', data.get('Mndt').get('Cdtr').get('Nm'))])
                                if not creditor_id:
                                    creditor_id = self.env['res.partner'].create({'name' : data.get('Mndt').get('Cdtr').get('Nm')})
        
                                if mandate_id:
                                    mandate_id.write({'reference' : data.get('Mndt').get('MndtId') if data.get('Mndt').get('MndtId') else False,
                                                   'partner_id' : partner_id.id if partner_id else False,
                                                   'state' : 'signed',
                                                   'creditor_id' : creditor_id.id if creditor_id else False,
                                                   'iban' : data.get('DbtrAcct') if data.get('DbtrAcct') else False,
                                                   'bic' : data.get('DbtrAgt').get('FinInstnId').get('BICFI') if data.get('DbtrAgt') and data.get('DbtrAgt').get('FinInstnId') and data.get('DbtrAgt').get('FinInstnId').get('BICFI') else False
                                                })
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
                                            country_id = self.env['res.country'].search([('code', '=', address_line.get('Ctry'))])
                                        partner_id.write({'street' : address,
                                                          'zip' : zip,
                                                          'city' : city,
                                                          'country_id' : country_id.id if country_id else False,
                                                          'email' : data.get('Mndt').get('Dbtr').get('CtctDtls').get('EmailAdr') if data.get('Mndt').get('Dbtr') and data.get('Mndt').get('Dbtr').get('CtctDtls') and data.get('Mndt').get('Dbtr').get('CtctDtls').get('EmailAdr') else False})
                                    
                                    if creditor_id:
                                        address = False
                                        zip = False
                                        city = False
                                        country_id = False
                                        if data.get('Mndt').get('Cdtr') and data.get('Mndt').get('Cdtr').get('PstlAdr'):
                                            address_line = data.get('Mndt').get('Cdtr').get('PstlAdr')
                                            address = address_line.get('AdrLine') if address_line.get('AdrLine') else False
                                            zip = address_line.get('PstCd') if address_line.get('PstCd') else False
                                            city = address_line.get('TwnNm') if address_line.get('TwnNm') else False
                                            country_id = self.env['res.country'].search([('code', '=', address_line.get('Ctry'))])
                                        creditor_id.write({'street' : address,
                                                          'zip' : zip,
                                                          'city' : city,
                                                          'country_id' : country_id.id if country_id else False,
                                                          'email' : data.get('Mndt').get('Cdtr').get('CtctDtls').get('EmailAdr') if data.get('Mndt').get('Cdtr') and data.get('Mndt').get('Cdtr').get('CtctDtls') and data.get('Mndt').get('Cdtr').get('CtctDtls').get('EmailAdr') else False})
                                else:
                                    mandate_id = self.env['mandate.details'].sudo().create({'partner_id' : partner_id.id if partner_id else False, 
                                                                                            'creditor_id' : creditor_id.id if creditor_id else False,
                                                                                            'reference' : data.get('Mndt').get('MndtId'), 
                                                                                            'state' : 'signed'
                                                                                            })
                            if data.get('CxlRsn'):
                                mandate_id = self.env['mandate.details'].search([('reference', '=', data.get('OrgnlMndtId'))])
                                if mandate_id:
                                    mandate_id.write({'state' : 'cancelled', 'description' : data.get('CxlRsn').get('Rsn')})
                                else:
                                    mandate_id = self.env['mandate.details'].sudo().create({
                                                                                            'reference' : data.get('OrgnlMndtId'), 
                                                                                            'state' : 'cancelled'
                                                                                            })
                            if data.get('Mndt'):
                                mandate_id = self.env['mandate.details'].search([('reference', '=', data.get('Mndt').get('MndtId'))])
                                partner_id = self.env['res.partner'].search([('name', '=', data.get('Mndt').get('Dbtr').get('Nm'))])
                                if not partner_id:
                                    partner_id = self.env['res.partner'].create({'name' : data.get('Mndt').get('Dbtr').get('Nm')})
                                creditor_id = self.env['res.partner'].search([('name', '=', data.get('Mndt').get('Cdtr').get('Nm'))])
                                if not creditor_id:
                                    creditor_id = self.env['res.partner'].create({'name' : data.get('Mndt').get('Cdtr').get('Nm')})
          
                                if not mandate_id:
                                    mandate_id = self.env['mandate.details'].sudo().create({'partner_id' : partner_id.id if partner_id else False, 'reference' : data.get('Mndt').get('MndtId'), 'creditor_id' : creditor_id.id if creditor_id else False, 'state' : 'signed'})
                                else:
                                    mandate_id.write({'state' : 'signed',
                                                   'partner_id' : partner_id.id if partner_id else False,
                                                   'creditor_id' : creditor_id.id if creditor_id else False,
                                                   'iban' : data.get('Mndt').get('DbtrAcct') if data.get('Mndt').get('DbtrAcct') else False,
                                                   'bic' : data.get('Mndt').get('DbtrAgt').get('FinInstnId').get('BICFI') if data.get('Mndt').get('DbtrAgt') and data.get('Mndt').get('DbtrAgt').get('FinInstnId') and data.get('Mndt').get('DbtrAgt').get('FinInstnId').get('BICFI') else False
                                                    })
            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                raise exceptions.AccessError(
                    _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                )

    def update_mandate_details(self):
        authorization_token=self.env['ir.config_parameter'].sudo().get_param(
                'twikey_integration.authorization_token')
        if authorization_token:
            data = {'mndtId' : self.reference,
                    'iban' : self.iban if self.iban else '',
                    'bic' : self.bic if self.bic else '',
                    'email' : self.partner_id.email if self.partner_id and self.partner_id.email else '',
                    'firstname' : self.partner_id.name.split(' ')[0] if self.partner_id and self.partner_id.name and self.partner_id.company_type == 'person' else '',
                    'lastname' : self.partner_id.name.split(' ')[1] if self.partner_id and self.partner_id.name and self.partner_id.company_type == 'person' else '',
                    'companyName' : self.partner_id.name if self.partner_id and self.partner_id.name and self.partner_id.company_type == 'company' else '',
                    'vatno' : self.partner_id.vat if self.partner_id and self.partner_id.vat and self.partner_id.company_type == 'company' else '',
                    'customerNumber' : self.id,
                    'address' : self.partner_id.street if self.partner_id and self.partner_id.street else '',
                    'city' : self.partner_id.city if self.partner_id and self.partner_id.city else '',
                    'zip' : self.partner_id.zip if self.partner_id and self.partner_id.zip else '',
                    'country' : self.partner_id.country_id.code if self.partner_id and self.partner_id.country_id else ''
                    }
            try:
                response = requests.post("https://api.beta.twikey.com/creditor/mandate/update", data=data, headers={'Authorization' : authorization_token})
            except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                raise exceptions.AccessError(
                    _('The url that this service requested returned an error. Please check your connection or try after sometime.')
                )
                
                
                
                
                
                
                
                
                
                
                
                