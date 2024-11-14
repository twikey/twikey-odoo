import requests


class Transaction(object):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client

    def create(self, data):
        """
        See https://www.twikey.com/api/#new-transaction
        :param data: parameters of the rest call as a struct
        :return: struct containing return value of the rest call
        """
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
        """
        See https://www.twikey.com/api/#transaction-feed
        :param transaction_feed: instance of TransactionFeed to handle transaction updates
        """
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

    def batch_send(self, ct, colltndt=False):
        """
        See https://www.twikey.com/api/#execute-collection
        :param ct	Contract template for which to do the collection	Yes	number
        :param colltndt	Collection date (default=earliest batch) [*1]	No	string
        :return: struct containing identifier of the batch
        """
        url = self.client.instance_url("/collect")
        data = {"ct": ct}
        if colltndt:
            data["colltndt"] = colltndt
        try:
            self.client.refreshTokenIfRequired()
            response = requests.post(
                url=url,
                data=data,
                headers=self.client.headers(),
                timeout=60,  # might be large batches
            )
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Send batch", response)
            return response.json()
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Send batch", e)

    def batch_import(self, pain008_xml):
        """
        See https://www.twikey.com/api/#import-collection
        :param pain008_xml content of the pain008 file
        """
        url = self.client.instance_url("/collect/import")
        try:
            self.client.refreshTokenIfRequired()
            response = requests.post(
                url=url,
                data=pain008_xml,
                headers=self.client.headers(),
                timeout=60,  # might be large batches
            )
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Import batch", response)
            return response.json()
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Import batch", e)

    def reporting_import(self, reporting_content):
        """
        :param reporting_content content of the coda/camt/mt940 file
        """
        url = self.client.instance_url("/reporting")
        try:
            self.client.refreshTokenIfRequired()
            response = requests.post(
                url=url,
                data=reporting_content,
                headers=self.client.headers(),
                timeout=60,  # might be large batches
            )
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Import reporting", response)
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Import reporting", e)


class TransactionFeed:
    def transaction(self, transaction):
        pass
