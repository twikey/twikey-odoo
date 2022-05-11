# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions,_
from odoo.exceptions import UserError
import requests
import logging
from .. import twikey

_logger = logging.getLogger(__name__)

def _lang_get(self):
    return self.env['res.lang'].get_installed()

class MandateDetails(models.Model):
    _name = 'mandate.details'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = "Mandate details of Twikey"
    _rec_name = 'partner_id'

    partner_id = fields.Many2one('res.partner', string="Customer")
    state = fields.Selection([('pending', 'Pending'), ('signed', 'Signed'), ('suspended', 'Suspended'), ('cancelled', 'Cancelled')], track_visibility='onchange', default='pending')
    creditor_id = fields.Many2one('res.partner', string="Creditor-ID")
    reference = fields.Char(string="Mandate Reference", required=True)
    iban = fields.Char(string="IBAN")
    bic = fields.Char(string="BIC")
    contract_temp_id = fields.Many2one(comodel_name="twikey.contract.template", string="Contract Template")
    description = fields.Text(string="Description")
    lang = fields.Selection(_lang_get, string='Language')
    url = fields.Char(string="URL")

    def update_feed(self):
        try:
            twikey_client = self.env['ir.config_parameter'].get_twikey_client()
            twikey_client.document.feed(OdooDocumentFeed(self.env))
        except UserError as ue:
            _logger.error('Error while updating mandates from Twikey: %s' % ue)
        except (ValueError, requests.exceptions.RequestException) as e:
            _logger.error('Error while updating mandates from Twikey: %s' % e)

    @api.multi
    def write(self, values):
        res = super(MandateDetails, self).write(values)
        if not self._context.get('update_feed'):
            twikey_client = self.env['ir.config_parameter'].get_twikey_client()
            data = {}
            if self.state != 'signed':
                data['mndtId'] = values.get('reference') if values.get('reference') else self.reference
                if 'iban' in values:
                    data['iban'] = values.get('iban') or ''
                if 'bic' in values:
                    data['bic'] = values.get('bic')
                if 'lang' in values:
                    data['l'] = values.get('lang')

                try:
                    if data != {}:
                        twikey_client.document.update(data)
                        _logger.info('Updating mandate data to Twikey %s ' % data)
                except (ValueError, requests.exceptions.RequestException) as e:
                    _logger.error('Mandate Write Exception %s' % (e))
                    raise exceptions.AccessError(_('The url that this service requested returned an error. Please check your connection or try after sometime.'))
        return res

    def unlink(self):
        context = self._context
        if not context.get('update_feed'):
            self.update_feed()
            twikey_client = self.env['ir.config_parameter'].get_twikey_client()
            if self.state in ['signed', 'cancelled']:
                raise UserError(_('This mandate is in already signed or cancelled. It can not be deleted.'))
            elif self.state == 'pending':
                _logger.info('Cancelling mandate %s -> %d' % self.reference)
                twikey_client.document.cancel(self.reference,'Deleted from odoo')
                return super(MandateDetails, self).unlink()
            else:
                return super(MandateDetails, self).unlink()
        else:
            return super(MandateDetails, self).unlink()

