import base64
import datetime
import logging
import requests
import pytz

from decouple import config

logger = logging.getLogger(__name__)


class MpesaClient:
    def __init__(self):
        self.consumer_key = config("MPESA_CONSUMER_KEY")
        self.consumer_secret = config("MPESA_CONSUMER_SECRET")
        self.shortcode = config("MPESA_SHORTCODE", default="174379")
        self.passkey = config("MPESA_PASSKEY")
        self.callback_url = config("MPESA_CALLBACK_URL")

        # Sandbox:
        # https://sandbox.safaricom.co.ke
        #
        # Production:
        # https://api.safaricom.co.ke
        self.api_url = config(
            "MPESA_API_URL",
            default="https://sandbox.safaricom.co.ke"
        )

    def format_phone(self, phone):
        """
        Convert:
        0712345678 -> 254712345678
        +254712345678 -> 254712345678
        254712345678 -> 254712345678
        """
        phone = str(phone).strip()

        if phone.startswith("0"):
            phone = "254" + phone[1:]
        elif phone.startswith("+254"):
            phone = phone[1:]

        return phone

    def get_access_token(self):
        """
        Generate Daraja access token.
        """
        url = f"{self.api_url}/oauth/v1/generate?grant_type=client_credentials"

        auth_string = (
            f"{self.consumer_key}:{self.consumer_secret}"
        )

        encoded_auth = base64.b64encode(
            auth_string.encode()
        ).decode()

        headers = {
            "Authorization": f"Basic {encoded_auth}"
        }

        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=30
            )

            response.raise_for_status()

            data = response.json()

            token = data.get("access_token")

            if not token:
                logger.error("No access token returned.")
                return None

            logger.info("Mpesa access token generated successfully.")
            return token

        except requests.exceptions.RequestException as e:
            logger.error(f"Access token error: {e}")

            if hasattr(e, "response") and e.response is not None:
                logger.error(e.response.text)

            return None

    def stk_push(
        self,
        phone_number,
        amount,
        account_reference,
        transaction_desc
    ):
        """
        Initiate STK Push request.
        """

        token = self.get_access_token()

        if not token:
            return {
                "ResponseCode": "1",
                "errorMessage": "Failed to obtain access token"
            }

        try:
            amount = int(amount)

            if amount < 1:
                return {
                    "ResponseCode": "1",
                    "errorMessage": "Amount must be greater than zero"
                }

        except (ValueError, TypeError):
            return {
                "ResponseCode": "1",
                "errorMessage": "Invalid amount"
            }

        phone_number = self.format_phone(phone_number)

        nairobi_tz = pytz.timezone("Africa/Nairobi")
        timestamp = datetime.datetime.now(
            nairobi_tz
        ).strftime("%Y%m%d%H%M%S")

        password_string = (
            f"{self.shortcode}{self.passkey}{timestamp}"
        )

        password = base64.b64encode(
            password_string.encode()
        ).decode()

        url = f"{self.api_url}/mpesa/stkpush/v1/processrequest"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone_number,
            "PartyB": self.shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": self.callback_url,
            "AccountReference": str(account_reference),
            "TransactionDesc": str(transaction_desc)[:50]
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=30
            )

            logger.info(
                f"STK Push Response Status: {response.status_code}"
            )

            logger.info(
                f"STK Push Response Body: {response.text}"
            )

            response.raise_for_status()

            result = response.json()

            if result.get("ResponseCode") != "0":
                logger.error(
                    f"STK Push rejected: {result}"
                )

            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"STK Push request failed: {e}")

            if hasattr(e, "response") and e.response is not None:
                logger.error(e.response.text)

            return {
                "ResponseCode": "1",
                "errorMessage": str(e)
            }