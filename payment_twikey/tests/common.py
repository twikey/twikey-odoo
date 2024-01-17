from odoo.fields import Command

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class TwikeyOdooCase(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company1 = cls.company_data["company"]
        cls.company2 = cls.company_data_2["company"]
        cls.company1.twikey_api_key = "key1"
        cls.company1.twikey_base_url = "https://example.com/api/v2"
        cls.company2.twikey_api_key = "key2"
        cls.company2.twikey_base_url = "https://example.com/api/v2"
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                allowed_company_ids=[cls.company1.id, cls.company2.id]
            )
        )
        cls.invoice1 = cls.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2017-01-01",
                "date": "2017-01-01",
                "partner_id": cls.partner_a.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "test line",
                            "price_unit": 0.025,
                            "quantity": 1,
                            "account_id": cls.company_data[
                                "default_account_revenue"
                            ].id,
                        }
                    )
                ],
            }
        )
        cls.invoice2 = cls.env["account.move"].create(
            {
                "company_id": cls.company2.id,
                "move_type": "out_invoice",
                "invoice_date": "2017-01-01",
                "date": "2017-01-01",
                "partner_id": cls.partner_a.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "test line",
                            "price_unit": 0.025,
                            "quantity": 1,
                            "account_id": cls.company_data_2[
                                "default_account_revenue"
                            ].id,
                        }
                    )
                ],
            }
        )

        cls.invoice1.action_post()
        cls.invoice2.action_post()
