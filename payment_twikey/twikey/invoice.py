import logging

import requests


class Invoice(object):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client
        self.logger = logging.getLogger(__name__)

    def create(self, data, origin=False, purpose=False, manual=False):
        url = self.client.instance_url("/invoice")
        data = data or {}
        try:
            self.client.refreshTokenIfRequired()
            headers = self.client.headers("application/json")
            if origin:
                headers["X-PARTNER"] = origin
            if purpose:
                headers["X-Purpose"] = purpose
            if manual:
                headers["X-MANUAL"] = "true"
            response = requests.post(
                url=url,
                json=data,
                headers=headers,
                timeout=15,
            )
            json_response = response.json()
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Create invoice", response)
            self.logger.debug("Added invoice : %s" % json_response["url"])
            return json_response
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Create invoice", e)

    def update(self, invoice_id, data):
        url = self.client.instance_url("/invoice/"+invoice_id)
        data = data or {}
        try:
            self.client.refreshTokenIfRequired()
            headers = self.client.headers("application/json")
            response = requests.put(url=url, json=data, headers=headers, timeout=15)
            json_response = response.json()
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Update invoice", response)
            self.logger.debug("Updated invoice : %s" % json_response["url"])
            return json_response
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Update invoice", e)

    #include=meta&include=lastpayment
    def feed(self, invoice_feed, start_position=False, *includes):
        _includes = ""
        for include in includes:
            _includes += "&include=" + include

        url = self.client.instance_url("/invoice?include=customer" + _includes)
        try:
            self.client.refreshTokenIfRequired()
            initheaders = self.client.headers()
            if start_position:
                initheaders["X-RESUME-AFTER"] = str(start_position)
            response = requests.get(
                url=url,
                headers=initheaders,
                timeout=15,
            )
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Feed invoice", response)
            feed_response = response.json()
            while len(feed_response["Invoices"]) > 0:
                number_of_invoices = len(feed_response["Invoices"])
                last_invoice = response.headers["X-LAST"]
                self.logger.debug("Feed handling : %d invoices from %s till %s" %
                                  (number_of_invoices, start_position, last_invoice))
                invoice_feed.start(response.headers["X-LAST"], len(feed_response["Invoices"]))
                error = False
                for invoice in feed_response["Invoices"]:
                    self.logger.debug("Feed handling : %s" % invoice)
                    error = invoice_feed.invoice(invoice)
                    if error:
                        break
                if error:
                    self.logger.debug("Error while handing invoice, stopping")
                    break
                response = requests.get(url=url, headers=self.client.headers(), timeout=15, )
                if "ApiErrorCode" in response.headers:
                    raise self.client.raise_error("Feed invoice", response)
                feed_response = response.json()
            self.logger.debug("Done handing invoice feed")
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Invoice feed", e)

    def geturl(self, invoice_id):
        if '.beta.' in self.client.api_base:
            return "https://app.beta.twikey.com/%s/%s" % (
                self.client.merchant_id,
                invoice_id,
            )
        return "https://app.twikey.com/%s/%s" % (
            self.client.merchant_id,
            invoice_id,
        )


class InvoiceFeed:
    def start(self, position, lenght):
        """
        Allow storing the start of the feed
        :param position: position where the feed started
        :param lenght: number of items in the feed
        """
        pass

    def invoice(self, invoice):
        """
        Handle an invoice of the feed
        :param invoice: the updated invoice
        :return: error from the function or False to continue
        """
        pass
