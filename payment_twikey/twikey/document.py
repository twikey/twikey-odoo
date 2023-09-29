import logging

import requests


class Document(object):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client
        self.logger = logging.getLogger(__name__)

    def create(self, data):
        url = self.client.instance_url("/invite")
        data = data or {}
        try:
            self.client.refreshTokenIfRequired()
            response = requests.post(url=url, data=data, headers=self.client.headers(), timeout=15)
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Invite", response)
            json_response = response.json()
            self.logger.debug("Added new mandate : %s" % json_response["mndtId"])
            return json_response
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Invite", e)

    def sign(self, data):  # pylint: disable=W8106
        url = self.client.instance_url("/sign")
        data = data or {}
        try:
            self.client.refreshTokenIfRequired()
            response = requests.post(url=url, data=data, headers=self.client.headers(), timeout=15)
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Sign", response)
            json_response = response.json()
            self.logger.debug("Added new mandate : %s" % json_response["MndtId"])
            return json_response
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Sign", e)

    def update(self, data):
        url = self.client.instance_url("/mandate/update")
        data = data or {}
        try:
            self.client.refreshTokenIfRequired()
            response = requests.post(url=url, data=data, headers=self.client.headers(), timeout=15)
            self.logger.debug("Updated mandate : {} response={}".format(data, response))
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Update", response)
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Update", e)

    def cancel(self, mandate_number, reason):
        url = self.client.instance_url("/mandate?mndtId=" + mandate_number + "&rsn=" + reason)
        try:
            self.client.refreshTokenIfRequired()
            response = requests.delete(url=url, headers=self.client.headers(), timeout=15)
            self.logger.debug("Cancel mandate : %s status=%d" % (mandate_number, response.status_code))
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Cancel", response)
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Cancel", e)

    def feed(self, document_feed, start_position=False):
        url = self.client.instance_url("/mandate?include=id&include=mandate&include=person")
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
                raise self.client.raise_error("Feed", response)
            feed_response = response.json()
            while len(feed_response["Messages"]) > 0:
                self.logger.debug("Feed handling : %d from %s till %s" % (
                    len(feed_response["Messages"]), start_position, response.headers["X-LAST"]))
                document_feed.start(response.headers["X-LAST"], len(feed_response["Messages"]))
                error = False
                for msg in feed_response["Messages"]:
                    if "AmdmntRsn" in msg:
                        mndt_id_ = msg["OrgnlMndtId"]
                        self.logger.debug("Feed update : %s" % mndt_id_)
                        mndt_ = msg["Mndt"]
                        rsn_ = msg["AmdmntRsn"]
                        at_ = msg["EvtTime"]
                        error = document_feed.updated_document(mndt_id_, mndt_, rsn_, at_)
                    elif "CxlRsn" in msg:
                        mndt_ = msg["OrgnlMndtId"]
                        rsn_ = msg["CxlRsn"]
                        at_ = msg["EvtTime"]
                        self.logger.debug("Feed cancel : %s" % mndt_)
                        error = document_feed.cancelled_document(mndt_, rsn_, at_)
                    else:
                        mndt_ = msg["Mndt"]
                        at_ = msg["EvtTime"]
                        self.logger.debug("Feed create : %s" % mndt_)
                        error = document_feed.new_document(mndt_, at_)
                    if error:
                        break
                if error:
                    self.logger.debug("Error while handing invoice, stopping")
                    break
                response = requests.get(url=url, headers=self.client.headers(), timeout=15, )
                if "ApiErrorCode" in response.headers:
                    raise self.client.raise_error("Feed", response)
                feed_response = response.json()
            self.logger.debug("Done handing mandate feed")
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Mandate feed", e)

    def update_customer(self, customer_id, data):
        url = self.client.instance_url("/customer/" + str(customer_id))
        try:
            self.client.refreshTokenIfRequired()
            response = requests.patch(url=url, params=data, headers=self.client.headers(), timeout=15)
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Cancel", response)
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Update customer", e)


class DocumentFeed:
    def start(self, position, number_of_updates):
        """
        Allow storing the start of the feed
        :param position: position where the feed started
        :param number_of_updates: number of items in the feed
        """
        pass

    def new_document(self, doc, evt_time):
        """
        Handle a newly available document
        :param doc: actual document
        :param evt_time: time of creation
        """
        pass

    def updated_document(self, original_doc_number, doc, reason, evt_time):
        """
        Handle an update of a document
        :param original_doc_number: original reference to the document
        :param doc: actual document
        :param reason: reason of change
        :param evt_time: time of creation
        """
        pass

    def cancelled_document(self, doc_number, reason, evt_time):
        """
        Handle an cancelled document
        :param doc_number: reference to the document
        :param reason: reason of change
        :param evt_time: time of creation
        """
        pass
