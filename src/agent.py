import csv,json,os,time,hashlib,argparse
from src.model_provider import MockModelProvider
from datetime import datetime,timedelta,timezone
UTC=timezone.utc; IST=timezone(timedelta(hours=5,minutes=30))
def dt(s): return datetime.fromisoformat(s.replace('Z','+00:00')) if s else None
def iso(t): return t.astimezone(UTC).isoformat(timespec='milliseconds').replace('+00:00','Z')
def jl(p):
 with open(p,encoding='utf-8') as f:
  for x in f:
   if x.strip(): yield json.loads(x)
def csvr(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def dumpj(p,rows):
 os.makedirs(os.path.dirname(p),exist_ok=True)
 with open(p,'w',encoding='utf-8') as f:
  for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
def sid(*x):return hashlib.sha256(':'.join(map(str,x)).encode()).hexdigest()[:16]
class ViewerAgent:
 def __init__(self,root):
  self.root=root
  with open(root+'/config/goals.json',encoding='utf-8') as f:self.goals=json.load(f)['goals']
  self.profiles={}
  for p in csvr(root+'/data/profiles_snapshot.csv'):
   if p['user_id'] not in self.profiles or p['updated_at']>self.profiles[p['user_id']]['updated_at']:self.profiles[p['user_id']]=p
  self.episodes={}
  for ep in csvr(root+'/data/episodes.csv'):self.episodes.setdefault(ep['content_slug'],[]).append(ep)
  self.cat={}
  for t in csvr(root+'/data/catalogue.csv'):
   t['genres']=t['genres'].split('|');t['start']=dt(t['available_from']);t['end']=dt(t['available_until']);self.cat[t['title_id']]=t
  self.arms={r['user_id']:r['arm'] for r in csvr(root+'/replay/arms.csv')}; self.hist={}; seen=set()
  for e in jl(root+'/data/events.jsonl'):
   if e['event_id'] in seen:continue
   seen.add(e['event_id']);self.hist.setdefault(e['user_id'],[]).append(e)
  self.live={}
  for e in jl(root+'/replay/live_events.jsonl'):self.live.setdefault(e['user_id'],[]).append(e)
  self.withdraw={e['title_id']:dt(e['at']) for e in jl(root+'/replay/control_events.jsonl') if e.get('type')=='title_withdrawn'}
  self.faults={e['trigger_event_id']:e for e in jl(root+'/replay/model_faults.jsonl')};self.provider=MockModelProvider(self.faults);self.processed=set();self.decisions=[];self.actions=[];self.states={};self.active_goals={}
  with open(root+'/config/interventions.json',encoding='utf-8') as f:self.interventions=json.load(f)
  with open(root+'/config/pricing.json',encoding='utf-8') as f:self.pricing=json.load(f)
  self.message_days={}
 def facts(self,u,at):
  p=dict(self.profiles.get(u,{})); es=[e for e in self.hist.get(u,[])+self.live.get(u,[]) if dt(e.get('received_at'))<=at]
  pur=[e for e in es if e['event'] in ('purchase_completed','subscription_renewed')]; lap=[e for e in es if e['event']=='subscription_lapsed']
  if pur and (not lap or max(dt(x['received_at']) for x in pur)>max(dt(x['received_at']) for x in lap)):p['subscription_status']='active'
  elif lap and (not pur or max(dt(x['received_at']) for x in lap)>max(dt(x['received_at']) for x in pur)):p['subscription_status']='lapsed'
  for e in es:
   if e['event']=='notification_opt_out':
    ch=e.get('properties',{}).get('channel');p['notifications_opt_in' if ch=='push' else 'whatsapp_opt_in']='false'
  return p,es
 def goal(self,p,es,at):
  ev={e['event'] for e in es}; signup=dt(p.get('signup_at')); status=p.get('subscription_status','unknown'); c=[]
  if signup and 0<=(at-signup).total_seconds()<=7*86400 and 'play_started' not in ev:c.append(('G01',4))
  if 'episode_completed' not in ev:c.append(('G02',3))
  if signup and 0<=(at-signup).total_seconds()<=2*86400:c.append(('G03',5))
  if status=='trial_active':c.append(('G04',4))
  if status=='never':c.append(('G05',2))
  if status=='lapsed':c.append(('G06',2))
  # Resume a lapsed show/micro-drama only when there are unwatched episodes and no recent play.
  by_slug={}
  for e in es:
   tid=e.get('properties',{}).get('title_id'); t=self.cat.get(tid)
   if not t or t.get('content_type') not in ('show','micro_drama','micro-drama'):continue
   slug=t['content_slug']; by_slug.setdefault(slug,{'plays':[],'completed':set()})
   if e['event']=='play_started':by_slug[slug]['plays'].append(dt(e['received_at']))
   if e['event']=='episode_completed':by_slug[slug]['completed'].add(e.get('properties',{}).get('episode_id'))
  for slug,info in by_slug.items():
   eps=self.episodes.get(slug,[])
   if info['plays'] and eps and len(info['completed'])<len(eps) and (at-max(info['plays'])).total_seconds()>=3*86400:
    c.append(('G07',4));break
  if status=='active':
   recent_release=any(t.get('release_date') and 0 <= (at.date()-datetime.fromisoformat(t['release_date']).date()).days <= 30 and t['start'] and t['start']<=at and (not t['end'] or at<t['end']) and (t['title_id'] not in self.withdraw or at<self.withdraw[t['title_id']]) for t in self.cat.values())
   playdays={dt(e['received_at']).astimezone(IST).date() for e in es if e['event']=='play_started' and dt(e['received_at'])>=at-timedelta(days=14)}
   if len(playdays)<=1:c.append(('G09',4))
   if recent_release:c.append(('G08',2))
   c.append(('G11',1))
  if not any(e['event']=='app_open' and dt(e['received_at'])>=at-timedelta(days=14) for e in es):c.append(('G12',3))
  if not c:return None
  gid=max(c,key=lambda x:x[1])[0];g=next(x for x in self.goals if x['goal_id']==gid);s=g['success']
  if not s.get('event'):return None
  result={'id':gid,'name':g['name'],'deadline':iso(at+timedelta(hours=s['window_hours'])),'success_event':s['event'],'success_condition':s['condition'],'window_hours':s['window_hours']}
  if gid=='G07':
   for slug,info in by_slug.items():
    eps=self.episodes.get(slug,[])
    if info['plays'] and eps and len(info['completed'])<len(eps) and (at-max(info['plays'])).total_seconds()>=3*86400:
     result['target_content_slug']=slug;result['target_title_ids']=[t['title_id'] for t in self.cat.values() if t['content_slug']==slug];break
  if gid=='G08':
   result['target_title_ids']=[t['title_id'] for t in self.cat.values() if t.get('release_date') and 0 <= (at.date()-datetime.fromisoformat(t['release_date']).date()).days <= 30 and t['start'] and t['start']<=at and (not t['end'] or at<t['end']) and (t['title_id'] not in self.withdraw or at<self.withdraw[t['title_id']])]
  result['started_at']=iso(at)
  return result
 def goal_succeeded(self,g,es,at):
  start=dt(g.get('started_at'));deadline=dt(g.get('deadline'))
  if not start:return False
  relevant=[e for e in es if e.get('event')==g.get('success_event') and dt(e.get('received_at')) and start<dt(e['received_at'])<=at and (not deadline or dt(e['received_at'])<=deadline)]
  cond=g.get('success_condition','')
  if g.get('id')=='G03' and 'later IST calendar day' in cond:
   relevant=[e for e in relevant if dt(e['received_at']).astimezone(IST).date()>start.astimezone(IST).date()]
  elif g.get('id') in ('G04','G05'):
   relevant=[e for e in relevant if e.get('properties',{}).get('is_trial') is False]
  elif g.get('id') in ('G07','G08'):
   ids=set(g.get('target_title_ids',[]));relevant=[e for e in relevant if e.get('properties',{}).get('title_id') in ids]
  elif g.get('id')=='G09':
   days={dt(e['received_at']).astimezone(IST).date() for e in relevant}
   return len(days)>=3
  return bool(relevant)
 def page(self,d,at,es):
  ts=[t for t in self.cat.values() if t['dialect']==d and t['start'] and t['start']<=at and (not t['end'] or at<t['end']) and (t['title_id'] not in self.withdraw or at<self.withdraw[t['title_id']])]
  watched={self.cat[e.get('properties',{}).get('title_id')]['content_slug'] for e in es if e['event'] in ('play_started','episode_completed') and e.get('properties',{}).get('title_id') in self.cat}
  ts.sort(key=lambda t:(t['content_slug'] in watched,t['is_premium']=='true',t['title_id'])); unique=[];slugs=set()
  for t in ts:
   if t['content_slug'] not in slugs:unique.append(t);slugs.add(t['content_slug'])
  if len(unique)<3:return None
  chosen=unique[:10];return {'hero_title_id':unique[10]['title_id'] if len(unique)>10 else unique[0]['title_id'],'rows':[{'row_type':'popular_in_dialect','title_ids':[t['title_id'] for t in chosen]}]}

 def _message_send_time(self, at):
  """Return an allowed send time, deferring messages during IST quiet hours."""
  local=at.astimezone(IST)
  if local.hour >= 22:
   local=(local+timedelta(days=1)).replace(hour=8,minute=0,second=0,microsecond=0)
  elif local.hour < 8:
   local=local.replace(hour=8,minute=0,second=0,microsecond=0)
  return local.astimezone(UTC)

 def _message_already_used(self, u, send_at, es):
  day=send_at.astimezone(IST).date().isoformat()
  if day in self.message_days.get(u,set()): return True
  for e in es:
   if e.get('event')=='message_delivered' and dt(e.get('received_at')) and dt(e['received_at']).astimezone(IST).date().isoformat()==day:
    return True
  for a in self.actions:
   if a.get('user_id')==u and a.get('type') in ('push','whatsapp'):
    t=dt(a.get('send_at') or a.get('published_at'))
    if t and t.astimezone(IST).date().isoformat()==day:return True
  return False

 def message_action(self,u,e,p,es,g,d,at):
  """Build one policy-compliant mock push/WhatsApp action when the goal warrants it."""
  if not g or not d:return None, None
  status=p.get('subscription_status','unknown')
  target_ids=g.get('target_title_ids') or []
  title=None
  for tid in target_ids:
   t=self.cat.get(tid)
   if t and t['dialect']==d and t['start'] and t['start']<=at and (not t['end'] or at<t['end']) and (tid not in self.withdraw or at<self.withdraw[tid]):
    title=t;break
  # Trial conversion is best served by the approved trial-ending template.
  wa_consent=p.get('whatsapp_opt_in')=='true' and p.get('preferred_language')=='hin' and e.get('app_language','hin')=='hin'
  push_consent=p.get('notifications_opt_in')=='true'
  if g.get('id')=='G04' and wa_consent:
   template=next((x for x in self.interventions['whatsapp']['approved_templates'] if x['template_id']=='wa_trial_ending_v1'),None)
   plan=next((x for x in self.pricing['plans'] if x['plan_id']=='P_MONTH'),None)
   if template and plan:
    send=self._message_send_time(at)
    if not self._message_already_used(u,send,es):
     price='₹%s/month'%plan['price_inr']
     body=template['text'].replace('{{plan_price}}',price)
     return {'action_id':'A-'+sid(u,e['event_id'],'whatsapp'),'user_id':u,'type':'whatsapp','send_at':iso(send),'template_id':template['template_id'],'template_variables':{'plan_price':price},'rendered_text':body,'language':'hin','dialect':d}, None
  # For resume/recent-release goals, use a title-specific push if opted in.
  if g.get('id') in ('G07','G08') and push_consent and title:
   send=self._message_send_time(at)
   if not self._message_already_used(u,send,es):
    name=title['title']
    headline=('New release: '+name)[:40]
    body=('Watch '+name+' in '+d+'.')[:120]
    forbidden=self.interventions['push']['copy']['forbidden_phrases']
    if not any(x.lower() in (headline+' '+body).lower() for x in forbidden):
     return {'action_id':'A-'+sid(u,e['event_id'],'push'),'user_id':u,'type':'push','send_at':iso(send),'title_id':title['title_id'],'title':headline,'body':body,'deeplink':'ott://title/'+title['title_id'],'dialect':d}, None
  # Use a general recommendation template only for Hindi-language users and a real title.
  if g.get('id') in ('G07','G08') and wa_consent and title:
   template=next((x for x in self.interventions['whatsapp']['approved_templates'] if x['template_id']=='wa_recommend_title_v1'),None)
   send=self._message_send_time(at)
   if template and not self._message_already_used(u,send,es):
    variables={'title_name':title['title'],'dialect_name':d}
    body=template['text'].replace('{{title_name}}',variables['title_name']).replace('{{dialect_name}}',variables['dialect_name'])
    return {'action_id':'A-'+sid(u,e['event_id'],'whatsapp'),'user_id':u,'type':'whatsapp','send_at':iso(send),'template_id':template['template_id'],'template_variables':variables,'rendered_text':body,'title_id':title['title_id'],'language':'hin','dialect':d}, None
  return None, 'No eligible, consented message opportunity; use home page or abstain.'

 def verify_message(self, action, p, es, at):
  """Independent hard gate for outbound mock message actions."""
  if self.arms.get(action['user_id'])=='holdout':return False,'holdout gate'
  typ=action.get('type');send=dt(action.get('send_at'))
  if typ not in ('push','whatsapp') or not send:return False,'unsupported message type or missing send time'
  local=send.astimezone(IST)
  if local.hour<8 or local.hour>=22:return False,'quiet hours'
  if self._message_already_used(action['user_id'],send,es):return False,'combined push/WhatsApp daily cap'
  consent='notifications_opt_in' if typ=='push' else 'whatsapp_opt_in'
  if p.get(consent)!='true':return False,'missing consent or opt-out override'
  if typ=='push':
   limits=self.interventions['push']['copy']
   if len(action.get('title',''))>limits['title_max_chars'] or len(action.get('body',''))>limits['body_max_chars']:return False,'push copy exceeds length limit'
   if action.get('deeplink')!='ott://title/'+str(action.get('title_id')):return False,'invalid push deeplink'
   if any(x.lower() in (action.get('title','')+' '+action.get('body','')).lower() for x in limits['forbidden_phrases']):return False,'forbidden push phrase'
  else:
   approved={x['template_id']:x for x in self.interventions['whatsapp']['approved_templates']}
   template=approved.get(action.get('template_id'))
   if not template:return False,'unapproved WhatsApp template'
   if p.get('preferred_language')!='hin' or action.get('language')!='hin':return False,'template language mismatch'
   if set(action.get('template_variables',{}))!=set(template['variables']):return False,'template variables mismatch'
   if action.get('title_id'):
    t=self.cat.get(action['title_id'])
    if not t or t['dialect']!=action.get('dialect') or not t['start'] or t['start']>send or (t['end'] and send>=t['end']) or (action['title_id'] in self.withdraw and send>=self.withdraw[action['title_id']]):return False,'invalid title/dialect/availability'
  return True,None

 def process(self,e):
  u=e['user_id'];eid=e['event_id'];at=dt(e.get('deliver_at') or e['received_at']); start=time.perf_counter()
  if eid in self.processed:return
  self.processed.add(eid);age=max(0,(dt(e['received_at'])-dt(e['occurred_at'])).total_seconds());p,es=self.facts(u,at);d=e.get('app_dialect') or p.get('preferred_dialect');conf=[]
  if d and p.get('preferred_dialect') and d!=p['preferred_dialect']:conf.append('profile:'+p['preferred_dialect'])
  provider_result=self.provider.inspect_trigger(eid)
  g=self.active_goals.get(u);
  # Keep one active goal per viewer until it succeeds, expires, or becomes invalidated by new evidence.
  if g and (not g.get('deadline') or dt(g['deadline'])<=at or self.goal_succeeded(g,es,at)):
   g=None;self.active_goals.pop(u,None)
  if g is None:g=self.goal(p,es,at)
  a=None;reason=None;status='NO_ACTION';ev=[];confidence=.65;cr='Deterministic rule-based decision; eligibility and content checked from supplied evidence.'
  if self.arms.get(u)=='holdout':reason='Randomized holdout: no action permitted.';g=None;confidence=.99
  elif age>600:reason='Stale/offline-buffered trigger; no live intervention.';g=None;confidence=.98
  elif provider_result.fault:ev.append('model_fault:'+provider_result.fault);cr='Injected provider fault; deterministic safe path used without an external model call.';confidence=.55
  if not reason and g and d:
   msg, msg_reason=self.message_action(u,e,p,es,g,d,at)
   if msg:
    valid_msg, msg_error=self.verify_message(msg,p,es,at)
    if valid_msg:
     self.actions.append(msg);self.message_days.setdefault(u,set()).add(dt(msg['send_at']).astimezone(IST).date().isoformat());a=msg;status='SCHEDULED';ev += ['goal_rule:'+g['id'],'message_policy:verified']
    else:
     ev.append('message_rejected:'+str(msg_error))
   if a is None:
    pg=self.page(d,at,es)
   else:
    pg=None
   if pg:
    a={'action_id':'A-'+sid(u,eid),'user_id':u,'type':'home_page','published_at':iso(at+timedelta(milliseconds=10)),'dialect':d,**pg}
    # Independent verifier: all titles must exist, be available in dialect, and be slug-unique.
    slugs=[];valid=True
    for row in a['rows']:
     for tid in row['title_ids']:
      t=self.cat.get(tid)
      if not t or t['dialect']!=d or t['start']>at or (t['end'] and at>=t['end']) or (tid in self.withdraw and at>=self.withdraw[tid]) or t['content_slug'] in slugs:valid=False
      elif t:slugs.append(t['content_slug'])
     if len(row['title_ids'])<3 or len(row['title_ids'])>10:valid=False
    if valid and self.arms.get(u)!='holdout':self.actions.append(a);status='PUBLISHED';ev += ['goal_rule:'+g['id']]+['catalogue:'+x for row in a['rows'] for x in row['title_ids']]
    else:a=None;reason='Independent verifier rejected the proposed home page.'
   elif a is None:reason='Insufficient valid titles in current app dialect.'
  elif not reason:reason='No measurable eligible goal or no authoritative dialect.'
  elapsed=max(1,int((time.perf_counter()-start)*1000))
  decision={'decision_id':'D-'+sid(u,eid),'viewer_id':u,'trigger':{'event':e.get('event'),'event_id':eid,'received_at':e.get('received_at'),'event_age_s':int(age)},'goal':g,'action':a['type'].upper() if a else 'NONE','dialect':{'used':d,'source':'app_setting' if e.get('app_dialect') else 'profile_fallback','conflicts':conf},'content':(([a['hero_title_id']]+[x for r in a['rows'] for x in r['title_ids']]) if a and a['type']=='home_page' else ([a['title_id']] if a and a.get('title_id') else [])),'confidence':confidence,'confidence_reason':cr,'evidence':ev+(['profile_snapshot:'+u+'@'+p.get('updated_at','unknown')] if p else []),'assumptions':['Newer purchase/lapse and opt-out events override the profile snapshot.'],'checks':{'passed':['idempotency','holdout_gate','freshness_gate']+(['goal_eligibility','dialect','availability','slug_uniqueness','row_size'] if a and a['type']=='home_page' else (['goal_eligibility','consent','quiet_hours','frequency_cap','template_or_copy_validation'] if a and a['type'] in ('push','whatsapp') else [])),'failed':[]},'decided_in_ms':elapsed,'deadline':g['deadline'] if g else None,'success_signal':g['success_event'] if g else None,'no_action_reason':reason,'status':status,'rule_version':'2026-09-30','model_calls':0,'tool_calls':0,'fallback_used':provider_result.mode=='deterministic_fallback'}
  self.decisions.append(decision)
  if g:self.active_goals[u]=g
  st=self.states.setdefault(u,{'viewer_id':u,'facts':[],'active_goal':None,'decision_ids':[],'actions':[],'outcomes':[]});st['active_goal']=g;st['decision_ids'].append(decision['decision_id'])
  st['facts']=[{'fact':'subscription_status','value':p.get('subscription_status'),'source':'profile_snapshot+events','as_of':e['received_at'],'freshness':'event-resolved as of trigger; profile snapshot may be stale'},{'fact':'dialect','value':d,'source':'app_setting' if e.get('app_dialect') else 'profile_snapshot','as_of':e['received_at'],'freshness':'current trigger setting' if e.get('app_dialect') else 'snapshot fallback'}]
  if a:st['actions'].append(a['action_id'])
def run(root='.',out='sample_run'):
 a=ViewerAgent(root);tr=sorted(jl(root+'/replay/triggers.jsonl'),key=lambda e:e.get('deliver_at') or e['received_at'])
 controls=sorted(jl(root+'/replay/control_events.jsonl'),key=lambda e:e.get('at',''))
 # Replay controls in event time. Rule corrections update only still-open goals; title withdrawals are checked at publish time.
 merged=[(dt(e.get('deliver_at') or e['received_at']),0,e) for e in tr]+[(dt(c['at']),1,c) for c in controls]
 for when,kind,obj in sorted(merged,key=lambda x:(x[0],x[1])):
  if kind==0:a.process(obj)
  elif obj.get('type')=='goal_rule_corrected':
   gid=obj.get('goal_id'); new=obj.get('new_success',{})
   for g in a.goals:
    if g['goal_id']==gid:g['success']=dict(g['success'],**new)
   for d in a.decisions:
    g=d.get('goal')
    if g and g.get('id')==gid and dt(g.get('deadline')) and dt(g['deadline'])>when:
     g['success_event']=new.get('event',g.get('success_event'));g['success_condition']=new.get('condition',g.get('success_condition'));d['success_signal']=g['success_event'];d.setdefault('rule_updates',[]).append({'at':iso(when),'control_event':'goal_rule_corrected','new_success':new})
   for st in a.states.values():
    g=st.get('active_goal')
    if g and g.get('id')==gid and dt(g.get('deadline')) and dt(g['deadline'])>when:
     g['success_event']=new.get('event',g.get('success_event'));g['success_condition']=new.get('condition',g.get('success_condition'))
 dumpj(out+'/decisions.jsonl',a.decisions);dumpj(out+'/actions.jsonl',a.actions);os.makedirs(out+'/viewer_state',exist_ok=True)
 for u,s in a.states.items():
  with open(out+'/viewer_state/'+u+'.json','w',encoding='utf-8') as f:json.dump(s,f,indent=2)
 ts=[d['decided_in_ms'] for d in a.decisions];r={'decisions':len(a.decisions),'actions':len(a.actions),'no_action':sum(d['action']=='NONE' for d in a.decisions),'max_decision_ms':max(ts,default=0),'p95_decision_ms':sorted(ts)[int(.95*(len(ts)-1))] if ts else 0,'within_60_seconds':all(x<=60000 for x in ts),'duplicate_triggers_skipped':len(tr)-len(a.processed),'stale_trigger_decisions':sum('Stale/offline' in (d.get('no_action_reason') or '') for d in a.decisions),'model_calls':0,'tool_calls':0}
 with open(out+'/latency_report.json','w',encoding='utf-8') as f:json.dump(r,f,indent=2)
 return r
def main():
 p=argparse.ArgumentParser();p.add_argument('--pack',default='.');p.add_argument('--out',default='sample_run');x=p.parse_args();print(json.dumps(run(x.pack,x.out),indent=2))
if __name__=='__main__':main()
