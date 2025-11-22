import asyncio
from flask import Flask, request, jsonify
from zabbix_utils import AsyncZabbixAPI
import asyncio

app = Flask(__name__)

ZABBIX_URL = "https://monitor.cfu.ac.ir"
ZABBIX_USER = "Admin"
ZABBIX_PASS = "M@cfu@2022"

async def fetch_metrics(hostname: str):
    api = AsyncZabbixAPI(url=ZABBIX_URL)
    await api.login(user=ZABBIX_USER, password=ZABBIX_PASS)

    hosts = await api.host.get(output=['hostid','name'])
    host = next((h for h in hosts if h['name'] == hostname), None)
    if not host:
        await api.logout()
        return {"error": f"Host '{hostname}' not found"}

    hostid = host['hostid']

    async def get_item(key, label):
        items = await api.item.get(
            hostids=hostid,
            search={'key_': key},
            output=['lastvalue']
        )
        return {label: items[0]['lastvalue'] if items else None}

    data = {"host": hostname}

    # CPU utilization in %
    cpu_item = await get_item("system.cpu.util[,user]", "cpu")
    cpu_value = cpu_item.get("cpu")
    if cpu_value is not None:
        data["cpu"] = f"{float(cpu_value):.2f}%"  # 2 decimal percentage
    else:
        data["cpu"] = "N/A"

    # Memory available in %
    mem_item = await get_item("vm.memory.utilization", "memory_used")
    mem_used = mem_item.get("memory_used")
    if mem_used is not None:
        mem_available = 100 - float(mem_used)
        data["memory_available"] = f"{mem_available:.2f}%"  # 2 decimals
    else:
        data["memory_available"] = "N/A"

    # System uptime
    uptime_item = await get_item("system.uptime", "uptime_seconds")
    uptime_seconds = uptime_item.get("uptime_seconds")
    if uptime_seconds is not None:
        uptime_seconds = int(uptime_seconds)
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        data["system_uptime"] = f"{days}d {hours}h {minutes}m {seconds}s"
    else:
        data["system_uptime"] = "N/A"

    await api.logout()
    return data



@app.route("/metrics")
def metrics():
    hostname = request.args.get("host")
    if not hostname:
        return jsonify({"error": "Please provide ?host=hostname"}), 400

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        data = loop.run_until_complete(fetch_metrics(hostname))
    finally:
        loop.close()

    return jsonify(data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6000, debug=True)
