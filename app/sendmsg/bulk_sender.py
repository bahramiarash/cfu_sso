import threading
import time
from persiantools.jdatetime import JalaliDate
from database import insert_message, insert_sms_record, update_sms_result
from sms_sender import login_and_get_token, send_sms

def bulk_send_worker(mobiles, message):
    token = login_and_get_token()
    if not token:
        print("[ERROR] Could not get token. Aborting bulk send.")
        return

    shamsi_date = str(JalaliDate.today())
    message_id = insert_message(message, shamsi_date)

    for i, mobile in enumerate(mobiles):
        mobile = mobile.strip()
        if not mobile:
            continue

        created_at = int(time.time())
        sms_id = insert_sms_record(mobile, message_id, created_at)

        try:
            result = send_sms(token, mobile, message)
            send_result = 'success' if result else 'failed'
        except Exception as e:
            print(f"[ERROR] Sending to {mobile}: {e}")
            send_result = 'failed'

        update_sms_result(sms_id, send_result, int(time.time()))
        print(f"[{i+1}/{len(mobiles)}] {mobile} -> {send_result}")
        time.sleep(0.2)  # avoid flooding the API (5 per second is safe)
