import logging
import pprint

from werkzeug.urls import url_unquote

from odoo import http
from odoo.http import Response, request

from ..twikey.webhook import Webhook

_logger = logging.getLogger(__name__)


class TwikeyController(http.Controller):

    @http.route("/twikey", type="http", auth="public", methods=['GET'], csrf=False, save_session=False)
    def twikey_webhook(self, **post):
        """Twikey webhook will trigger either the document feed to get updates of documents persisted in Odoo
        Payments from the bank will trigger the invoice feed allowing invoices to be handled too.
        If in an eCommerce setting, the trigger of a payment to a link will cause the transaction to be updated"""
        payload = url_unquote(request.httprequest.query_string)
        received_sign = request.httprequest.headers.get("X-Signature")
        api_key = request.env.ref("base.main_company").twikey_api_key
        if not post or not Webhook.verify_signature(payload, received_sign, api_key):
            _logger.warning("Twikey: failed signature verification %s", pprint.pformat(post))
            return Response(status=403)

        _logger.info("Twikey: entering webhook with post data %s", pprint.pformat(post))
        webhooktype = post.get("type")
        if webhooktype == "payment":
            if post.get("id"):
                request.env['payment.transaction'].sudo()._handle_notification_data('twikey', post)
            else:
                request.env["account.move"].sudo().update_invoice_feed()
            return "OK"
        elif webhooktype == "contract":
            if post.get("mandateNumber"):
                # Removal of a prepared mandate doesn't show up in the feed
                mandate_id = (
                    request.env["twikey.mandate.details"]
                    .sudo()
                    .search([("reference", "=", post.get("mandateNumber"))])
                )
                if mandate_id:
                    event = post.get("event")
                    if event == "Invite" and post.get("reason") in ["removed", "expired"]:
                        mandate_id.with_context(update_feed=True).unlink()
                    else:
                        if event not in ["Sign", "Update"]:
                            _logger.info("Unknown twikey mandate event of type "+event)
                        request.env["twikey.mandate.details"].sudo().update_feed()
                else:
                    request.env["twikey.mandate.details"].sudo().update_feed()
            return "OK"
        elif webhooktype == "event" and post.get("msg") == "dummytest":
            _logger.info("Twikey Webhook test successful!")
            return "OK"
        else:
            return "OK"

    @http.route("/twikey/status", type='http', auth='public', methods=['GET', 'POST'], csrf=False, save_session=False)
    def twikey_return_from_checkout(self, **data):
        """
        :param dict data: The notification data (only `id`) and the transaction reference (`ref`)
                          embedded in the return URL
        """
        _logger.info("handling redirection from Twikey with data:\n%s", pprint.pformat(data))
        request.env['payment.transaction'].sudo()._handle_notification_data('twikey', data)
        return request.redirect('/payment/status')
