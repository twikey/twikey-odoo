# -*- coding: utf-8 -*-

import logging
import pprint

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class TwikeyController(http.Controller):
    
    @http.route('/twikey', type='http', auth='public', csrf=False)
    def twikey_return(self, **post):
        """ Twikey"""
        _logger.info(
            'Twikey: entering form_feedback with post data %s', pprint.pformat(post))
        if post:
            if post.get('event') == 'Invite' and post.get('reason') == 'removed':
                mandate_id = request.env['mandate.details'].search([('reference', '=', post.get('mandateNumber'))])
                if mandate_id:
                    mandate_id.with_context(by_controller=True).unlink()