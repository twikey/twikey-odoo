import requests


class Refund(object):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client

    def create_beneficiary_account(self, data):
        """
        Creation a beneficiary account (with accompanied customer)
        :param data all_customer fields + iban and bic
        :return  {
            "name": "Beneficiary Name",
            "iban": "BE68068897250734",
            "bic": "JVBABE22",
            "available": true,
            "address": {
                "street": "Veldstraat 11",
                "city": "Gent",
                "zip": "9000",
                "country": "BE"
            }
        }
        """
        url = self.client.instance_url("/transfers/beneficiaries")
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
                raise self.client.raise_error("Create beneficiary", response)
            return response.json()
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Create paylink", e)

    def create(self, customerNumber, transactionDetails):
        """
        Creation of a refund provided the customer was created and has a customerNumber
        :param customerNumber The customer number (required)
        :param transactionDetails required

        transactionDetails should contain
            * iban	Iban of the beneficiary
            * message	Message to the creditor	Yes	string
            * amount	Amount to be send
            * ref	Reference of the transaction
            * date	Required execution date of the transaction (ReqdExctnDt)
            * place	Optional place

        :return {
                    "id": "11DD32CA20180412220109485",
                    "iban": "BE68068097250734",
                    "bic": "JVBABE22",
                    "amount": 12,
                    "msg": "test",
                    "place": null,
                    "ref": "123",
                    "date": "2018-04-12"
                }
        """
        url = self.client.instance_url("/transfer")
        data = dict(transactionDetails) or {}
        data["customerNumber"] = customerNumber
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

    def feed(self, refund_feed):
        url = self.client.instance_url("/transfer")
        try:
            self.client.refreshTokenIfRequired()
            response = requests.get(
                url=url,
                headers=self.client.headers(),
                timeout=15,
            )
            if "ApiErrorCode" in response.headers:
                raise self.client.raise_error("Feed refunds", response)
            feed_response = response.json()
            while len(feed_response["Entries"]) > 0:
                for msg in feed_response["Entries"]:
                    refund_feed.refund(msg)
                response = requests.get(
                    url=url,
                    headers=self.client.headers(),
                    timeout=15,
                )
                if "ApiErrorCode" in response.headers:
                    raise self.client.raise_error("Feed refunds", response)
                feed_response = response.json()
        except requests.exceptions.RequestException as e:
            raise self.client.raise_error_from_request("Feed refunds", e)


class RefundFeed:
    def refund(self, refund):
        """
        :refund – Json object containing
            * id: Twikey id
            * iban: IBAN of the beneficiary
            * bic: BIC of the beneficiary
            * amount: Amount of the refund
            * msg: Message for the beneficiary
            * place: Optional place
            * ref: Your reference
            * date: Date when the transfer was requested
            * state: Paid
            * bkdate: Date when the transfer was done
        """
        pass
