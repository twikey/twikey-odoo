<p align="center">
  <img src="https://cdn.twikey.net/img/v2/partners/odoo-twikey.png" width="128" height="128"/>
</p>
<h1 align="center">Twikey integration for Odoo 16</h1>

* * *

The Twikey plugin provides a convenient integration with Twikey, **a payment service provider specializing in recurring payments and payments for returning customers**.

Installing the Twikey plugin in Odoo allows an automated and efficient financial workflow whether you use the e-commerce functionality of Odoo through your online shop or use Odoo as an invoice generation tool, this plugin allows you as well as your customer to make the payment process as painless as possible. It does this in several ways:

*   **Invite your customers to a recurring payment method** whether it's via direct debit or credit card reducing your financial costs as well as improving your cash flow as the predictable nature of recurring payments (and direct debit in particular) allows businesses to accurately forecast and plan their incoming cash flow.
*   Mandate Management: Twikey offers a comprehensive solution for **managing mandates**. With the Twikey plugin, merchants can efficiently handle the creation, modification, and cancellation of mandates directly from within Odoo. This simplifies mandate management and ensures compliance with relevant regulations.
*   The existing Sepa mandates as well as any recurring credit card your customer can be used for **registering payments** either in a customer flow in the online show or when you're on your monthly billing run. The heavy lifting of sending the transactions to one or more banks or downstream payment providers is being done in Twikey where you can configure how those transactions are finally sent to either one or more banks/payment providers.
*   Direct Debit Payments: Via Twikey's gateway to multiple banks, the transactions can be directly retrieved from their customer's bank accounts **without the need to ever download/upload files in your bank environment**.
*   A Twikey Provider is available in the list of **Odoo payment providers**, giving your customers a transparent and easy way for future purchases. This lowers the bar making the purchases on your website even easier. The provider can be used for tokenized methods as well as for one-off payments. As some of your customers might not want to pay every invoice in an automated way (e.g. setup invoices)
*   The plugin also reduces the operational overhead by **leveraging the reconciliation engine of Odoo** as well as providing the reconciliation files for use in third-party accounting software, reducing the need for manual intervention and minimizing errors. This automation saves time and resources, allowing businesses to focus on core activities while maintaining accurate and up-to-date payment records.
*   The plugin synchronizes payment information between Twikey and Odoo, enabling businesses to maintain accurate records and monitor the status of payments. This simplifies the reconciliation process even further and enhances financial visibility.

In summary, installing the Twikey plugin in Odoo provides customers with a comprehensive solution for recurring payment management, mandate handling, and automation. It streamlines payment processes, improves operational efficiency, and facilitates seamless integration with Odoo's existing functionalities.

Once installed
--------------

Once the plugin is installed, you'll be able to do the following:

*   have a mandate overview in the Contacts menu
*   invite a specific (or range) of customer to do their payments via Direct Debit instead of costly creditcard
*   confirmed invoices generated through a sales order can either be sent with or without pdf to Twikey
*   qr code going to the Twikey paypage where the state of the page is directly visible
*   qr code also usable in belgian bank apps
*   payment links via the Odoo payment provider
*   payment tokens are registered automatically allowing payment registration
*   creation of one or multiple payment methods via the Odoo payment providers, supporting both tokenisation as well as one-time payments.
*   allow usage of multiple bank accounts for direct debit collection
*   allow usage of multiple payment provider for different payment methods
*   see updates about customer actions in a dedicated chat channel

Next to these actions, a couple of cron jobs will update your odoo environment if webhooks aren't enabled/available in your setup for real-time feedback.

Configuration
-------------

Configuration is really straightforward. Once the plugin is installed, head to the settings and paste the api url and key you copied from the [Twikey Api settings](https://www.twikey.com/r/admin/#/c/settings/api).

*   Be sure to test the connectivity ensuring there is no network issue between your odoo environment and Twikey
*   Synchronise the Twikey profiles so you can start using the plugin right a way
*   \[Only for ecommerce\] Head to "Payment providers" and duplicate the default while setting the correct profile and payment method. Note: be sure to enable the payment method in the profile on Twikey side as it is doing a direct call to the [sign api](//www.twikey.com/api/#sign-a-mandate)

Installation - Support
----------------------

For installation support, contact your own integrator who installed your Odoo set-up.

Or contact one of our partners: [Twikey Odoo integrators](https://www.twikey.com/partner/odoo.html)
