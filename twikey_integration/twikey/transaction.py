import json

import requests


class Transaction(object):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client

    def create(self, data):  # pylint: disable=W8106
        url = self.client.instance_url("/transaction")
        data = data or {}
        self.client.refreshTokenIfRequired()
        response = requests.post(
            url=url,
            data=data,
            headers=self.client.headers(),
            timeout=15,
        )
        response.raise_for_status()
        response_text = json.loads(response.text)
        if "code" in response_text:
            if "err" in response_text["code"]:
                error = response.json()
                raise Exception("Error sending transaction : %s" % error)
        return response.json()["Entries"][0]

    def feed(self, transactionFeed):
        url = self.client.instance_url("/transaction")

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
        while len(feed_response["Entries"]) > 0:
            for msg in feed_response["Entries"]:
                transactionFeed.transaction(msg)
            response = requests.get(
                url=url,
                headers=self.client.headers(),
                timeout=15,
            )
            response_text = json.loads(response.text)
            if "code" in response_text:
                if "err" in response_text["code"]:
                    error = response.json()
                    raise Exception("Error creating : %s" % error)
            feed_response = response.json()


class TransactionFeed:
    def transaction(self, transaction):
        pass
