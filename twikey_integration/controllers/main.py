# -*- coding: utf-8 -*-

import logging
import pprint

from odoo import http
from odoo.http import request, Response

from werkzeug.urls import url_unquote

from ..twikey.webhook import Webhook

_logger = logging.getLogger(__name__)


class TwikeyController(http.Controller):
    
    @http.route('/twikey', type='http', auth='public', csrf=False)
    def twikey_return(self, **post):
        """ Twikey"""
        payload = url_unquote(request.httprequest.query_string)
        received_sign = request.httprequest.headers.get('X-Signature')
        api_key = request.env['ir.config_parameter'].get_twikey_api_key()
        if not Webhook.verify_signature(payload, received_sign, api_key):
            _logger.warning("Twikey: failed signature verification %s", pprint.pformat(post))
            return Response(status=403)

        if post.get("msg") == "dummytest":
            _logger.info("Twikey Webhook test successfull!")
            return "OK"

        _logger.info('Twikey: entering form_feedback with post data %s', pprint.pformat(post))
        if post and post.get('mandateNumber'):
            # See https://www.twikey.com/api/#webhooks
            if post.get('type') == 'contract':
                # Removal of a prepared mandate doesn't show up in the feed
                if post.get('event') == 'Invite' and post.get('reason') == 'removed':
                    mandate_id = request.env['mandate.details'].sudo().search([('reference', '=', post.get('mandateNumber'))])
                    if mandate_id:
                        mandate_id.with_context(update_feed=True).sudo().unlink()
                elif post.get('event') == 'Sign':
                    mandate_id = request.env['mandate.details'].sudo().search([('reference', '=', post.get('mandateNumber'))])
                    if mandate_id:
                        mandate_id.with_context(update_feed=True).sudo().write({'state': 'signed'})
                else:
                    mandate_obj = request.env['mandate.details']
                    mandate_obj.sudo().update_feed()
            elif post.get('type') == 'payment':
                invoice_obj = request.env['account.invoice']
                invoice_obj.sudo().update_invoice_feed()
                return "OK"
        else:
            return "OK"
