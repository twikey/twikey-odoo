from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestControllerReturnRoute(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref("payment_twikey.payment_provider_twikey")
        cls.provider.state = "test"
        cls.tx = cls.env["payment.transaction"].create(
            {
                "provider_id": cls.provider.id,
                "reference": "TWIKEY-RETURN-ROUTE-TEST",
                "amount": 12.34,
                "currency_id": cls.env.company.currency_id.id,
                "partner_id": cls.env.user.partner_id.id,
                "state": "pending",
            }
        )

    def test_status_paid_in_return_url_leaves_transaction_pending(self):
        response = self.url_open(
            "/twikey/status?ref=%s&status=paid" % self.tx.reference,
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.tx.invalidate_recordset()
        self.assertEqual(self.tx.state, "pending")

    def test_status_canceled_in_return_url_leaves_transaction_pending(self):
        self.url_open(
            "/twikey/status?ref=%s&status=canceled" % self.tx.reference,
            allow_redirects=False,
        )
        self.tx.invalidate_recordset()
        self.assertEqual(self.tx.state, "pending")

    def test_status_paid_from_signed_webhook_marks_transaction_done(self):
        # The signed /twikey webhook passes its data to the same handler
        # without forcing a status, so status=paid must still mark it done.
        self.env["payment.transaction"]._handle_notification_data(
            "twikey", {"ref": self.tx.reference, "status": "paid"}
        )
        self.assertEqual(self.tx.state, "done")
