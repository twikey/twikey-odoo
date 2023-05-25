# -*- coding: utf-8 -*-

import logging
import re

from odoo import _, api, fields, models, service

_logger = logging.getLogger(__name__)

class PaymentAcquirer(models.Model):

    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('twikey', 'Twikey')], ondelete={'twikey': 'set default'})
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
        if mandate_id.is_creditcard():
            payment_details = self.build_display({
                "info": mandate_id.get_attribute("_last"),
                "type": 'CC',
                "expiry": mandate_id.get_attribute("_expiry"),
            })
            type = 'CC'
            expiry = mandate_id.get_attribute("_expiry")
        else:
            payment_details = self.build_display({
                "info": mandate_id.iban,
                "type": 'SDD',
                "expiry": False,
            })
            type = 'SDD'
            expiry = False


        existing_token = self.env['payment.token'].sudo().search([
            ('acquirer_id', '=', self.id),
            ('acquirer_ref', '=', mandate_id.reference)
        ])

        active = mandate_id.is_signed()
        if existing_token:
            existing_token.update({
                'name': payment_details,
                'active': active,
                'expiry': expiry,
            })
        else:
            self.env['payment.token'].create({
                'name': payment_details,
                'acquirer_id': self.id,
                'partner_id': partner_id.id,
                'acquirer_ref': mandate_id.reference,
                'active': active,
                'verified': True,
                'expiry': expiry,
                'type': type,
            })

    def build_display(self, data):
        """ Build a token name of the desired maximum length with the format `•••• 1234`.
        """
        info = data.get("info") if data else False
        _logger.info("Using data=%s",data)
        if not info:
            create_date_str = self.create_date.strftime('%Y/%m/%d')
            return _("Payment details saved on %(date)s", date=create_date_str)
        elif len(info) > 8 and re.match('[a-zA-Z]{2}[0-9]{2}.*\d{4}',info):
            iban = info
            masked = iban[:4] + "•"*(len(iban)-8) + iban[-4:]
            return _("Via account %(masked)s", masked=masked)
        elif data.get("type") == 'CC':
            return _("Via card ending in %(last)s", last=info)
        else:  # Not enough room for neither padding nor the payment details.
            return info


    def _get_default_payment_method_id(self):
        self.ensure_one()
        if self.provider != 'twikey':
            return super()._get_default_payment_method_id()
        return self.env.ref('payment_twikey.payment_method_twikey').id
