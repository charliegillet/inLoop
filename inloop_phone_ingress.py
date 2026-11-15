"""Authenticated GPS/health receiver reachable only through Tailscale Serve."""
from datetime import datetime,timezone
import json,math,os,secrets,time
from pathlib import Path
from aiohttp import web
ROOT=Path(__file__).resolve().parent
TOKEN=ROOT/'logs/phone-telemetry.token'
SNAPSHOT=ROOT/'logs/phone-telemetry.json'
def timestamp(value):
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()
    except (ValueError,TypeError):return None

def normalize(payload,previous=None):
    now=time.time();result=dict(previous or {});at=timestamp(payload.get('snapshotAt'))
    if at is None or not now-3600<=at<=now+120:raise ValueError('Snapshot time')
    if at<(timestamp(result.get('snapshotAt')) or 0):return result
    gps_at=timestamp(payload.get('locationRecordedAt'))
    if gps_at is not None and gps_at<=now+120:
        lat,lon,acc=(payload.get(k) for k in ('latitude','longitude','accuracy'))
        if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (lat,lon,acc)):raise ValueError('GPS')
        if not -90<=lat<=90 or not -180<=lon<=180 or not 0<=acc<=10000:raise ValueError('GPS')
        if gps_at>=(timestamp((result.get('location') or {}).get('recordedAt')) or 0):
            result['location']={k:payload[k] for k in ('latitude','longitude','accuracy','altitude','speed','bearing') if k in payload}
            result['location'].update(recordedAt=payload['locationRecordedAt'],device='Phone',source='tailscale')
    health=dict(result.get('health')or{})
    for source,keys,target,age in [('heartRateRecordedAt',('bpm',),'recordedAt',600),('activityRecordedAt',('steps','distanceMeters','caloriesBurned'),'activityRecordedAt',600),('sleepRecordedAt',('sleepMinutes',),'sleepRecordedAt',129600),('restingRecordedAt',('restingBpm',),'restingRecordedAt',129600),('hrvRecordedAt',('hrvMs',),'hrvRecordedAt',129600),('oxygenRecordedAt',('oxygenPercent',),'oxygenRecordedAt',129600)]:
        t=timestamp(payload.get(source))
        if t is None or not now-age<=t<=now+120 or t<(timestamp(health.get(target)) or 0):continue
        values={k:payload[k] for k in keys if isinstance(payload.get(k),(int,float)) and not isinstance(payload[k],bool) and math.isfinite(payload[k]) and 0<=payload[k]<1e9}
        if values:health.update(values);health[target]=payload[source]
    for key,date_key,max_age in [('bpm','recordedAt',600),('steps','activityRecordedAt',600),('distanceMeters','activityRecordedAt',600),('caloriesBurned','activityRecordedAt',600),('sleepMinutes','sleepRecordedAt',129600),('restingBpm','restingRecordedAt',129600),('hrvMs','hrvRecordedAt',129600),('oxygenPercent','oxygenRecordedAt',129600)]:
        measured=timestamp(health.get(date_key))
        if measured is None or now-measured>max_age:health.pop(key,None)
    result['health']=health
    result.update(snapshotAt=payload['snapshotAt'],receivedAt=datetime.now(timezone.utc).isoformat(),direct_received_at=now,transport='tailscale',source='tailscale',device='main-phone.tail287a74.ts.net')
    return result

def application(token):
    async def receive(request):
        if not secrets.compare_digest(request.headers.get('Authorization',''),'Bearer '+token):raise web.HTTPUnauthorized()
        if request.headers.get('Origin'):raise web.HTTPForbidden()
        try:
            payload=await request.json()
            if not isinstance(payload,dict):raise ValueError()
            try:previous=json.loads(SNAPSHOT.read_text())
            except (OSError,ValueError):previous={}
            data=normalize(payload,previous)
        except (ValueError,TypeError):raise web.HTTPBadRequest(text='Invalid telemetry')
        tmp=SNAPSHOT.with_suffix('.tmp');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as out:json.dump(data,out,allow_nan=False)
        os.replace(tmp,SNAPSHOT)
        return web.json_response({'accepted':True,'receivedAt':data['receivedAt']})
    async def health(request):return web.json_response({'service':'inloop-phone-ingress','ok':True})
    app=web.Application(client_max_size=16384);app.router.add_post('/api/telemetry/update',receive);app.router.add_get('/health',health);return app
if __name__=='__main__':web.run_app(application(TOKEN.read_text().strip()),host='127.0.0.1',port=8791,access_log=None,print=None)
