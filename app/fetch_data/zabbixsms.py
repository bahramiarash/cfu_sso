#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import time
import json
import logging
import sys
import asyncio
import time
from zabbix_utils import AsyncZabbixAPI
from typing import Dict, Any, Optional, List

# ---------- CONFIG ----------
ZABBIX_URL = "https://monitor.cfu.ac.ir"
ZABBIX_USER = "Admin"
ZABBIX_PASS = "M@cfu@2022"

API_BASE_URL = "https://api.cfu.ac.ir"
SWAGGER_LOGIN_URL = f"{API_BASE_URL}/Login"
SWAGGER_SMS_URL = f"{API_BASE_URL}/API/Admin/SendSMSBody"


SMS_USER = "khodarahmi"
SMS_PASS = "9909177"
# ADMINS = ["09123880167"]
ADMINS = ["09123880167", "09121451151"]

blacklist = ["shamim_search_1", "shamim_search_2"]

# Thresholds
CPU_THRESHOLD = 90        # percent
RAM_THRESHOLD = 90        # percent
DISK_THRESHOLD = 10       # GB free


# === SMS FUNCTIONS ===
def get_sms_token():
    """Login to Swagger and get bearer token"""
    resp = requests.post(SWAGGER_LOGIN_URL, json={"username": SMS_USER, "password": SMS_PASS})
    resp.raise_for_status()
    data = resp.json()
    token = None
    if "data" in data and "token" in data["data"]:
        token = data["data"]["token"]

    if not token:
        raise ValueError("❌ No token found in Swagger login response")

    return token



def send_sms(token, message, receivers):
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




# === ZABBIX CHECK ===
async def check_hosts():
    sms_token = get_sms_token()

    async with AsyncZabbixAPI(
        url=ZABBIX_URL,
        user=ZABBIX_USER,
        password=ZABBIX_PASS,
    ) as api:

        hosts = await api.host.get(
            output=["hostid", "host", "status"],
            selectInterfaces=["ip"]
        )

        for host in hosts:
            if not host["host"] in blacklist:
                print(host)
                hostid = host["hostid"]
                hostname = host["host"]
                status = host["status"]  # 0=enabled, 1=disabled

                issues = []

                if status != "0":
                    issues.append("❌ Host is disabled / unavailable")

                # CPU usage
                cpu_items = await api.item.get(hostids=hostid, filter={"key_": "system.cpu.util[,user]"})
                if cpu_items:
                    cpu = float(cpu_items[0]["lastvalue"])
                    if cpu > CPU_THRESHOLD:
                        issues.append(f"⚠️ High CPU usage: {cpu:.2f}%")

                # RAM usage
                mem_items = await api.item.get(hostids=hostid, filter={"key_": "vm.memory.utilization"})
                if mem_items:
                    mem_used = float(mem_items[0]["lastvalue"])
                    if mem_used > RAM_THRESHOLD:
                        issues.append(f"⚠️ High RAM usage: {mem_used:.2f}%")

                # Disk free
                disk_items = await api.item.get(hostids=hostid, filter={"key_": "vfs.fs.size[/,free]"})
                if disk_items:
                    disk_free = float(disk_items[0]["lastvalue"]) / (1024 ** 3)
                    if disk_free < DISK_THRESHOLD:
                        issues.append(f"⚠️ Low Disk Space: {disk_free:.2f} GB free")

                # Send SMS if needed
                if issues:
                    message = f"🚨 Alert on host {hostname}:\n" + "\n".join(issues)
                    send_sms(sms_token, message, ADMINS)
            else:
                print(host["host"]," has problem, but is in BlackList")



# === MAIN ===
if __name__ == "__main__":
    while True:
        try:
            asyncio.run(check_hosts())
        except Exception as e:
            print("❌ Error in check_hosts:", e)
        # wait 10 minutes
        time.sleep(600)