"""NL scenario compiler and interruptible, receipt-driven human actor runner."""
import copy
from pathlib import Path
import threading
import time
import uuid

from .bridge import atomic, read
from .contracts import ROOMS, text
from .director_contract import validate_scenario
from .director_routes import entity, route
from .forge import micro_spec, validate_micro


class Stopped(RuntimeError):
    pass


class Director:
    def __init__(self, live):
        self.live=live; self.root=live.root/'scenarios'; self.root.mkdir(exist_ok=True)
        self.lock=threading.RLock(); self.stop_event=threading.Event()
        self.job={}; self.items={}; self.owner=None; self.identity=None; self.error=''
        self.last_heartbeat=0; self.events=[]; self.started=0; self.folder=None
        for path in sorted(self.root.glob('*.json')):
            if path.name.endswith('.run.json'): continue
            try:
                row=read(path); validate_scenario(row['scenario'])
                if row.get('micro'): validate_micro(row['micro'])
                self.items[row['id']]=row
            except (ValueError,KeyError,TypeError):
                continue

    def busy(self):
        with self.lock: return self.job.get('status') in ('compiling','voicing','starting','running','stopping')

    def state(self):
        with self.lock:
            return {'job':copy.deepcopy(self.job),'items':[self.summary(v) for v in reversed(list(self.items.values()))]}

    @staticmethod
    def summary(row):
        result = {k:copy.deepcopy(row[k]) for k in ('id','prompt','scenario','seed','micro','compiler_ms','scene_ms')}
        if row.get('title'): result['title'] = text(row['title'], 120)
        return result

    def log(self, kind, value):
        self.live.log('scenario-'+kind, value)

    def compile(self,prompt,seed=0,extended=False):
        if type(extended) is not bool: raise ValueError('Invalid scenario profile')
        prompt=text(prompt,3200 if extended else 1600)
        if type(seed) is not int or not 0<=seed<=999999: raise ValueError('Invalid seed')
        with self.lock:
            if self.busy(): raise ValueError('A scenario job is already active')
            self.stop_event.clear(); ident=uuid.uuid4().hex
            self.job={'id':ident,'status':'compiling','prompt':prompt,'steps':[]}
            self.live.pool.submit(self._compile,ident,prompt,seed,extended)
            return copy.deepcopy(self.job)

    def _compile(self,ident,prompt,seed,extended=False):
        try:
            result=self.live.api('scenario_long' if extended else 'scenario',prompt); spec=validate_scenario(result['answer'])
            if self.stop_event.is_set(): raise Stopped('Compilation stopped')
            if not spec['supported']:
                with self.lock: self.job.update(status='unsupported',explanation=spec['explanation'])
                return
            if spec['mode']=='micro':
                selection=self.live.api('forge_jev',{'request':spec['scene_description']})
                micro=micro_spec(selection['answer'],seed); layout='everyday'
            else:
                selection=self.live.api('layout',{'request':spec['scene_description']})
                micro=None; layout=selection['answer']['choice']
            if self.stop_event.is_set(): raise Stopped('Compilation stopped')
            row={'id':ident,'prompt':prompt,'scenario':spec,'seed':seed,'micro':micro,'layout':layout,
                 'compiler_ms':result['latency_ms'],'scene_ms':selection['latency_ms'],
                 'compiler_model':result['model'],'scene_model':selection['model'],'clips':{}}
            with self.lock: self.job.update(status='voicing',scenario=spec)
            for index,step in enumerate(spec['steps']):
                if self.stop_event.is_set(): raise Stopped('Voice preparation stopped')
                if step['skill'] in ('say','walk_say'):
                    clip=self.live.voice(step['line'],step['speaker'])
                    # PCM lives in the existing private voice cache, never in UI proposals.
                    row['clips'][str(index)]={'text':clip['text'],'role':clip['role']}
            if self.stop_event.is_set(): raise Stopped('Compilation stopped')
            atomic(self.root/(ident+'.json'),row)
            with self.lock:
                self.items[ident]=row; self.job.update(status='ready',scenario=spec,
                    compiler_ms=row['compiler_ms'],scene_ms=row['scene_ms'])
            self.log('compiled',self.summary(row))
        except Exception as exc:
            with self.lock: self.job.update(status='stopped' if isinstance(exc,Stopped) else 'failed',error=str(exc)[:400])

    def play(self,ident,view='first',assistant='live'):
        with self.lock:
            if self.busy(): raise ValueError('Stop the current scenario before starting another')
            if ident not in self.items or view not in ('first','third'): raise ValueError('Unknown scenario or view')
            if assistant not in ('live','off'): raise ValueError('Unknown assistant condition')
            self.stop_event.clear(); self.error=''; self.owner=uuid.uuid4().hex
            self.job={'id':ident,'run_id':self.owner,'view':view,'assistant':assistant,'requested_wall_time':time.time(),'status':'starting','steps':[],'events':[],'interventions':[]}
            self.live.pool.submit(self._play,copy.deepcopy(self.items[ident]),view,self.owner,assistant)
            return copy.deepcopy(self.job)

    def cancel(self):
        with self.lock:
            if self.busy(): self.stop_event.set(); self.job['status']='stopping'
            return copy.deepcopy(self.job)

    def check(self):
        if self.stop_event.is_set(): raise Stopped('Stopped by user')
        if self.error: raise RuntimeError(self.error)
        folder,identity,_=self.live.bridge.snapshot()
        raw=read(folder/'state.json')
        if (raw['session_id'],raw['scene_epoch'])!=identity: raise Stopped('Scene changed during actor observation')
        if identity!=self.identity: raise Stopped('Scene changed; old scenario stopped')
        if raw.get('director',{}).get('owner')!=self.owner: raise Stopped('Native actor control ended')
        if self.started and raw['clock_s'] - self.started > 900:
            raise RuntimeError('Scenario exceeded fifteen minutes')
        self.record_intervention(raw)
        return raw

    def record_intervention(self,raw):
        feedback=raw.get('companion_execution',{})
        if not feedback.get('id'): return
        # This is a separate execution result, never inferred from actor steps.
        # Only the assistant's existing own-action receipt fields are retained.
        with self.lock:
            entries=self.job.setdefault('interventions',[])
            row=next((r for r in entries if r['id']==feedback['id']),None)
            if feedback.get('target') not in ('stove','faucet'):
                if not (row and feedback.get('status')=='cancelled' and
                        row.get('status') in ('approaching','reaching','waiting_clearance')): return
            if row is None:
                row={'id':feedback['id'],'target':feedback['target'],'started_clock_s':raw['clock_s'],'transitions':[]}
                entries.append(row)
            if row.get('status')!=feedback.get('status'):
                row['transitions'].append({'status':feedback.get('status'),'clock_s':raw['clock_s']})
            row.update(status=feedback.get('status'),updated_clock_s=raw['clock_s'],
                       finger_error_cm=feedback.get('finger_error_cm'))

    def command(self,control,**fields):
        self.check()
        with self.live.world_lock:
            result=self.live.bridge.command('actor',{'owner':self.owner,'control':control,**fields},self.identity)
        if result['code']!='ACTOR_ACCEPTED': raise RuntimeError('Native actor: '+result['code'])
        self.log('native',{'run_id':self.owner,'control':control,'result':result})
        return result

    def until(self,predicate,seconds,label):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            state=self.check()
            if predicate(state): return state
            time.sleep(.1)
        raise RuntimeError('Timed out: '+label)

    def wait(self,seconds):
        end=self.check()['clock_s']+seconds
        self.until(lambda s:s['clock_s']>=end,seconds*3+10,'wait')

    def monitor(self,done):
        try:
            while not done.wait(.2):
                raw=self.check()
                if time.monotonic()-self.last_heartbeat>1.5:
                    self.command('heartbeat'); self.last_heartbeat=time.monotonic()
                elapsed=raw['clock_s']-self.started
                for event in self.events:
                    if not event.get('result') and elapsed>=event['at_s']:
                        with self.live.world_lock:
                            receipt=self.live.bridge.command('event',{'event_id':event['id']},self.identity)
                        if receipt['code']!='EVENT_STARTED': raise RuntimeError('Event rejected: '+receipt['code'])
                        event['result']=receipt
                        with self.lock: self.job['events']=copy.deepcopy(self.events)
                        self.log('event',{'run_id':self.owner,'event':event})
        except Stopped:
            self.stop_event.set()
        except Exception as exc:
            self.error=str(exc)[:400]

    def motion(self,control,**fields):
        result=self.command(control,**fields)
        state=self.until(lambda s:s['clock_s']>result['clock_s']+.1 and
            s['director']['motion'] in ('arrived','blocked'),180 if control=='path' else 15,control)
        if state['director']['motion']!='arrived': raise RuntimeError('Walking blocked; episode stopped at actual position')
        return {**result,'completion':{'motion':state['director']['motion'],
            'clock_s':state['clock_s'],'player_cm':state['player_cm']}}

    def action(self,action,target=''):
        ident=uuid.uuid4().hex; self.command('action',action=action,target=target,action_id=ident)
        path=self.folder/'responses'/(ident+'.json')
        self.until(lambda s:path.is_file(),20,'human '+action)
        result=read(path)
        if result.get('status')!='succeeded': raise RuntimeError('Human action failed: '+result.get('code','unknown'))
        self.log('action',{'run_id':self.owner,'result':result})
        return result

    def step(self,step,index,clips):
        skill=step['skill']; target=step['target']
        if skill=='walk':
            if self.check()['crouch_alpha']>.5: self.action('crouch')
            return self.motion('path',points_cm=route(self.check(),target))
        if skill=='look':
            return self.motion('look',target=target)
        if skill=='pickup_phone':
            state=self.check(); room=state.get('micro_room')
            # Rotate the BODY first, then lower it if this support is low.
            self.action('look_at','phone'); self.motion('look',target='phone')
            if room and room['family'] in ('lounge','bedroom') and state['crouch_alpha']<.5:
                self.action('crouch')
            for _ in range(3): self.motion('look',target='phone')
            result=self.action('pick_up','phone')
            if self.check()['held_id']!=entity(self.check(),'phone')['id']:
                raise RuntimeError('Phone grip was not retained')
            if self.check()['crouch_alpha']>.5: self.action('crouch')
            return result
        if skill in ('answer_phone','hangup_phone'):
            enabled=skill=='answer_phone'; result=self.command('phone',enabled=enabled)
            self.until(lambda s:s['human_phone_call']==enabled and
                s['director']['motion']=='arrived' and
                (s['phone_blend']>.95 if enabled else s['phone_blend']<.02),8,'phone pose')
            return result
        if skill in ('say','walk_say'):
            movement = None
            if skill == 'walk_say':
                if self.check()['crouch_alpha'] > .5: self.action('crouch')
                movement = self.command('path', points_cm=route(self.check(), target))
            result = self.dialogue(step,index,clips[index])
            if movement:
                arrived = self.until(lambda s:s['clock_s']>movement['clock_s']+.1 and
                    s['director']['motion'] in ('arrived','blocked'),180,'walk and talk arrival')
                if arrived['director']['motion'] != 'arrived':
                    raise RuntimeError('Walking blocked during dialogue')
                result['movement'] = {'started_clock_s':movement['clock_s'],
                    'arrived_clock_s':arrived['clock_s'],'motion':'arrived',
                    'player_cm':arrived['player_cm']}
            if step['seconds']: self.wait(step['seconds'])
            return result
        if skill=='wait': self.wait(step['seconds']); return {'status':'waited'}
        raise ValueError('Unsupported skill')

    def dialogue(self,step,index,clip):
        cause=('authored_phone_exchange:' if step['audience']=='phone' else 'scenario_human:')+self.owner+':'+str(index)
        with self.live.lock: epoch=self.live.epoch
        self.live.speak(clip,epoch,priority=60,cause=cause)
        started=self.until(lambda s:(self.live.last_speech or {}).get('cause')==cause,45,'in-world speech start')
        duration=clip.get('duration_s',len(clip['pcm_b64'])*.75/(2*clip['sample_rate']))
        self.wait(duration+.3)
        interrupted=(self.live.last_speech or {}).get('cause')!=cause
        return {'status':'interrupted' if interrupted else 'spoken','text':step['line'],
                'speech_started_clock_s':started['clock_s'],
                'speech_finished_clock_s':self.check()['clock_s'],
                'motion_at_speech_start':started['director'].get('motion'),
                'position_at_speech_start':started.get('player_cm')}

    def finish_dialogue(self, assistant):
        if assistant != 'live': return
        # Actor listening time can expire while a final reply is synthesizing
        # or playing. Keep the episode/capture open until that existing work
        # and its completed-speech callback settle; never issue a new request.
        def settled(_):
            with self.live.lock:
                if not self.live.enabled or self.live.error: return True
                pending = (getattr(self.live, 'research_job', None) or
                           getattr(self.live, 'research_requested', False))
                callbacks = any(s['kind'] in ('heard', 'research_heard')
                                and s['epoch'] == self.live.epoch for s in self.live.schedule)
                return not (pending or self.live.pending_speech or callbacks or
                            time.monotonic() < self.live.speech_until)
        self.until(settled, 45, 'final dialogue completion')

    def _play(self,row,view,owner,assistant='live'):
        done=threading.Event(); monitor=None; previous_enabled=self.live.enabled
        terminal='completed'; failure=None
        try:
            spec=validate_scenario(row['scenario'])
            # Resolve cached clips BEFORE scene reset, event time or actor ownership.
            clips={i:self.live.voice(step['line'],step['speaker']) for i,step in enumerate(spec['steps']) if step['skill'] in ('say','walk_say')}
            if self.stop_event.is_set(): raise Stopped('Stopped before scene entry')
            ready_until=time.monotonic()+30
            while True:
                if self.stop_event.is_set(): raise Stopped('Stopped while loading the assistant')
                try:
                    folder,_,_=self.live.bridge.snapshot()
                    if 'companion_execution' in read(folder/'state.json'): break
                except (RuntimeError,OSError):
                    pass  # Only retry local startup reads, never a command or model call.
                if time.monotonic()>ready_until: raise RuntimeError('Native companion is still loading')
                time.sleep(.15)
            proposal={'id':row['id'],'human_clip':None,'spec':{
                'supported':True,'explanation':spec['explanation'],'layout':row['layout'],
                'start_room':spec['start_room'],'events':[],'phone_call':False,'phone_delay_s':0,'human_goal':'none'}}
            if row['micro'] is not None: proposal['micro']=row['micro']
            with self.live.world_lock:
                self.live.proposals[row['id']]=proposal; self.live.apply(row['id'])
                with self.live.lock: self.live.enabled=assistant=='live'
                self.folder,self.identity,_=self.live.bridge.snapshot()
                result=self.live.bridge.command('actor',{'control':'begin','owner':owner,'view':view},self.identity)
                if result['code']!='ACTOR_ACCEPTED': raise RuntimeError('Actor could not start: '+result['code'])
            self.started=result['clock_s']; self.events=copy.deepcopy(spec['events']); self.last_heartbeat=0
            monitor=threading.Thread(target=self.monitor,args=(done,),daemon=True); monitor.start()
            with self.lock: self.job.update(status='running',started_clock_s=self.started,scenario=spec)
            self.log('start',{'run_id':owner,'scenario_id':row['id'],'identity':self.identity,'view':view,'assistant':assistant})
            self.wait(1.5)  # Settle the chosen camera before the first acting step.
            for index,step in enumerate(spec['steps']):
                self.check()
                with self.lock: self.job['step']=index
                receipt=self.step(step,index,clips)
                with self.lock: self.job['steps'].append({'index':index,'step':step,'receipt':receipt})
                self.log('step',{'run_id':owner,'index':index,'step':step,'receipt':receipt})
            # A late scheduled event is part of the episode, not silently dropped.
            if self.events:
                last=max(e['at_s'] for e in self.events)
                self.until(lambda s:all(e.get('result') for e in self.events),max(15,last+15),'scheduled events')
            self.finish_dialogue(assistant)
        except Exception as exc:
            terminal='stopped' if isinstance(exc,Stopped) else 'failed'; failure=str(exc)[:400]
        finally:
            done.set()
            if monitor: monitor.join(timeout=8)
            if self.identity:
                try:
                    with self.live.world_lock:
                        self.live.bridge.command('actor',{'owner':owner,'control':'stop'},self.identity)
                except (RuntimeError,OSError,ValueError): pass
            if terminal!='completed':
                try:
                    _,identity,_=self.live.bridge.snapshot()
                    if identity==self.identity: self.live.cancel()
                except (RuntimeError,OSError,ValueError): pass
            try:
                folder,identity,_=self.live.bridge.snapshot()
                if identity==self.identity: self.record_intervention(read(folder/'state.json'))
            except (RuntimeError,OSError,ValueError): pass
            with self.live.lock:
                self.live.enabled=previous_enabled if terminal=='completed' and assistant=='live' else False
            with self.lock:
                self.job['status']=terminal
                self.job['finished_wall_time']=time.time()
                if failure: self.job['error']=failure
            self.log('finish',copy.deepcopy(self.job))
            atomic(self.root/(owner+'.run.json'),self.job)
