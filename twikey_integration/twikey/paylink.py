import json

import requests


class Paylink(object):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client

    def create(self, data):  # pylint: disable=W8106
        url = self.client.instance_url("/payment/link")
        data = data or {}
        self.client.refreshTokenIfRequired()
        response = requests.post(
            url=url,
            data=data,
            headers=self.client.headers(),
            timeout=15,
        )
        response_text = json.loads(response.text)
        if "code" in response_text:
            if "err" in response_text["code"]:
                error = response.json()
                raise Exception("Error creating paylink : %s" % error)
        return response.json()

    def feed(self, paylinkFeed):
        url = self.client.instance_url("/payment/link/feed")

        self.client.refreshTokenIfRequired()
        response = requests.get(
            url=url,
            headers=self.client.headers(),
            timeout=15,
        )
        response.raise_for_status()
        response_text = json.loads(response.text)
        if "code" in response_text:
            if "err" in response_text["code"]:
                error = response.json()
                raise Exception("Error feed : %s" % error)
        feed_response = response.json()
        while len(feed_response["Links"]) > 0:
            for msg in feed_response["Links"]:
                paylinkFeed.paylink(msg)
            response = requests.get(
                url=url,
                headers=self.client.headers(),
                timeout=15,
            )
            response_text = json.loads(response.text)
            if "code" in response_text:
                if "err" in response_text["code"]:
                    error = response.json()
                    raise Exception("Error feed : %s" % error)
            feed_response = response.json()


class PaylinkFeed:
    def paylink(self, paylink):
        pass
