import logging
import pprint

from werkzeug.urls import url_unquote

from odoo import http
from odoo.http import Response, request

from ..twikey.webhook import Webhook

_logger = logging.getLogger(__name__)


class TwikeyController(http.Controller):

    @http.route(["/twikey/<int:company_id>","/twikey"], type="http", auth="public", methods=['GET'], csrf=False, save_session=False)
    def twikey_webhook(self, **post):
        """Twikey webhook will trigger either the document feed to get updates of documents persisted in Odoo
        Payments from the bank will trigger the invoice feed allowing invoices to be handled too.
        If in an eCommerce setting, the trigger of a payment to a link will cause the transaction to be updated"""
        if post.get("company_id"):
            company = request.env["res.company"].sudo().browse(post["company_id"])
            if company.exists():
                api_key = company.twikey_api_key
            else:
                _logger.warning("Twikey: no company found %s", pprint.pformat(post))
                return Response(response="not yet configured", status=403)
        else:
            api_key = request.env.company.twikey_api_key
        return self.handle_webhook(api_key,**post)

    def handle_webhook(self, api_key, **post):
        if not api_key:
            _logger.warning("Twikey: not yet configured %s", pprint.pformat(post))
            return Response(response="not yet configured", status=403)

        payload = url_unquote(request.httprequest.query_string)
        received_sign = request.httprequest.headers.get("X-Signature")

        if not post or not Webhook.verify_signature(payload, received_sign, api_key):
            _logger.warning("Twikey: failed signature verification %s", pprint.pformat(post))
            return Response(response="invalid signature", status=403)

        _logger.info("Twikey: entering webhook with post data %s", pprint.pformat(post))
        webhooktype = post.get("type")
        if webhooktype == "payment":
            if post.get("id"):
                request.env['payment.transaction'].sudo()._handle_notification_data('twikey', post)
            else:
                request.env["account.move"].sudo().update_invoice_feed()
            return Response(status=204)
        elif webhooktype == "contract":
            mandate_number = post.get("mandateNumber")
            if mandate_number:
                # Removal of a prepared mandate doesn't show up in the feed
                mandate_id = (
                    request.env["twikey.mandate.details"]
                    .sudo()
                    .search([("reference", "=", mandate_number)])
                )
                if mandate_id:
                    event = post.get("event")
                    if event == "Invite":
                        reason = post.get("reason")
                        if reason == "removed":
                            _logger.info(f"Removing twikey mandate {mandate_number}")
                            mandate_id.with_context(update_feed=True).unlink()
                        elif reason == "expired":
                            if mandate_id.contract_temp_id.mandate_number_required:
                                _logger.info(f"Not removing expired (mandate_number_required) {mandate_number}")
                                mandate_id.message_post(body=f"Ignoring expiry for Twikey mandate {mandate_number}")
                            else:
                                _logger.info(f"Removing expired twikey mandate {mandate_number}")
                                mandate_id.with_context(update_feed=True).unlink()
                        else:
                            _logger.warning("Unknown twikey mandate event of type "+event)
                    else:
                        if event not in ["Sign", "Update"]:
                            _logger.info("Unknown twikey mandate event of type "+event)
                        request.env["twikey.mandate.details"].sudo().update_feed()
                else:
                    request.env["twikey.mandate.details"].sudo().update_feed()
            return Response(status=204)
        elif webhooktype == "event" and post.get("msg") == "dummytest":
            _logger.info("Twikey Webhook test successful!")
            return Response(status=204)
        else:
            return Response(status=204)

    @http.route("/twikey/status", type='http', auth='public', methods=['GET', 'POST'], csrf=False, save_session=False)
    def twikey_return_from_checkout(self, **data):
        """
        :param dict data: The notification data (only `id`) and the transaction reference (`ref`)
                          embedded in the return URL
        """
        _logger.info("handling redirection from Twikey with data: %s", pprint.pformat(data))
        request.env['payment.transaction'].sudo()._handle_notification_data('twikey', data)
        return request.redirect('/payment/status')
