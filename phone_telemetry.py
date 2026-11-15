"""Read the phone's private sensor snapshot over an authorized ADB connection."""
import asyncio
from datetime import datetime, timezone
import ipaddress
import json
import math
import os
import re
import shutil
import socket
import time

PACKAGE='dev.alhinai.fliptracker'
DEVICE=os.environ.get('INLOOP_ADB_DEVICE','R3GL90J20YX')


async def command(*arguments,timeout=5):
    process=await asyncio.create_subprocess_exec(*arguments,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
    try:output,_=await asyncio.wait_for(process.communicate(),timeout)
    except (TimeoutError,asyncio.CancelledError):
        try:process.kill()
        except ProcessLookupError:pass
        await process.wait();raise
    if process.returncode:raise OSError('Phone connection unavailable')
    return output.decode('utf-8')


def normalize_snapshot(data,now=None):
    now=time.time() if now is None else now
    try:recorded=datetime.fromisoformat(data['snapshotAt'].replace('Z','+00:00')).timestamp()
    except (ValueError,TypeError,KeyError):raise ValueError('Missing phone snapshot time')
    if not 0<=now-recorded<=45:raise ValueError('Phone snapshot is stale')
    health={}
    numeric=('bpm','steps','distanceMeters','caloriesBurned','sleepMinutes','restingBpm','hrvMs','oxygenPercent')
    dates=('heartRateRecordedAt','activityRecordedAt','sleepRecordedAt','restingRecordedAt','hrvRecordedAt','oxygenRecordedAt')
    for key in numeric:
        value=data.get(key)
        if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0:health[key]=value
    for key in dates:
        value=data.get(key)
        if isinstance(value,str):health[key]=value
    if 'heartRateRecordedAt' in health:health['recordedAt']=health['heartRateRecordedAt']
    health.update(activitySource='Phone · Health Connect',recoverySource='Phone · Health Connect')
    if isinstance(data.get('source'),str):health['source']=data['source'][:80]
    location=None
    lat,lon,accuracy=data.get('latitude'),data.get('longitude'),data.get('accuracy')
    if all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (lat,lon,accuracy)) and -90<=lat<=90 and -180<=lon<=180 and 0<=accuracy<=10000:
        location=dict(latitude=lat,longitude=lon,accuracy=accuracy,recordedAt=data.get('locationRecordedAt'),device='Phone',source='adb')
    return dict(location=location,health=health,receivedAt=datetime.fromtimestamp(now,timezone.utc).isoformat(),source='adb'),recorded


async def read_phone():
    adb=shutil.which('adb')
    if not adb:raise OSError('ADB unavailable')
    raw=await command(adb,'-s',DEVICE,'exec-out','run-as',PACKAGE,'cat','files/inloop-telemetry.json')
    metadata=await asyncio.gather(
        command(adb,'-s',DEVICE,'shell','ip','-o','-4','addr','show','wlan0'),
        command(adb,'-s',DEVICE,'shell','getprop','ro.product.model'),return_exceptions=True)
    ip,model=[value if isinstance(value,str) else '' for value in metadata]
    payload=json.loads(raw);telemetry,recorded=normalize_snapshot(payload)
    match=re.search(r'\binet\s+(\d+\.\d+\.\d+\.\d+)/',ip)
    phone=dict(connected=True,name=model.strip()[:80] or 'Phone',ip=match.group(1) if match else None,
        synced_at=recorded,source='adb',health_status='ready' if payload.get('healthPermissionsGranted') else 'permission_needed')
    return phone,telemetry


async def network_snapshot():
    local_ip=None
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as handle:
            handle.connect(('1.1.1.1',80));local_ip=handle.getsockname()[0]
    except OSError:pass
    tailscale_ip=None;executable=shutil.which('tailscale')
    if executable:
        try:
            value=(await command(executable,'ip','-4',timeout=2)).strip()
            tailscale_ip=str(ipaddress.IPv4Address(value))
        except (OSError,ValueError,TimeoutError):pass
    return dict(local_ip=local_ip,tailscale_ip=tailscale_ip)
