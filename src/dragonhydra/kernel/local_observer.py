"""Bounded local observations driven by the EXISTING worker, never status GETs."""
from datetime import datetime,timedelta
import json,os,time
from pathlib import Path
from threading import Lock
from uuid import uuid4

from .contracts import Observation,iso


class LocalObserver:
    def __init__(self,registry,supporting,state,identity,*,interval,clock,monotonic=time.monotonic):
        self.registry,self.supporting,self.state=registry,supporting,Path(state)
        self.identity,self.interval,self.clock,self.monotonic=identity,interval,clock,monotonic
        self.lock=Lock();self.next_due=0.0;self.running=False;self.cycle_id=None
        self.completed=0;self.failed=0;self.last_cache_error=None;self.last_observed=None
        self.path=self.state/'module-observations.json'
    def _ordinary(self):
        for path in (self.path,*self.path.parents):
            if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
                raise OSError('LINKED_OBSERVATION_PATH')
    def _load_history(self):
        try:
            self._ordinary()
            if not self.path.is_file() or self.path.stat().st_size>512*1024:return
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('schema_version')!='core-next.observations/1' or data.get('installation')!=self.identity:return
            now=self.clock()
            for identifier,item in data.get('observations',{}).items():
                if identifier not in self.registry.definitions:continue
                try:
                    at=datetime.fromisoformat(item['observed_at'].replace('Z','+00:00'))
                    expiry=datetime.fromisoformat(item['expires_at'].replace('Z','+00:00'))
                    success=datetime.fromisoformat(item['last_success_at'].replace('Z','+00:00')) if item.get('last_success_at') else None
                    if at.utcoffset() is None or at>now or not 0<(expiry-at).total_seconds()<=self.registry.ttl:continue
                    sampled=datetime.fromisoformat(item['metrics_sampled_at'].replace('Z','+00:00')) if item.get('metrics_sampled_at') else None
                    metrics_expiry=datetime.fromisoformat(item['metrics_expires_at'].replace('Z','+00:00')) if item.get('metrics_expires_at') else None
                    if sampled is not None and (sampled.utcoffset() is None or sampled>at):continue
                    if metrics_expiry is not None and (sampled is None or not sampled<metrics_expiry<=sampled+timedelta(seconds=self.registry.ttl)):continue
                    value=Observation('UNVERIFIED','RESTORED_HISTORICAL_EVIDENCE',at,expiry,item.get('metrics',{}),
                        ('Historical same-build observation; startup must check again',),self.registry.installation_id,identifier,
                        success,sampled,item.get('observation_id',''),item.get('observer_identity',''),
                        self.registry.build_identity,('RESTORED_HISTORICAL_EVIDENCE',),metrics_expiry)
                    self.registry.observations[identifier]=value
                except (ValueError,TypeError,KeyError,AttributeError):continue
        except (OSError,ValueError,TypeError,AttributeError):self.last_cache_error='OBSERVATION_HISTORY_UNREADABLE'
    def _persist(self):
        temporary=None
        try:
            self._ordinary()
            if not self.state.is_dir():raise OSError('MISSING_OWNED_STATE')
            with self.registry.lock:
                observations={identifier:{'state':v.state,'reason':v.reason,'observed_at':iso(v.observed_at),
                    'expires_at':iso(v.expires_at),'last_success_at':iso(v.last_success) if v.last_success else None,
                    'metrics':dict(v.metrics),'observation_id':v.observation_id,'observer_identity':v.observer_identity,
                    'metrics_sampled_at':iso(v.metrics_sampled_at) if v.metrics_sampled_at else None,
                    'metrics_expires_at':iso(v.metrics_expiry) if v.metrics_expiry else None,
                    'build_identity':v.build_identity,'verification_scope':list(v.verification_scope)}
                    for identifier,v in self.registry.observations.items()}
            data={'schema_version':'core-next.observations/1','installation':self.identity,'cycle_id':self.cycle_id,
                'observations':observations,'saved_at':iso(self.clock())}
            raw=(json.dumps(data,sort_keys=True,allow_nan=False)+'\n').encode()
            if len(raw)>512*1024:raise ValueError('OBSERVATION_CACHE_TOO_LARGE')
            temporary=self.path.with_name(self.path.name+'.'+uuid4().hex+'.tmp')
            with temporary.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            self._ordinary();os.replace(temporary,self.path)
            self.last_cache_error=None
        except (OSError,ValueError,TypeError):self.last_cache_error='OBSERVATION_CACHE_WRITE_FAILED'
        finally:
            if temporary is not None:
                try:
                    self._ordinary()
                    temporary.unlink(missing_ok=True)
                except OSError:pass # Never delete through a rejected ancestor.
    def start(self):
        self._load_history();self.running=True;self.registry.running=True
        return self.tick(force=True)
    def stop(self):
        self.running=False
        if self.lock.acquire(timeout=3):
            try:self._persist()
            finally:self.lock.release()
        else:self.last_cache_error='OBSERVER_STOP_FLUSH_TIMEOUT'
    def tick(self,force=False):
        if not self.running:return self.result('disabled')
        if not force and self.monotonic()<self.next_due:return None
        if not self.lock.acquire(blocking=False):return self.result('busy')
        try:
            self.supporting.begin_cycle();results={};failures=[]
            for identifier in self.registry._order:
                if identifier in self.registry.disabled:
                    results[identifier]={'state':'UNAVAILABLE','reason':'MODULE_DISABLED_BY_PROFILE','metrics':{}}
                    continue
                try:
                    result=self.registry.bindings[identifier].observe()
                    # Validate the clock/state/metrics before publishing the batch.
                    now=self.clock();at=result.get('observed_at',now);expiry=result.get('expires_at',at+timedelta(seconds=self.registry.ttl))
                    if at>now or expiry<=now:raise ValueError('INVALID_SOURCE_EVIDENCE_CLOCK')
                    Observation(result['state'],result['reason'],at,expiry,result.get('metrics',{}),last_success=result.get('last_success_at'))
                    results[identifier]={**result,'_observed_at':at}
                except Exception:
                    failures.append(identifier);results[identifier]={'state':'DEGRADED','reason':'BOUNDED_LOCAL_OBSERVATION_FAILED','metrics':{},'_observed_at':self.clock()}
            self.cycle_id=uuid4().hex
            if not self.running:return self.result('disabled')
            with self.registry.lock:
                for identifier,result in results.items():
                    self.registry.record(identifier,result['state'],result['reason'],metrics=result.get('metrics',{}),
                        evidence=result.get('evidence',()),observer_identity='core-next.local-observer:'+str(os.getpid()),
                        verification_scope=('LIGHTWEIGHT_LOCAL_OBSERVATION',),observed_at=result.get('_observed_at'),
                        expires_at=result.get('expires_at'),last_success_at=result.get('last_success_at'),
                        service_identity=result.get('service_identity'))
            self.completed+=1;self.failed=len(failures);self.last_observed=self.clock()
            # One failed observation never blocks other modules; capped cadence
            # backoff avoids tight retries while preserving expiry honesty.
            delay=min(300,self.interval*(2 if failures else 1));self.next_due=self.monotonic()+delay
            self._persist()
            return self.result('completed',failures)
        finally:self.lock.release()
    def result(self,status,failures=()):
        remaining=max(0,self.next_due-self.monotonic())
        return {'schema_version':'core-next.local-observation/1','installation':self.identity,'status':status,
            'observed_at':iso(self.last_observed) if self.last_observed else None,'observation_id':self.cycle_id,
            'observer_identity':'core-next.local-observer:'+str(os.getpid()),
            'next_due_at':iso(self.clock()+timedelta(seconds=remaining)) if self.running else None,
            'failed_module_ids':list(failures),'inventory':self.registry.inventory(),
            'cache_state':'unavailable' if self.last_cache_error else 'saved','cache_reason':self.last_cache_error,
            'verification_scope':'LIGHTWEIGHT_LOCAL_OBSERVATION; no acquisition, forecasts, inference or service control'}
