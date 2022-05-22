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

    def splmtrAsDict(self,doc):
        field_dict = {}
        if 'SplmtryData' in doc:
            lst = doc.get('SplmtryData')
            for ls in lst:
                field_dict[ls["Key"]] = ls["Value"]
        else:
            _logger.debug("No kv in doc" % doc)
        return field_dict

    def newDocument(self, doc):

        partner_id = False
        debtor = doc.get('Dbtr')
        iban = doc.get('DbtrAcct')
        bic = doc.get('DbtrAgt').get('FinInstnId').get('BICFI')
        mandate_number = doc.get('MndtId')

        template_id = False
        lang_id = False

        field_dict = self.splmtrAsDict(doc)
        if 'Language' in field_dict:
            lang = field_dict['Language']
            lang_id = self.env['res.lang'].search([('iso_code', '=', lang)])

        if 'TemplateId' in field_dict:
            temp_id = field_dict['TemplateId']
            template_id = self.env['twikey.contract.template'].search([('template_id', '=', temp_id)],limit=1)

        address = False
        zip = False
        city = False
        country_id = False
        email = False
        if debtor and 'PstlAdr' in debtor:
            address_line = debtor.get('PstlAdr')
            address = address_line.get('AdrLine') if address_line.get('AdrLine') else False
            zip = address_line.get('PstCd') if address_line.get('PstCd') else False
            city = address_line.get('TwnNm') if address_line.get('TwnNm') else False
            country_id = self.env['res.country'].search([('code', '=', address_line.get('Ctry'))])

        # Find by customernumber
        if 'CtctDtls' in debtor:
            contact_details = debtor.get('CtctDtls')
            if "Othr" in contact_details:
                customer_number = contact_details.get('Othr')
                try:
                    lookup_id = int(customer_number)
                    partner_id = self.env['res.partner'].browse(lookup_id)
                except:
                    _logger.info('Customer not found by %s skipping mandate.' % customer_number)
                    return
            if "EmailAdr" in contact_details:
                email = contact_details.get('EmailAdr')
                partner_id = self.env['res.partner'].search([('email', '=', email)])

        # Find by name if not found create
        if not partner_id and 'Nm' in debtor:
            partner_id = self.env['res.partner'].search([('name', '=', debtor.get('Nm'))])
            # Last step, just create
            if not partner_id:
                partner_id = self.env['res.partner'].create({'name' : debtor.get('Nm')})

        if partner_id:
            partner_id.with_context(update_feed=True).write({'street' : address,
                                                             'zip' : zip,
                                                             'city' : city,
                                                             'country_id' : country_id.id if country_id else False,
                                                             'email' : email
                                                             })

        # Update actual mandate
        mandate_id = self.env['mandate.details'].search([('reference', '=', mandate_number)])
        if mandate_id:
            mandate_vals = {'partner_id': partner_id.id if partner_id else False,
                            'state': 'signed',
                            'lang': lang_id.code if lang_id else False,
                            'contract_temp_id': template_id.id if template_id else False,
                            'iban': iban if iban else False,
                            'bic': bic if bic else False,
                            }
            mandate_vals.update(field_dict)
            mandate_id.with_context(update_feed=True).write(mandate_vals)
            _logger.info('New (updated) mandate.. %s' % mandate_number)
        else:
            mandate_vals = {'partner_id': partner_id.id if partner_id else False,
                            'state': 'signed',
                            'lang': lang_id.code if lang_id else False,
                            'contract_temp_id': template_id.id if template_id else False,
                            'reference': mandate_number,
                            'iban': iban if iban else False,
                            'bic': bic if bic else False,
                            }
            mandate_vals.update(field_dict)
            self.env['mandate.details'].sudo().create(mandate_vals)
            _logger.info('New mandate.. %s' % mandate_number)

        # everything is updated partner/mandate see if any attributes need updating
        if template_id:
            # We found the template, but there might be attributes
            for key in field_dict:
                if key in template_id.attribute_ids.mapped('name'):
                    value = field_dict[key]
                    field_name = 'x_' + key + '_' + str(temp_id)
                    _logger.debug("Update attribute %s = %s" % (field_name,value))
                    mandate_vals.update({field_name: value})
                else:
                    _logger.debug("Could not find attribute %s in template %s" % (key,temp_id))

    def updatedDocument(self, mandate_number, doc, reason):

        partner_id = False
        debtor = doc.get('Dbtr')
        iban = doc.get('DbtrAcct')
        bic = doc.get('DbtrAgt').get('FinInstnId').get('BICFI')
        new_mandate_number = doc.get('MndtId')

        template_id = False
        lang_id = False

        field_dict = self.splmtrAsDict(doc)
        if 'Language' in field_dict:
            lang = field_dict['Language']
            lang_id = self.env['res.lang'].search([('iso_code', '=', lang)])

        if 'TemplateId' in field_dict:
            temp_id = field_dict['TemplateId']
            template_id = self.env['twikey.contract.template'].search([('template_id', '=', temp_id)],limit=1)

        address = False
        zip = False
        city = False
        country_id = False
        email = False
        if debtor and 'PstlAdr' in debtor:
            address_line = debtor.get('PstlAdr')
            address = address_line.get('AdrLine') if address_line.get('AdrLine') else False
            zip = address_line.get('PstCd') if address_line.get('PstCd') else False
            city = address_line.get('TwnNm') if address_line.get('TwnNm') else False
            country_id = self.env['res.country'].search([('code', '=', address_line.get('Ctry'))])

        # Find by customernumber
        if 'CtctDtls' in debtor:
            contact_details = debtor.get('CtctDtls')
            if "Othr" in contact_details:
                customer_number = contact_details.get('Othr')
                try:
                    lookup_id = int(customer_number)
                    partner_id = self.env['res.partner'].browse(lookup_id)
                except:
                    _logger.info('Customer not found by %s' % customer_number)
                    return
            if "EmailAdr" in contact_details:
                email = contact_details.get('EmailAdr')
                partner_id = self.env['res.partner'].search([('email', '=', email)])

        # Find by name if not found
        if not partner_id:
            if debtor.get('Nm'):
                partner_id = self.env['res.partner'].search([('name', '=', debtor.get('Nm'))])
            if not partner_id:
                partner_id = self.env['res.partner'].create({'name' : debtor.get('Nm')})

        if partner_id:
            partner_id.with_context(update_feed=True).write({'street' : address,
                                                             'zip' : zip,
                                                             'city' : city,
                                                             'country_id' : country_id.id if country_id else False,
                                                             'email' : email
                                                             })

        mandate_id = self.env['mandate.details'].search([('reference', '=', mandate_number)])
        new_state = 'suspended' if reason["Rsn"] and reason["Rsn"] == 'uncollectable|user' else 'signed'
        if mandate_id:
            mandate_vals = {'partner_id': partner_id.id if partner_id else False,
                            'state': new_state,
                            'lang': lang_id.code if lang_id else False,
                            'contract_temp_id': template_id.id if template_id else False,
                            'reference': new_mandate_number,
                            'iban': iban if iban else False,
                            'bic': bic if bic else False
                            }
            mandate_vals.update(field_dict)
            mandate_id.with_context(update_feed=True).write(mandate_vals)
            _logger.info("Update %s b/c %s" % (mandate_number, reason["Rsn"]))
        else:
            mandate_vals = {'partner_id': partner_id.id if partner_id else False,
                            'state': new_state,
                            'lang': lang_id.code if lang_id else False,
                            'contract_temp_id': template_id.id if template_id else False,
                            'reference': new_mandate_number,
                            'iban': iban if iban else False,
                            'bic': bic if bic else False,
                            }
            mandate_vals.update(field_dict)
            self.env['mandate.details'].sudo().create(mandate_vals)
            _logger.info("Update (with create of) %s b/c %s" % (mandate_number, reason["Rsn"]))

    def cancelDocument(self, mandateNumber, rsn):
        _logger.info('Response CxlRsn.. %s - %s' % (mandateNumber, rsn["Rsn"]))
        mandate_id = self.env['mandate.details'].search([('reference', '=', mandateNumber)])
        if mandate_id:
            mandate_id.with_context(update_feed=True).write({'state' : 'cancelled', 'description' : 'Cancelled with reason : '+rsn["Rsn"]})
        else:
            self.env['mandate.details'].sudo().create({
                'reference' : mandateNumber,
                'state' : 'cancelled'
            })
