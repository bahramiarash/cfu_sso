from flask import Flask, render_template, request
from database import init_db, insert_message, insert_sms_record, update_sms_result
from sms_sender import login_and_get_token, send_sms
import time
from datetime import datetime
from persiantools.jdatetime import JalaliDate
import threading
from bulk_sender import bulk_send_worker
import re

app = Flask(__name__)
init_db()

@app.route('/', methods=['GET', 'POST'])
def index():
    status = None

    if request.method == 'POST':
        mobiles_raw = request.form['mobiles']
        message = request.form['message']

        # Normalize and extract valid mobile numbers
        mobiles = re.split(r'[,\n\r]+', mobiles_raw)
        mobiles = [m.strip() for m in mobiles if m.strip() and m.strip().isdigit()]

        if len(mobiles) == 0:
            status = "No valid mobile numbers found."
        else:
            # Start background thread
            thread = threading.Thread(target=bulk_send_worker, args=(mobiles, message))
            thread.start()
            status = f"Started sending SMS to {len(mobiles)} numbers in background."

    return render_template('index.html', status=status)


if __name__ == '__main__':
    app.run(debug=True)
