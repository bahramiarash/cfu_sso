import requests
import os

# ---------- CONFIG ----------
API_BASE_URL = "https://api.cfu.ac.ir"
SWAGGER_LOGIN_URL = f"{API_BASE_URL}/Login"
SWAGGER_SMS_URL = f"{API_BASE_URL}/API/Admin/SendSMSBody"

# SMS credentials must be set as environment variables for security
SMS_USER = os.getenv("SMS_USER")
SMS_PASS = os.getenv("SMS_PASS")

if not SMS_USER or not SMS_PASS:
    raise ValueError(
        "SMS_USER and SMS_PASS environment variables are not set. "
        "Please set them in your .env file or environment variables."
    )

# Admin phone numbers for SMS alerts (comma-separated in environment variable)
ADMINS_ENV = os.getenv("SMS_ADMIN_NUMBERS", "09123880167,09121451151")
ADMINS = [num.strip() for num in ADMINS_ENV.split(",") if num.strip()]


# === SMS FUNCTIONS ===
def get_sms_token():
    """Login to Swagger and get bearer token"""
    resp = requests.post(
        SWAGGER_LOGIN_URL,
        json={"username": SMS_USER, "password": SMS_PASS}
    )
    resp.raise_for_status()
    data = resp.json()

    token = data.get("data", {}).get("token")
    if not token:
        raise ValueError("❌ No token found in Swagger login response")

    return token


def send_sms(token: str, message: str, receivers: list[str]):
    """Send SMS via Swagger API"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    for mobile in receivers:
        payload = {"mobile": mobile, "message": message}
        resp = requests.post(SWAGGER_SMS_URL, headers=headers, json=payload)

        if resp.status_code == 200:
            print(f"✅ SMS sent to {mobile}: {message}")
        else:
            print(f"❌ Failed to send SMS to {mobile}: {resp.text}")