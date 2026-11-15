"""Live Gemini motion preview. Sends motion to Google; never posts Mac input."""
import argparse
import asyncio
from collections import deque
import fcntl
import json
import math
import os
from pathlib import Path
import select
import sys
import termios
import time
import tty

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import VEXO_BAND
from motion import LEASE, STATE, atomic_json
from scripts.benchmark_gemini_motion import AXES, decide, key_from_file

STATUS = ROOT/'logs/gemini-live-status.json'
SCREEN_CHECK = ROOT/'logs/gemini-screen-check-current.json'
PROFILE_MAX_AGE = 24*60*60
RAW_CRITERIA = {
    'swipe': 'One short mostly translational stroke: accelerate in one direction, then decelerate to rest. Do not confuse its braking phase with repeated waving.',
    'circle': 'A loop-like motion with direction changing around a sequence of axes rather than simply reversing along one axis.',
    'still': 'Nearly constant acceleration including gravity and little angular velocity.',
    'tilting': 'Smooth change of gravity direction caused by a mostly one-way tilt.',
    'rotating': 'Mostly one-way rotation, particularly turning around gravity with little change in gravity direction.',
    'back_and_forth': 'Clear repeated, approximately regular direction reversals.',
    'shaking': 'Irregular or brisk oscillating motion with substantial acceleration or angular variation.',
    'impact': 'A brief isolated acceleration or angular impulse; physical contact is possible but not established.',
    'unknown': 'Insufficient, mixed, conflicting or otherwise unclassified motion.',
}
RAW_INSTRUCTIONS = ('Classify the physical movement in these raw six-axis IMU samples. '
    'Use the supplied raw samples and units. No old calibration is used. Acceleration includes gravity. '
    'Fresh screen_direction_examples, if present, describe strokes from the wearer\'s recent short check. '
    'Classify the physical movement separately from direction. Do not infer a finger gesture or computer command. '
    'Choose the best supported physical movement, or unknown when ambiguous.')
SCREEN_CRITERIA = {d:f'A stroke toward the {d} edge of the screen, matching this run\'s fresh {d} example.'
                   for d in ('left','right','up','down')}
SCREEN_CRITERIA['unknown']='Stillness, no clear single direction, conflicting evidence, or inadequate fresh examples.'
SCREEN_INSTRUCTIONS=('Identify the dominant screen direction of the latest stroke in samples, '
    'using only the four fresh screen_direction_examples from the recent short check. '
    'Each example was labeled by the wearer. Ignore braking/recentering after a stroke. '
    'No old calibration is available. Choose unknown for stillness or ambiguous direction.')


