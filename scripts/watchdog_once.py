#!/usr/bin/env python3
"""GitHub scheduled alternative: skip a recorded daily success, otherwise replay."""
import datetime, json, os, subprocess, urllib.request
base=os.environ['BASE_URL'];token=os.environ['DEMO_CONTROL_TOKEN']
request=urllib.request.Request(base+'/api/demo/heartbeat',headers={'Authorization':'Bearer '+token})
try:
    with urllib.request.urlopen(request,timeout=10) as response: heartbeat=json.load(response)
except Exception: heartbeat={}
if heartbeat.get('date')==datetime.datetime.now(datetime.timezone.utc).date().isoformat() and heartbeat.get('result')=='passed':
    print('Daily heartbeat already passed; no browser replay needed')
else:
    subprocess.run(['node','scripts/journey.mjs'],check=True,timeout=120)
