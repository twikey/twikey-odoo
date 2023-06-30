import requests


class Transaction(object):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client

    def create(self, data):
        url = self.client.instance_url("/transaction")
        data = data or {}
        try:
            self.client.refreshTokenIfRequired()
            response = requests.post(
                url=url,
                data=data,
                headers=self.client.headers(),
                timeout=15,
            )
            response.raise_for_status()
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Create transaction", response)
            return response.json()["Entries"][0]
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Create transaction", e)

    def feed(self, transaction_feed):
        url = self.client.instance_url("/transaction")
        try:
            self.client.refreshTokenIfRequired()
            response = requests.get(
                url=url,
                headers=self.client.headers(),
                timeout=15,
            )
            response.raise_for_status()
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Feed transaction", response)
            feed_response = response.json()
            while len(feed_response["Entries"]) > 0:
                for msg in feed_response["Entries"]:
                    transaction_feed.transaction(msg)
                response = requests.get(
                    url=url,
                    headers=self.client.headers(),
                    timeout=15,
                )
                if "ApiErrorCode" in response.headers:
                    raise self.client.raise_error("Feed transaction", response)
                feed_response = response.json()
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Feed transaction", e)


class TransactionFeed:
    def transaction(self, transaction):
        pass
