# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentMethod(models.Model):
    _inherit = 'account.payment.method'

    @api.model
    def _get_payment_method_information(self):
        res = super()._get_payment_method_information()
        _logger.info(f"Fetching {self.name} {self.code}")
        res['twikey'] = {'mode': 'multi', 'domain': [('type', '=', 'bank')]}
        return res
