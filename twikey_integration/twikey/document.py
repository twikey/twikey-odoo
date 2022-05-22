import requests
import logging

__all__ = ["Document", "DocumentFeed"]

class Document(object):

    def __init__(self, client) -> None:
        super().__init__()
        self.client = client
        self.logger = logging.getLogger(__name__)

    def create(self, data):
        url = self.client.instance_url("/invite")
        data = data or {}
        self.client.refreshTokenIfRequired()
        response = requests.post(url=url, data=data, headers=self.client.headers())
        json_response = response.json()
        if "ApiErrorCode" in response.headers:
            raise self.client.raise_error("Invite", response)
        self.logger.debug("Added new mandate : %s" % json_response.mndtId)
        return json_response

    def update(self, data):
        url = self.client.instance_url("/mandate/update")
        data = data or {}
        self.client.refreshTokenIfRequired()
        response = requests.post(url=url, data=data, headers=self.client.headers())
        self.logger.debug("Updated mandate : %s response=%s" % (data,response))
        if "ApiErrorCode" in response.headers:
            raise self.client.raise_error("Update", response)

    def cancel(self, mandate_number, reason):
        url = self.client.instance_url("/mandate?mndtId=" + mandate_number + '&rsn=' + reason)
        self.client.refreshTokenIfRequired()
        response = requests.delete(url=url, headers=self.client.headers())
        self.logger.debug("Updated mandate : %s status=%d" % (mandate_number,response.status_code))
        if "ApiErrorCode" in response.headers:
            raise self.client.raise_error("Cancel", response)

    def feed(self, documentFeed):
        url = self.client.instance_url("/mandate")

        self.client.refreshTokenIfRequired()
        response = requests.get(url=url, headers=self.client.headers())
        response.raise_for_status()
        if "ApiErrorCode" in response.headers:
            raise self.client.raise_error("Feed", response)
        feed_response = response.json()
        while len(feed_response["Messages"]) > 0:
            self.logger.debug("Feed handling : %d" % (len(feed_response["Messages"])))
            for msg in feed_response["Messages"]:
                if "AmdmntRsn" in msg:
                    mndt_id_ = msg["OrgnlMndtId"]
                    self.logger.debug("Feed update : %s" % (mndt_id_))
                    mndt_ = msg["Mndt"]
                    rsn_ = msg["AmdmntRsn"]
                    documentFeed.updatedDocument(mndt_id_, mndt_, rsn_)
                elif "CxlRsn" in msg:
                    self.logger.debug("Feed cancel : %s" % (msg["OrgnlMndtId"]))
                    documentFeed.cancelDocument(msg["OrgnlMndtId"], msg["CxlRsn"])
                else:
                    self.logger.debug("Feed create : %s" % (msg["Mndt"]))
                    documentFeed.newDocument(msg["Mndt"])
            response = requests.get(url=url, headers=self.client.headers())
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Feed", response)
            feed_response = response.json()


class DocumentFeed:
    def newDocument(self, doc):
        pass

    def updatedDocument(self, mandate_number, doc, reason):
        pass

    def cancelDocument(self, docNumber, reason):
        pass
