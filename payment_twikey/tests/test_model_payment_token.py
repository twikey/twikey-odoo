from odoo.tests import TransactionCase


class TestModelPaymentToken(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.token = cls.env["payment.token"].create(
            {
                "provider_id": cls.env.ref("payment_twikey.payment_provider_twikey").id,
                "partner_id": cls.env.user.partner_id.id,
                "provider_ref": __name__,
            }
        )

    def test_build_display_name_iban(self):
        self.token.payment_details = "NL28DEUT0265186439"
        self.assertEqual(
            self.token._build_display_name(),
            "Via account NL28••••••••••6439",
        )

    def test_build_display_name_credit_card(self):
        self.token.type = "CC"
        self.token.payment_details = "123"
        self.assertEqual(
            self.token._build_display_name(),
            "Via card ending in 123",
        )
