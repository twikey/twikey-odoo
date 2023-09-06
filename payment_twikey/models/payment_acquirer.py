# -*- coding: utf-8 -*-

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(selection_add=[('twikey', 'Twikey')], ondelete={'twikey': 'set default'})
    name = fields.Char(string="Name", required=True, translate=True)
    twikey_template_id = fields.Many2one(comodel_name="twikey.contract.template", string="Contract Template", index=True)
    twikey_method = fields.Selection(
        [
            ("bancontact", "bancontact"),
            ("sofort", "sofort"),
            # ("sms", "sms"),
            # ("itsme", "itsme"),
            # ("emachtiging", "emachtiging"),
            # ("idin", "idin"),
            ("ideal", "ideal"),
            ("visa", "visa"),
            ("mastercard", "mastercard"),
            ("paypal", "paypal"),
            ("amex", "amex"),
        ],
        help="This will be the method to use to sign mandate"
    )

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable additional features. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'twikey').update({
            'support_refund': 'partial',
            'support_tokenization': True,
        })
        self.filtered(lambda p: p.code == 'twikey').show_credentials_page = False

    def token_from_mandate(self, partner_id, mandate_id):
        if mandate_id.is_creditcard():
            payment_details = mandate_id.get_attribute("_last")
            type = 'CC'
            expiry = mandate_id.get_attribute("_expiry")
        else:
            payment_details = mandate_id.iban
            type = 'SDD'
            expiry = False

        existing_token = self.env['payment.token'].sudo().search([
            ('provider_code', '=', self.code),
            ('provider_ref', '=', mandate_id.reference)
        ])

        active = mandate_id.is_signed()
        if existing_token:
            existing_token.update({
                'payment_details': payment_details,
                'active': active,
                'expiry': expiry,
            })
            return False
        else:
            self.env['payment.token'].create({
                'payment_details': payment_details,
                'provider_id': self.id,
                'partner_id': partner_id.id,
                'provider_ref': mandate_id.reference,
                'active': active,
                'expiry': expiry,
                'type': type,
            })
            return True
