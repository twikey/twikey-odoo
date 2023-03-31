import logging
import pprint

from werkzeug.urls import url_unquote

from odoo import http
from odoo.http import Response, request

from ..twikey.webhook import Webhook

_logger = logging.getLogger(__name__)


class TwikeyController(http.Controller):
    @http.route("/twikey", type="http", auth="public", csrf=False)
    def twikey_return(self, **post):
        """ Twikey"""
        if post.get("msg") == "dummytest":
            _logger.info("Twikey Webhook test successfull!")
        payload = url_unquote(request.httprequest.query_string)
        received_sign = request.httprequest.headers.get("X-Signature")
        api_key = request.env.ref("base.main_company").twikey_api_key
        if not Webhook.verify_signature(payload, received_sign, api_key):
            _logger.warning("Twikey: failed signature verification %s", pprint.pformat(post))
            return Response(status=403)
        _logger.info("Twikey: entering form_feedback with post data %s", pprint.pformat(post))

        if post and post.get("type") == "payment":
            request.env["account.move"].sudo().update_invoice_feed()
            return "OK"
        elif post and post.get("type") == "contract":
            if post.get("mandateNumber"):
                # Removal of a prepared mandate doesn't show up in the feed
                if post.get("event") == "Invite" and post.get("reason") == "removed":
                    mandate_id = (
                        request.env["twikey.mandate.details"]
                        .sudo()
                        .search([("reference", "=", post.get("mandateNumber"))])
                    )
                    if mandate_id:
                        mandate_id.with_context(update_feed=True).unlink()
                elif post.get("event") == "Sign":
                    mandate_id = (
                        request.env["twikey.mandate.details"]
                        .sudo()
                        .search([("reference", "=", post.get("mandateNumber"))])
                    )
                    if mandate_id:
                        mandate_id.with_context(update_feed=True).write({"state": "signed"})
                else:
                    request.env["twikey.mandate.details"].sudo().update_feed()
        else:
            return "OK"