class DirectionCheck:
    directions=('left','right','up','down')
    def __init__(self):
        self.examples={};self.active=False;self.started=None;self.generation=None;self.message=''

    def save(self, path=SCREEN_CHECK, now=None):
        atomic_json(path,dict(schema=1,band=VEXO_BAND,saved_at=time.time() if now is None else now,
                             source='fresh_screen_direction_check',examples=self.examples))

    def restore(self, path=SCREEN_CHECK, now=None):
        try:
            data=json.loads(path.read_text());now=time.time() if now is None else now
            if (data.get('schema')!=1 or data.get('band')!=VEXO_BAND
                    or data.get('source')!='fresh_screen_direction_check'
                    or not 0<=now-data['saved_at']<PROFILE_MAX_AGE):return False
            examples=data['examples']
            if not isinstance(examples,dict) or list(examples)!=list(self.directions[:len(examples)]):return False
            for example in examples.values():
                samples=example['samples']
                if not 15<=len(samples)<=160:return False
                if any(not isinstance(s[k],(int,float)) or isinstance(s[k],bool) or not math.isfinite(s[k])
                       for s in samples for k in (*AXES,'t','received_at')):return False
            self.examples=examples;self.active=len(examples)<4;self.started=None
            self.message=('Recent direction check restored. A starts live recognition; C starts a new check.'
                          if not self.active else f"{self.directions[len(examples)].upper()}: return to centre, press Space, then swipe and hold.")
            return True
        except (OSError,ValueError,KeyError,TypeError):return False

    def correct(self, direction, trial):
        if direction not in self.directions or len(trial['samples'])<15:return False
        self.examples[direction]={'samples':[dict(s) for s in trial['samples']]}
        return True

    def begin(self):
        self.examples.clear();self.active=True;self.started=None;self.generation=None
        self.message='LEFT: return to a comfortable centre. Press Space, then swipe LEFT once and hold.'

    def start(self, window, now, fresh):
        if not fresh:
            self.message='Wait for fresh motion, then press Space.';return
        self.started=now;self.generation=window.generation
        self.message=f'SWIPE {self.directions[len(self.examples)].upper()} once now, then hold.'

    def feed(self, window, now, fresh):
        if self.started is None:return
        if not fresh or window.generation!=self.generation:
            self.started=None;self.message='Motion interrupted. Return to centre; Space repeats this direction.';return
        if now-self.started<2.2:return
        samples=[s for s in window.samples if self.started-.25<=s['received_at']<=self.started+2.2]
        self.started=None
        if len(samples)<30 or any(b['t']-a['t']>200 for a,b in zip(samples,samples[1:])):
            self.message='Too little continuous motion. Return to centre; Space repeats this direction.';return
        baseline=[sum(s[k] for s in samples[:3])/3 for k in AXES[:3]]
        moving=sum(math.dist([s[k] for k in AXES[:3]],baseline)>.07
                   or math.sqrt(sum(s[k]**2 for k in AXES[3:]))>20 for s in samples)
        if moving<3:
            self.message='No clear stroke captured. Return to centre; Space repeats this direction.';return
        direction=self.directions[len(self.examples)]
        self.examples[direction]={'samples':samples}
        if len(self.examples)==4:
            self.active=False;self.message='Four fresh directions saved for this run. A starts live recognition.'
        else:
            direction=self.directions[len(self.examples)].upper()
            self.message=f'{direction}: return to centre. Press Space, then swipe {direction} once and hold.'


def make_raw_input(trial, screen_examples=None):
    data=dict(sensor=dict(type='six-axis wrist IMU',
        acceleration_unit='g including gravity',gyro_unit='degrees per second',
        time_unit='milliseconds since band startup',frame='band sensor axes; mounting and neutral unspecified'),
        columns=['t_ms',*AXES],
        samples=[[s['t'],*[s[k] for k in AXES]] for s in trial['samples']])
    if screen_examples:
        data['screen_direction_examples']={}
        for direction,example in screen_examples.items():
            samples=example['samples']
            points=[samples[round(i*(len(samples)-1)/11)] for i in range(12)]
            data['screen_direction_examples'][direction]=[[s['t'],*[s[k] for k in AXES]] for s in points]
    return json.dumps(data,separators=(',',':'),allow_nan=False)


