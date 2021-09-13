# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, exceptions, _
import requests
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    twikey_reference = fields.Char(string="Twikey Reference", copy = False, help="Twikey Customer Number will be save in this field.")
    mandate_ids = fields.One2many('mandate.details', 'partner_id', string="Mandates")
    twikey_inv_ids = fields.One2many('account.invoice', 'partner_id', readonly=True, copy=False,compute='_compute_invoice_ids')

    def _compute_invoice_ids(self):
        for res in self:
            flt_invoice = res.invoice_ids.filtered(lambda x: x.type == 'out_invoice' and x.twikey_invoice_id != False)
            res.twikey_inv_ids = [(6, 0, [x.id for x in flt_invoice])]

    def action_invite_customer(self):
        module_twikey = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.module_twikey')
        if module_twikey:
            authorization_token=self.env['ir.config_parameter'].sudo().get_param('twikey_integration.authorization_token')
            if authorization_token:
                self.env['res.config.settings'].sync_contract_template()
                action = self.env.ref('twikey_integration.contract_template_wizard_action').read()[0]
                return action
            else:
                raise UserError(_("Authorization Token Not Found, Please Run Authenticate Twikey Scheduled Actions Manually!!!"))
        else:
            raise UserError(_('Please enable Twikey integration from Settings.'))
    
    @api.multi
    def write(self, values):
        res = super(ResPartner, self).write(values)
        if not self._context.get('update_feed'):
          for rec in self:
              authorization_token = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.authorization_token')
              base_url = self.env['ir.config_parameter'].sudo().get_param('twikey_integration.base_url')

              customer_name = ''
              if rec.company_type == 'person':
                  if values.get('name'):
                      customer_name = values.get('name').split(' ')
                  else:
                      customer_name = rec.name.split(' ')
              country_id = False
              if values.get('country_id'):
                  country_id = self.env['res.country'].browse(values.get('country_id'))

              data = {
                      'email': values.get('email') if values.get('email') else rec.email if rec.email else '',
                      'firstname': customer_name[0] if customer_name and rec.company_type == 'person' else '',
                      'lastname': customer_name[1] if customer_name and len(customer_name) > 1 and rec.company_type == 'person' else '',
                      'companyName': values.get('name') if values.get('name') and rec.company_type == 'company' else rec.name if rec.company_type == 'company' else '',
                      'vatno': values.get('vat') if values.get('vat') and rec.company_type == 'company' else rec.vat if rec.vat and rec.company_type == 'company' else '',
                      'customerNumber': values.get('twikey_reference') if values.get('twikey_reference') else rec.twikey_reference if rec.twikey_reference else '',
                      'address': values.get('street') if values.get('street') else rec.street if rec.street else '',
                      'city': values.get('city') if values.get('city') else rec.city if rec.city else '',
                      'zip': values.get('zip') if values.get('zip') else rec.zip if rec.zip else '',
                      'country': country_id.code if country_id != False else rec.country_id.code if rec.country_id else ''
                      }
              print('=============================================')
              if rec.mandate_ids:
                  mandate_id = rec.mandate_ids[0]
                  print("===============",mandate_id.reference)
                  data.update({'mndtId': mandate_id.reference})
                  try:
                      response = requests.post(base_url + "/creditor/mandate/update", data=data, headers={'Authorization': authorization_token})
                      print("response",response)
                      _logger.debug('Updating customer details of mandate %s %s' % (mandate_id, response))
                      _logger.info('Updating customer details of mandate %s %d' % (mandate_id,response.status_code))
                      if response.status_code != 204:
                          raise UserError(_('%s') % (response.json().get('message')))
                  except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.MissingSchema,
                          requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                      _logger.error('Exception raised while updating customer details to Twikey %s' % (e))
                      raise exceptions.AccessError(_('The url that this service requested returned an error. Please check your connection or try after sometime.'))
              else:
                  print('=============================================')
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
