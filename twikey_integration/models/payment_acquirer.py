# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models, service

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
            ("sms", "sms"),
            ("itsme", "itsme"),
            ("emachtiging", "emachtiging"),
            ("idin", "idin"),
            ("ideal", "ideal"),
            ("visa", "visa"),
            ("mastercard", "mastercard"),
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
        existing_token = self.env['payment.token'].sudo().search([
            ('provider_id', '=', self.id),
            ('provider_ref', '=', mandate_id.reference)
        ])

        active = mandate_id.is_signed()
        if existing_token:
            existing_token.update({'active': active})
            return

        if mandate_id.is_creditcard():
            last_digits = mandate_id.get_attribute("_last")
            expiry = mandate_id.get_attribute("_expiry")

            self.env['payment.token'].create({
                'payment_details': last_digits,
                'provider_id': self.id,
                'partner_id': partner_id.id,
                'provider_ref': mandate_id.reference,
                'active': active,
                'expiry': expiry,
                'type': 'CC',
            })
        else:
            self.env['payment.token'].create({
                'payment_details': mandate_id.iban,
                'provider_id': self.id,
                'partner_id': partner_id.id,
                'provider_ref': mandate_id.reference,
                'active': active,
                'type': 'SDD',
            })