class MotionWindow:
    def __init__(self):
        self.generation = None
        self.samples = deque(maxlen=160)
        self.seen = deque(maxlen=320)

    def ingest(self, state, now):
        if state.get('generation') != self.generation:
            self.generation = state.get('generation')
            self.samples.clear();self.seen.clear()
        try:
            fresh = (state.get('band') == VEXO_BAND and bool(self.generation)
                     and state.get('connected') is True and state.get('enabled') is True
                     and 0 <= now-state['published_at'] < .35
                     and 0 <= now-state['sample']['received_at'] < .3)
        except (KeyError,TypeError): fresh = False
        if not fresh:
            self.samples.clear();return False
        for sample in state.get('recent_samples', []):
            try:
                values = [sample[k] for k in (*AXES,'t','received_at')]
                if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in values):
                    continue
                if not 0 <= now-sample['received_at'] < 6: continue
                identity = sample['received_at']
                if identity in self.seen: continue
                if self.samples and (sample['t'] <= self.samples[-1]['t']
                                     or identity <= self.samples[-1]['received_at']): continue
                self.seen.append(identity);self.samples.append(dict(sample))
            except (KeyError,TypeError): continue
        while self.samples and now-self.samples[0]['received_at'] > 6:
            self.samples.popleft()
        return True

    def trial(self, after=None):
        samples = list(self.samples)
        if samples:
            start=samples[-1]['received_at']-1.2 if after is None else after-.2
            samples=[s for s in samples if s['received_at']>=start]
        if len(samples) < 15 or samples[-1]['received_at']-samples[0]['received_at'] < .8:
            return None
        if after is not None and samples[-1]['received_at']-after<.8:return None
        # Reject windows with missing telemetry, rather than compressing a hole.
        if any(b['received_at']-a['received_at'] > .2 or b['t']-a['t'] > 200
               for a,b in zip(samples,samples[1:])): return None
        return dict(samples=samples)


def result_current(generation, request_epoch, current_generation, current_epoch, now, window_end, fresh):
    return (fresh and generation == current_generation and request_epoch == current_epoch
            and 0 <= now-window_end < 2.)


def read_key(fd):
    if not select.select([fd],[],[],0)[0]:return None
    key=os.read(fd,1)
    if key==b'\x1b':
        tail=b''
        while len(tail)<16 and select.select([fd],[],[],.02)[0]:
            char=os.read(fd,1);tail+=char
            if (tail[:1] not in (b'[',b'O') or len(tail)>=2 and 64<=char[0]<=126):break
        return None if tail else '\x1b'
    return key.decode(errors='ignore').lower()


