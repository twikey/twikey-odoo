import requests


class Paylink(object):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client

    def create(self, data):
        url = self.client.instance_url("/payment/link")
        data = data or {}
        self.client.refreshTokenIfRequired()
        response = requests.post(url=url, data=data, headers=self.client.headers())
        if "ApiErrorCode" in response.headers:
            error = response.json()
            raise Exception("Error creating paylink : %s" % error)
        return response.json()

    def feed(self, paylinkFeed):
        url = self.client.instance_url("/payment/link/feed")

        self.client.refreshTokenIfRequired()
        response = requests.get(url=url, headers=self.client.headers())
        response.raise_for_status()
        if "ApiErrorCode" in response.headers:
            error = response.json()
            raise Exception("Error feed : %s" % error)
        feed_response = response.json()
        while len(feed_response["Links"]) > 0:
            for msg in feed_response["Links"]:
                paylinkFeed.paylink(msg)
            response = requests.get(url=url, headers=self.client.headers())
            if "ApiErrorCode" in response.headers:
                error = response.json()
                raise Exception("Error feed : %s" % error)
            feed_response = response.json()


class PaylinkFeed:
    def paylink(self, paylink):
        pass
