from unittest.mock import patch

from odoo.fields import Command
from odoo.tests import tagged

from .common import TwikeyOdooCase


@tagged("post_install", "-at_install")
class TestModelAccountMove(TwikeyOdooCase):
    def test_send_invoices(self):
        """Only invoices are selected that match the company of the client."""
        self.assertTrue(self.invoice1.is_twikey_eligable)
        self.assertTrue(self.invoice2.is_twikey_eligable)
        self.invoice1.btn_send_to_twikey()
        self.invoice2.btn_send_to_twikey()
        self.assertTrue(self.invoice1.send_to_twikey)
        self.assertTrue(self.invoice2.send_to_twikey)

        def transfer_to_twikey(invoices, client):
            """Ensure only invoice1 is sent."""
            self.assertEqual(invoices, self.invoice1)
            self.assertEqual(client.api_key, invoices.company_id.twikey_api_key)

        with patch(
            "odoo.addons.payment_twikey.models.account_move.AccountInvoice.transfer_to_twikey",
            new=transfer_to_twikey,
        ):
            with patch(
                "odoo.addons.payment_twikey.twikey.client.TwikeyClient.refreshTokenIfRequired"
            ):
                self.env.ref(
                    "payment_twikey.action_send_invoices_to_twikey"
                ).with_company(self.company1).run()

    def test_send_invoices_cron(self):
        """In cron mode, invoices are sent for all companies."""
        self.assertTrue(self.invoice1.is_twikey_eligable)
        self.assertTrue(self.invoice2.is_twikey_eligable)
        self.invoice1.btn_send_to_twikey()
        self.invoice2.btn_send_to_twikey()
        self.assertTrue(self.invoice1.send_to_twikey)
        self.assertTrue(self.invoice2.send_to_twikey)

        sent_invoices = []

        def transfer_to_twikey(invoices, client):
            """Collect sent invoices for later inspection."""
            invoices.env.context["sent_invoices"].append(invoices)

        with patch(
            "odoo.addons.payment_twikey.models.account_move.AccountInvoice.transfer_to_twikey",
            new=transfer_to_twikey,
        ):
            with patch(
                "odoo.addons.payment_twikey.twikey.client.TwikeyClient.refreshTokenIfRequired"
            ):
                self.env.ref(
                    "payment_twikey.twikey_invoice_sender"
                ).with_context(sent_invoices=sent_invoices).ir_actions_server_id.run()

        self.assertEqual(len(sent_invoices), 2)
        self.assertIn(self.invoice1, sent_invoices)
        self.assertIn(self.invoice2, sent_invoices)

    def test_invoice_create(self):
        """Invoices are assigned the parameters according to their company.

        (and not the company of the environment).
        """
        self.company1.twikey_send_pdf = True
        self.company2.twikey_send_pdf = False
        invoice_company1 = (
            self.env["account.move"]
            .sudo()
            .with_company(self.company2)
            .create(
                {
                    "company_id": self.company1.id,
                    "move_type": "out_invoice",
                    "invoice_date": "2017-01-01",
                    "date": "2017-01-01",
                    "partner_id": self.partner_a.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "test line",
                                "price_unit": 0.025,
                                "quantity": 1,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                            }
                        )
                    ],
                }
            )
        )
        invoice_company2 = (
            self.env["account.move"]
            .sudo()
            .with_company(self.company1)
            .create(
                {
                    "company_id": self.company2.id,
                    "move_type": "out_invoice",
                    "invoice_date": "2017-01-01",
                    "date": "2017-01-01",
                    "partner_id": self.partner_a.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "test line",
                                "price_unit": 0.025,
                                "quantity": 1,
                                "account_id": self.company_data_2[
                                    "default_account_revenue"
                                ].id,
                            }
                        )
                    ],
                }
            )
        )
        self.assertTrue(invoice_company1.include_pdf_invoice)
        self.assertFalse(invoice_company2.include_pdf_invoice)

    def test_compute_twikey_url(self):
        self.assertFalse(self.invoice1.id_and_link_html)
        self.invoice1.twikey_invoice_identifier = "123"
        self.assertIn("https://app.twikey.com/0/123", self.invoice1.id_and_link_html)

    def test_compute_twikey_url_company(self):
        """Client is fetched with the company of the invoice."""

        def geturl(klass, invoice_identifier):
            """The invoice_identifier is set to the api_key of the invoice's company.

            Check that the client matches the company by comparing the api key.
            """
            self.assertEqual(invoice_identifier, klass.client.api_key)
            return invoice_identifier

        with patch(
            "odoo.addons.payment_twikey.twikey.invoice.Invoice.geturl",
            new=geturl,
        ):
            self.invoice1.twikey_invoice_identifier = (
                self.invoice1.company_id.twikey_api_key
            )
            self.invoice2.twikey_invoice_identifier = (
                self.invoice2.company_id.twikey_api_key
            )
            self.env["account.move"].flush_model()