class OdooDocumentFeed(twikey.document.DocumentFeed):

    def __init__(self, env):
        self.env = env

    def newDocument(self, doc):

        mandate_number = doc.get('MndtId')

        contract_temp_id = False
        field_dict = {}
        lang_id = False
        if 'Splmtrydoc' in doc:
            lst = doc.get('Splmtrydoc')
            for ls in lst:
                field_dict[ls["Key"]] = ls["Value"]

            if 'Language' in field_dict:
                lang = field_dict['Language']
                lang_id = self.env['res.lang'].search([('iso_code', '=', lang)])

            if 'TemplateId' in field_dict:
                temp_id = field_dict['TemplateId']
                contract_temp_id = self.env['twikey.contract.template'].search([('template_id', '=', temp_id)],limit=1)
                if contract_temp_id:
                    for ls in lst:
                        if ls.get('Key') in contract_temp_id.attribute_ids.mapped('name'):
                            value = ls.get('Value')
                            field_name = 'x_' + ls.get('Key') + '_' + str(temp_id)
                            field_dict.update({field_name: value})

        debtor = doc.get('Dbtr')
        iban = doc.get('DbtrAcct')
        bic = doc.get('DbtrAgt').get('FinInstnId').get('BICFI')
        new_mandate_number = doc.get('MndtId')

        # Find by customernumber
        customer_number = ""
        partner_id = False
        contact_details = debtor.get('CtctDtls')
        if contact_details and contact_details.get('Othr'):
            customer_number = contact_details.get('Othr')
            partner_id = self.env['res.partner'].search([('twikey_reference', '=', customer_number)])

        # Find by name if not found
        if not partner_id:
            if debtor.get('Nm'):
                partner_id = self.env['res.partner'].search([('name', '=', debtor.get('Nm'))])
            if not partner_id:
                partner_id = self.env['res.partner'].create({'name' : debtor.get('Nm')})

        mandate_id = self.env['mandate.details'].search([('reference', '=', mandate_number)])
        if not mandate_id:
            mandate_vals = {'partner_id': partner_id.id if partner_id else False,
                            'reference': mandate_number,
                            'state': 'signed',
                            'contract_temp_id': contract_temp_id.id if contract_temp_id else False,
                            'lang': lang_id.code if lang_id else False}
            mandate_vals.update(field_dict)
            mandate_id = self.env['mandate.details'].sudo().create(mandate_vals)
        if partner_id:
            address = False
            zip = False
            city = False
            country_id = False
            if debtor and debtor.get('PstlAdr'):
                address_line = debtor.get('PstlAdr')
                address = address_line.get('AdrLine') if address_line.get('AdrLine') else False
                zip = address_line.get('PstCd') if address_line.get('PstCd') else False
                city = address_line.get('TwnNm') if address_line.get('TwnNm') else False
                country_id = self.env['res.country'].search([('code', '=', address_line.get('Ctry'))])
            partner_id.with_context(update_feed=True).write({'street' : address,
                                                             'name' : debtor.get('Nm') if 'Nm' in debtor else False,
                                                             'zip' : zip,
                                                             'twikey_reference': customer_number,
                                                             'city' : city,
                                                             'country_id' : country_id.id if country_id else False,
                                                             'lang': lang_id.code if lang_id else False,
                                                             'email' : contact_details.get('EmailAdr') if 'EmailAdr' in contact_details else False})

        if mandate_id:
            mandate_vals = {'state': 'signed',
                            'partner_id': partner_id.id if partner_id else False,
                            'lang': lang_id.code if lang_id else False,
                            'contract_temp_id': contract_temp_id.id if contract_temp_id else False,
                            'iban': iban if iban else False,
                            'bic': bic if bic else False,
                            }
            mandate_vals.update(field_dict)
            mandate_id.with_context(update_feed=True).write(mandate_vals)
        _logger.info('New mandate.. %s' % mandate_number)

    def updatedDocument(self, mandate_number, doc, reason):

        partner_id = False
        debtor = doc.get('Dbtr')
        iban = doc.get('DbtrAcct')
        bic = doc.get('DbtrAgt').get('FinInstnId').get('BICFI')
        new_mandate_number = doc.get('MndtId')

        # Find by customernumber
        customer_number = ""
        contact_details = debtor.get('CtctDtls')
        if contact_details and contact_details.get('Othr'):
            customer_number = contact_details.get('Othr')
            partner_id = self.env['res.partner'].search([('twikey_reference', '=', customer_number)])

        # Find by name if not found
        if not partner_id:
            if debtor.get('Nm'):
                partner_id = self.env['res.partner'].search([('name', '=', debtor.get('Nm'))])
            if not partner_id:
                partner_id = self.env['res.partner'].create({'name' : debtor.get('Nm')})

        mandate_id = self.env['mandate.details'].search([('reference', '=', mandate_number)])

        contract_temp_id = False
        field_dict = {}
        lang_id = False
        if 'Splmtrydoc' in doc:
            lst = doc.get('Splmtrydoc')
            for ls in lst:
                field_dict[ls["Key"]] = ls["Value"]

            if 'Language' in field_dict:
                lang = field_dict['Language']
                lang_id = self.env['res.lang'].search([('iso_code', '=', lang)])

            if 'TemplateId' in field_dict:
                temp_id = field_dict['TemplateId']
                contract_temp_id = self.env['twikey.contract.template'].search([('template_id', '=', temp_id)],limit=1)
                if contract_temp_id:
                    for ls in lst:
                        if ls.get('Key') in contract_temp_id.attribute_ids.mapped('name'):
                            value = ls.get('Value')
                            field_name = 'x_' + ls.get('Key') + '_' + str(temp_id)
                            field_dict.update({field_name: value})

        if mandate_id:
            mandate_vals = {'reference': new_mandate_number,
                            'partner_id': partner_id.id if partner_id else False,
                            'state': 'suspended' if reason["Rsn"] and reason["Rsn"] == 'uncollectable|user' else 'signed',
                            'contract_temp_id': contract_temp_id.id if contract_temp_id else False,
                            'iban': iban if iban else False,
                            'bic': bic if bic else False,
                            'lang': lang_id.code if lang_id else False
                            }
            mandate_vals.update(field_dict)
            mandate_id.with_context(update_feed=True).write(mandate_vals)
            if partner_id:
                address = False
                zip = False
                city = False
                country_id = False
                if debtor and debtor.get('PstlAdr'):
                    address_line = debtor.get('PstlAdr')
                    address = address_line.get('AdrLine') if address_line.get('AdrLine') else False
                    zip = address_line.get('PstCd') if address_line.get('PstCd') else False
                    city = address_line.get('TwnNm') if address_line.get('TwnNm') else False
                    country_id = self.env['res.country'].search([('code', '=', address_line.get('Ctry'))])

                partner_id.with_context(update_feed=True).write({'street' : address,
                                                                 'name' : debtor.get('Nm'),
                                                                 'zip' : zip,
                                                                 'twikey_reference': customer_number,
                                                                 'city' : city,
                                                                 'country_id' : country_id.id if country_id else False,
                                                                 'lang': lang_id.code if lang_id else False,
                                                                 'email' : contact_details.get('EmailAdr') if contact_details and contact_details.get('EmailAdr') else False})
        else:
            mandate_vals = {'partner_id': partner_id.id if partner_id else False,
                            'reference': new_mandate_number,
                            'state': 'suspended' if reason["Rsn"] and reason["Rsn"] == 'uncollectable|user' else 'signed',
                            'lang': lang_id.code if lang_id else False,
                            'contract_temp_id': contract_temp_id.id if contract_temp_id else False,
                            'iban': iban if iban else False,
                            'bic': bic if bic else False,
                            }
            mandate_vals.update(field_dict)
            self.env['mandate.details'].sudo().create(mandate_vals)
        _logger.info("Update %s b/c %s" % (mandate_number, reason["Rsn"]))

    def cancelDocument(self, mandateNumber, rsn):
        _logger.info('Response CxlRsn.. %s - %s' % (mandateNumber, rsn["Rsn"]))
        mandate_id = self.env['mandate.details'].search([('reference', '=', mandateNumber)])
        if mandate_id:
            mandate_id.with_context(update_feed=True).write({'state' : 'cancelled', 'description' : rsn["Rsn"]})
        else:
            self.env['mandate.details'].sudo().create({
                'reference' : mandateNumber,
                'state' : 'cancelled'
            })
