# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, exceptions, _
import requests
from odoo.exceptions import UserError

from .. import twikey

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    mandate_ids = fields.One2many('mandate.details', 'partner_id', string="Mandates")
    twikey_inv_ids = fields.One2many('account.invoice', 'partner_id', readonly=True, copy=False,compute='_compute_invoice_ids')

    def _compute_invoice_ids(self):
        for res in self:
            flt_invoice = res.invoice_ids.filtered(lambda x: x.type == 'out_invoice' and x.twikey_invoice_id != False)
            res.twikey_inv_ids = [(6, 0, [x.id for x in flt_invoice])]

    def action_invite_customer(self):
        module_twikey = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.module_twikey')
        if module_twikey:
            # authorization_token=self.env['ir.config_parameter'].sudo().get_param('twikey_integration.authorization_token')
            # if authorization_token:
            self.env['res.config.settings'].sync_contract_template()
            action = self.env.ref('twikey_integration.contract_template_wizard_action').read()[0]
            return action
            # else:
            #     raise UserError(_("Authorization Token Not Found, Please Run Authenticate Twikey Scheduled Actions Manually!!!"))
        else:
            raise UserError(_('Please enable Twikey integration from Settings.'))

    @api.multi
    def write(self, values):
        res = super(ResPartner, self).write(values)
        if self._context.get("update_feed"):
            return res
        twikey_client = self.env['ir.config_parameter'].get_twikey_client()
        for rec in self:
            country_id = False
            if values.get('country_id'):
                country_id = self.env['res.country'].browse(values.get('country_id'))

            data = {
                'email': values.get('email') if values.get('email') else rec.email if rec.email else '',
                'customerNumber': rec.id,
                'address': values.get('street') if values.get('street') else rec.street if rec.street else '',
                'city': values.get('city') if values.get('city') else rec.city if rec.city else '',
                'zip': values.get('zip') if values.get('zip') else rec.zip if rec.zip else '',
                'country': country_id.code if country_id != False else rec.country_id.code if rec.country_id else '',
                'l': values.get('lang') if values.get('lang') else rec.lang,
            }

            if rec.company_type == 'company' and values.get('name'):
                data['companyName'] = values.get('name') if values.get('name') else ''
                data['vatno'] = values.get('vat') if values.get('vat') else ''
            elif values.get('name'): # 'person'
                customer_name = values.get('name').split(' ')
                if customer_name and len(customer_name) > 1:
                    data['firstname'] = customer_name[0]
                    data['lastname'] = ' '.join(customer_name[1:])
                else:
                    data['firstname'] = values.get('name')

        if rec.mandate_ids:
                mandate_id = rec.mandate_ids[0]
                data.update({'mndtId': mandate_id.reference})
                try:
                    twikey_client.document.update(data)
                    _logger.debug('Updating customer details of mandate %s' % (mandate_id))
                except (ValueError, requests.exceptions.RequestException) as e:
                    _logger.error('Exception raised while updating customer details to Twikey %s' % (e))
                    raise exceptions.AccessError(
                        _('The url that this service requested returned an error. Please check your connection or try after sometime.'))

        return res
