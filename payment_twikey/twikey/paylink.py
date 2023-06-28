import requests


class Paylink(object):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client

    def create(self, data):
        url = self.client.instance_url("/payment/link")
        data = data or {}
        try:
            self.client.refreshTokenIfRequired()
            response = requests.post(
                url=url,
                data=data,
                headers=self.client.headers(),
                timeout=15,
            )
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Create paylink", response)
            return response.json()
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Create paylink", e)

    def feed(self, paylink_feed):
        url = self.client.instance_url("/payment/link/feed")
        try:
            self.client.refreshTokenIfRequired()
            response = requests.get(
                url=url,
                headers=self.client.headers(),
                timeout=15,
            )
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Feed paylink", response)
            feed_response = response.json()
            while len(feed_response["Links"]) > 0:
                for msg in feed_response["Links"]:
                    paylink_feed.paylink(msg)
                response = requests.get(
                    url=url,
                    headers=self.client.headers(),
                    timeout=15,
                )
                if "ApiErrorCode" in response.headers:
                    raise self.client.raise_error("Feed paylink", response)
                feed_response = response.json()
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Feed paylink", e)


class PaylinkFeed:
    def paylink(self, paylink):
        pass
