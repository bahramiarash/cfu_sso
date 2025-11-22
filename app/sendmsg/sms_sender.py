import requests

API_BASE_URL = "https://api.cfu.ac.ir"
LOGIN_URL = f"{API_BASE_URL}/Login"
SEND_SMS_URL = f"{API_BASE_URL}/API/Admin/SendSMSBody"

USERNAME = "khodarahmi"
PASSWORD = "9909177"

def login_and_get_token():
    payload = {
        "userName": USERNAME,
        "password": PASSWORD
    }
    try:
        response = requests.post(LOGIN_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        token = data['data']['token']
        return token
    except Exception as e:
        print(f"[ERROR] Login failed: {e}")
        return None

def send_sms(token, mobile, message):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "mobile": mobile,
        "message": message
    }
    try:
        response = requests.post(SEND_SMS_URL, json=payload, headers=headers)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"[ERROR] Sending SMS failed: {e}")
        return False