async def run(args):
    key=key_from_file(args.env_file)
    window=MotionWindow();check=DirectionCheck();rows=[];pending=None;request_epoch=0;last_window_end=None
    automatic=args.auto;message='Hold a pose for a second, then press Space to ask Gemini.'
    if args.screen_check:
        if not check.restore():check.begin()
        automatic=False;message=check.message
    last_request=-math.inf;last_lease=last_paint=0
    result=None;last_observation=None;requests=0;started=time.monotonic();fresh=False
    interactive=sys.stdin.isatty() and sys.stdout.isatty()
    terminal=termios.tcgetattr(sys.stdin) if interactive else None
    report=ROOT/'logs'/time.strftime(f'gemini-live-%Y%m%dT%H%M%SZ-{os.getpid()}.json',time.gmtime())
    try:
        if interactive:tty.setcbreak(sys.stdin.fileno());sys.stdout.write('\x1b[?25l')
        while time.monotonic()-started < args.seconds:
            now,tick=time.time(),time.monotonic()
            if tick-last_lease > 1:
                LEASE.write_text('control');os.chmod(LEASE,0o600);last_lease=tick
            try:state=json.loads(STATE.read_text())
            except (OSError,ValueError):state={}
            old_generation=window.generation
            fresh=window.ingest(state,now)
            if window.generation != old_generation:
                result=None;last_observation=None;last_window_end=None
                if check.examples:
                    message='Band reconnected. Completed strokes from this run are retained; C restarts if the fit changed.'
            pressed=None
            if interactive:pressed=read_key(sys.stdin.fileno())
            if pressed=='q':break
            if pressed=='\x1b':
                automatic=False;request_epoch+=1;result=None;check.started=None
                message='Paused. A resumes recognition; Space captures the indicated stroke.'
            if pressed=='c':
                check.begin();automatic=False;request_epoch+=1;result=None;last_window_end=None
                check.save()
            if pressed in ('l','r','u','d'):
                if result and last_observation and fresh and now-result['completed_at']<8:
                    direction={'l':'left','r':'right','u':'up','d':'down'}[pressed]
                    if check.correct(direction,last_observation):
                        check.save();request_epoch+=1
                        message=f'Your correction: {direction.upper()}. Gemini will use this example on the next request.'
                else:message='Wait for a fresh prediction, then L/R/U/D corrects that window.'
            if check.active:
                previous_count=len(check.examples)
                if pressed==' ' and check.started is None:check.start(window,now,fresh)
                check.feed(window,now,fresh);message=check.message
                if len(check.examples)!=previous_count:check.save()
            if pressed == 'a':
                if args.screen_check and len(check.examples)!=4:
                    automatic=False;check.active=True
                    message=check.message or 'Complete the four fresh strokes first.'
                else:
                    automatic=not automatic if not check.active else False
                    message='Automatic mode ON; try single swipes, circles and turns.' if automatic else 'Automatic mode paused. Space tests one window.'
                request_epoch+=1;result=None
            trial=window.trial(after=last_window_end if automatic else None) if fresh else None
            if pending is not None and pending.done():
                context,task=pending.context,pending
                pending=None
                try:
                    answer=task.result()
                except RuntimeError as error:
                    message=str(error);automatic=False
                    rows.append(dict(error=message));break
                accepted=result_current(context['generation'],context['epoch'],window.generation,
                    request_epoch,now,context['window_end'],fresh)
                row=dict(**answer,usable=accepted,window_ms=context['window_ms'],
                         sample_count=context['sample_count'],completed_at=now)
                rows.append(row)
                atomic_json(report,dict(model='gemini-decision-1',advisory_only=True,old_calibration_used=False,rows=rows))
                if accepted:
                    result=row
                    last_observation=context['trial']
                    message='Prediction for the last motion window. Hold another pose; Space asks again.'
                else:
                    result=None;message='Result expired or the source changed; wait for fresh motion and try again.'
                if not interactive:print(json.dumps(row),flush=True)
                if requests>=args.max_requests:
                    automatic=False;message='Request limit reached. Q closes this preview.'
                    if not interactive:break
            direction_ready=not args.screen_check or len(check.examples)==4
            want = not check.active and direction_ready and (pressed == ' ' or (automatic and trial is not None and tick-last_request >= .8))
            if want and pending is None and requests<args.max_requests:
                if trial is None:
                    message='Waiting for at least 0.8 seconds of uninterrupted, fresh motion.'
                else:
                    text=make_raw_input(trial,check.examples if len(check.examples)==4 else None)
                    extra=dict(screen_direction=dict(type='choice',criteria=SCREEN_CRITERIA,
                        instructions=SCREEN_INSTRUCTIONS)) if len(check.examples)==4 else None
                    pending=asyncio.create_task(asyncio.to_thread(decide,key,text,
                        criteria=RAW_CRITERIA,instructions=RAW_INSTRUCTIONS,extra_questions=extra))
                    pending.context=dict(generation=window.generation,epoch=request_epoch,
                        window_end=trial['samples'][-1]['received_at'],
                        window_ms=round(trial['samples'][-1]['t']-trial['samples'][0]['t']),
                        sample_count=len(trial['samples']),trial=trial)
                    requests+=1;last_request=tick
                    last_window_end=trial['samples'][-1]['received_at']
                    message='Gemini is classifying the last motion window…'
            if not fresh:result=None;last_observation=None
            if requests>=args.max_requests:
                automatic=False
                if pressed in ('a',' '):message='Request limit reached. Q then rerun the command; the fresh check will be restored.'
            if tick-last_paint > .1:
                status=dict(advisory_only=True,old_calibration_used=False,fresh_direction_examples=len(check.examples),
                    direction_check_active=check.active,model='gemini-decision-1',fresh=fresh,
                    automatic=automatic,pending=pending is not None,requests=requests,
                    max_requests=args.max_requests,result=result,message=message,
                    updated_at=now,pid=os.getpid())
                atomic_json(STATUS,status)
                if interactive:
                    label=result['choice'].upper() if result else '—'
                    direction=result.get('screen_direction') if result else None
                    if direction:label+=f" · {direction['choice'].upper()} ({direction['confidence']:.0%} direction confidence)"
                    detail=(f"Confidence {result['confidence']:.0%} | API {result['elapsed_ms']:.0f} ms | "
                            f"{result['sample_count']} samples / {result['window_ms']} ms | "
                            f"Result age {now-result['completed_at']:.1f}s" if result else '')
                    sample=window.samples[-1] if window.samples and fresh else None
                    accel=('Accelerometer g: '+ '  '.join(f'{k} {sample[k]:+.3f}' for k in AXES[:3]) if sample else 'Accelerometer: waiting')
                    gyro=('Gyro deg/s:      '+ '  '.join(f'{k} {sample[k]:+.1f}' for k in AXES[3:]) if sample else 'Gyro: waiting')
                    display='\n'.join([
                        'VEXO 43 → GEMINI DECISION 1 · LIVE PREVIEW',
                        'Live wrist motion goes to Google. This preview does not control the Mac.',
                        '', 'C: new check   SPACE: capture / classify   A: auto   Escape: pause   Q: quit',
                        'L/R/U/D: correct the last prediction as left/right/up/down (updates fresh examples).',
                        'Swipes, circles, tilts, rotations, shaking and stillness. Screen directions need C first.',
                        f'Old calibration unused. Recent screen-check examples: {len(check.examples)}/4 (valid 24h; C resets).',
                        '', f'LAST WINDOW: {label}', detail, '', message,
                        '',accel,gyro,
                        f"Motion: {'fresh' if fresh else 'waiting/stale'} | Auto: {automatic} | "
                        f"Requests {requests}/{args.max_requests}",
                        f'Time remaining: {max(0,args.seconds-(tick-started)):.0f} sec',
                        '', 'Confidence is provisional. Unknown/low confidence is useful feedback.',
                        'Captions continue separately. No second Bluetooth client is opened.',
                    ])
                    sys.stdout.write('\x1b[H\x1b[2J'+display+'\n');sys.stdout.flush()
                last_paint=tick
            await asyncio.sleep(.03)
    finally:
        LEASE.unlink(missing_ok=True)
        try:
            atomic_json(report,dict(model='gemini-decision-1',advisory_only=True,old_calibration_used=False,rows=rows,requests=requests))
            atomic_json(STATUS,dict(stopped=True,advisory_only=True,old_calibration_used=False,requests=requests,report=str(report),
                                    updated_at=time.time(),pid=os.getpid()))
        finally:
            if terminal:
                termios.tcsetattr(sys.stdin,termios.TCSADRAIN,terminal);sys.stdout.write('\x1b[?25h\n')
        # A sent request may still complete; its result cannot reach any Mac input code.
        if pending is not None:
            try:await pending
            except Exception:pass
        print('Live preview stopped. Report:',report,flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,required=True)
    parser.add_argument('--seconds',type=int,default=120)
    parser.add_argument('--max-requests',type=int,default=24)
    parser.add_argument('--auto',action='store_true',help='Start automatic bounded classification')
    parser.add_argument('--screen-check',action='store_true',help='Start a fresh four-stroke screen-direction check')
    args=parser.parse_args()
    if not 1<=args.seconds<=300 or not 1<=args.max_requests<=24:
        parser.error('Use 1–300 seconds and 1–24 requests')
    if not (sys.stdin.isatty() and sys.stdout.isatty()) and not args.auto:
        parser.error('Use an interactive terminal, or explicitly select --auto for a bounded check')
    if args.screen_check and not (sys.stdin.isatty() and sys.stdout.isatty()):
        parser.error('--screen-check needs an interactive terminal')
    with (ROOT/'logs/vexo-motion-view.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('Close the existing motion/control viewer first; captions can stay open.');return 1
        try:asyncio.run(run(args))
        except KeyboardInterrupt:pass
    return 0


if __name__=='__main__':raise SystemExit(main())
