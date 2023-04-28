import binascii
import datetime
import hmac
import json
import logging
import struct
import time

import requests

from .document import Document
from .invoice import Invoice
from .paylink import Paylink
from .transaction import Transaction

class TwikeyClient(object):
    lastLogin = None
    api_key = None
    api_token = None  # Once authenticated
    merchant_id = 0  # Once authenticated
    private_key = None
    vendorPrefix = "own"
    api_base = "https://api.twikey.com"

    document = None
    transaction = None
    paylink = None
    invoice = None

    def __init__(
        self,
        api_key,
        base_url="https://api.twikey.com",
        user_agent="twikey-odoo-12/v0.1.0",
    ) -> None:
        self.user_agent = user_agent
        self.api_key = api_key
        self.api_base = base_url
        self.merchant_id = 0
        self.document = Document(self)
        self.transaction = Transaction(self)
        self.paylink = Paylink(self)
        self.invoice = Invoice(self)
        self.logger = logging.getLogger(__name__)

    def instance_url(self, url=""):
        return "{}{}".format(self.api_base, url)

    @staticmethod
    def get_totp(vendorPrefix, secret):
        secret = bytearray(vendorPrefix) + binascii.unhexlify(secret)
        counter = struct.pack(">Q", int(time.time()) // 30)

        import hashlib

        hash = hmac.new(secret, counter, hashlib.sha256).digest()  # pylint: disable=W0622
        offset = ord(hash[19]) & 0xF

        return (struct.unpack(">I", hash[offset : offset + 4])[0] & 0x7FFFFFFF) % 100000000

    def refreshTokenIfRequired(self):
        if self.lastLogin:
            self.logger.debug(
                "Last authenticated with {} with {}".format(self.lastLogin, self.api_token)
            )
        now = datetime.datetime.now()
        if self.lastLogin is None or (now - self.lastLogin).seconds > 23 * 3600:
            payload = {"apiToken": self.api_key}
            if self.private_key:
                payload["otp"] = self.get_totp(self.vendorPrefix, self.private_key)

            if not self.api_base:
                raise TwikeyError(ctx="Config", error_code = "Api-Url", error = "No base url defined - %s" % self.api_base)

            self.logger.debug("Authenticating with {} using {}...".format(self.api_base, self.api_key[0:10]))
            response = requests.post(
                self.instance_url(),
                data=payload,
                headers={"User-Agent": self.user_agent},
                timeout=15,
            )

            if "ApiErrorCode" in response.headers:
                error_json = response.json()
                self.logger.error(error_json)
                raise TwikeyError(ctx="Config", error_code = response.headers["ApiErrorCode"], error = "Error authenticating : %s" % error_json["message"])

            if "X-Rate-Limit-Retry-After-Seconds" in response.headers:
                raise TwikeyError(ctx="Config", error_code = "Rate limit", error = "Too many login's, please try again after %s sec." % (response.headers["X-Rate-Limit-Retry-After-Seconds"]))

            if "Authorization" in response.headers:
                self.api_token = response.headers["Authorization"]
                self.merchant_id = response.headers["X-MERCHANT-ID"]
                self.lastLogin = datetime.datetime.now()
            else:
                raise TwikeyError(ctx="Config", error_code = "Authentication", error = "Invalid response : %s" % str(response))
        else:
            self.logger.debug(
                "Reusing token {} valid till {}".format(self.api_token, self.lastLogin)
            )

    def headers(self, contentType="application/x-www-form-urlencoded"):
        return {
            "Content-type": contentType,
            "Authorization": self.api_token,
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }

    def raise_error(self, context, response):
        self.logger.error("Error in '%s' response %s " % (context, response.text))
        try:
            error_json = response.json()
            extra = error_json["extra"] if "extra" in error_json else False
            return TwikeyError(context, error_json["code"], error_json["message"], extra)
        except requests.exceptions.JSONDecodeError:
            return TwikeyError(context, response.url, response.text)

    def raise_error_from_request(self, context, requestException):
        self.logger.error("Error in '%s' request %s " % (context, requestException))
        return TwikeyError(context, requestException.__class__.__name__, requestException)

    def logout(self):
        self.logger.info("Logging out of Twikey")
        response = requests.get(
            self.instance_url(),
            headers={"User-Agent": self.user_agent},
            timeout=15,
        )
        response_text = json.loads(response.text)
        if "code" in response_text:
            if "err" in response_text["code"]:
                raise TwikeyError(ctx = "Logout",error_code = "Logout", error = response_text["message"])

        self.api_token = None
        self.lastLogin = None


class TwikeyError(Exception):
    """Twikey error."""

    def __init__(self, ctx, error_code, error, extra = False, *args, **kwargs):  # real signature unknown
        super().__init__(args, kwargs)
        self.ctx = ctx
        self.error_code = error_code
        self.error = error
        self.extra = extra

    def __str__(self):
        if self.extra:
            return "[{}] code={}, msg={} extra={}".format(self.ctx, self.error_code, self.error, self.extra)
        return "[{}] code={}, msg={}".format(self.ctx, self.error_code, self.error)
