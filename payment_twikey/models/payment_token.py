# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
import re

class PaymentToken(models.Model):
    _inherit = 'payment.token'
    expiry = fields.Date(string="Expiry", readonly=True)
    type = fields.Selection(
        [
            ("SDD", "SDD"),
            ("CC", "CC"),
        ]
        , readonly=True
    )

    def _build_display_name(self, *args, max_length=34, should_pad=True, **kwargs):
        """ Build a token name of the desired maximum length with the format `•••• 1234`.
        :param list args: The arguments passed by QWeb when calling this method.
        :param int max_length: The desired maximum length of the token name. The default is `34` to
                               fit the largest IBANs.
        :param bool should_pad: Whether the token should be padded.
        :param dict kwargs: Optional data used in overrides of this method.
        :return: The padded token name.
        :rtype: str
        """
        display_name = super()._build_display_name(
            self,
            *args,
            max_length=max_length,
            should_pad=should_pad,
            **kwargs,
        )
        if self.payment_details and self.provider_id == self.env.ref(
            "payment_twikey.payment_provider_twikey"
        ):
            if len(self.payment_details) > 8 and re.match(
                r"[a-zA-Z]{2}[0-9]{2}.*\d{4}", self.payment_details
            ):
                iban = self.payment_details
                masked = iban[:4] + "•" * (len(iban) - 8) + iban[-4:]
                display_name = _("Via account %(masked)s", masked=masked)
            elif self.type == "CC":
                display_name = _(
                    "Via card ending in %(last)s", last=self.payment_details
                )
        return display_name
