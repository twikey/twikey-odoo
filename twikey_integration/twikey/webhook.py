from hashlib import sha256
from hmac import HMAC, compare_digest


class Webhook(object):
    """Sample usage

    app = Flask(__name__)

    @app.route('/webhook', methods=['GET'])
    def webhook(request):
        payload = unquote(request.query_string)
        received_sign = req.headers.get('X-Signature')
        if not received_sign:
            return False
        if twikey.Webhook.verify_signature(request):
            return 'Successfully', 200
        return 'Forbidden', 403

    if __name__ == '__main__':
        #setup dev server
        app.debug = True
        app.run(host = "0.0.0.0",port=8000)
    """

    @staticmethod
    def verify_signature(payload, sig_header, api_key=None):
        expected_sign = (
            HMAC(key=api_key.encode(), msg=payload.encode(), digestmod=sha256)
            .hexdigest()
            .upper()
        )
        return compare_digest(sig_header, expected_sign)
