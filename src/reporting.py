import csv,json,os,math
from datetime import datetime,timezone,timedelta
def dt(s):return datetime.fromisoformat(s.replace('Z','+00:00')) if s else None
def readj(p):
 with open(p,encoding='utf-8') as f:return [json.loads(x) for x in f if x.strip()]
def writej(p,rows):
 with open(p,'w',encoding='utf-8') as f:
  for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
def judge_outcomes(out,simout):
 ds=readj(out+'/decisions.jsonl');ev=readj(simout+'/outcome_events.jsonl');by={}
 for e in ev:by.setdefault(e['user_id'],[]).append(e)
 observed_until=max((dt(e.get('received_at')) for e in ev if dt(e.get('received_at'))),default=None)
 ist=timezone(timedelta(hours=5,minutes=30));res=[]
 for d in ds:
  g=d.get('goal');start=dt(g.get('started_at') or d['trigger']['received_at']) if g else dt(d['trigger']['received_at']);end=dt(g['deadline']) if g else None;matches=[]
  if g and g.get('success_event') and end:
   candidates=[]
   for e in by.get(d['viewer_id'],[]):
    t=dt(e.get('received_at'))
    if e.get('event')==g['success_event'] and start<t<=end:candidates.append(e)
   cond=g.get('success_condition','')
   if g.get('id')=='G03' and 'later IST calendar day' in cond:
    candidates=[e for e in candidates if dt(e['received_at']).astimezone(ist).date()>start.astimezone(ist).date()]
   elif g.get('id') in ('G04','G05'):
    candidates=[e for e in candidates if e.get('properties',{}).get('is_trial') is False]
   elif g.get('id')=='G07':
    ids=set(g.get('target_title_ids',[]));candidates=[e for e in candidates if e.get('properties',{}).get('title_id') in ids]
   elif g.get('id')=='G08':
    ids=set(g.get('target_title_ids',[]));candidates=[e for e in candidates if e.get('properties',{}).get('title_id') in ids]
   elif g.get('id')=='G09':
    days={dt(e['received_at']).astimezone(ist).date() for e in candidates}
    if len(days)<3:candidates=[]
   matches=candidates
  if not g:status='inconclusive';reason='no measurable eligible goal'
  elif matches:status='succeeded';reason='matching success signal and goal-specific conditions observed inside the goal window'
  elif observed_until and observed_until>=end:status='failed';reason='observation horizon covered the deadline but no qualifying success signal was observed'
  else:status='inconclusive';reason='simulator observation horizon did not cover the complete goal window'
  res.append({'decision_id':d['decision_id'],'user_id':d['viewer_id'],'goal_id':g.get('id') if g else None,'goal_started_at':g.get('started_at',d['trigger']['received_at']) if g else d['trigger']['received_at'],'deadline':g.get('deadline') if g else None,'success_event':g.get('success_event') if g else None,'status':status,'reason':reason})
 writej(out+'/outcomes.jsonl',res);return res

def make_impact_report(root,out,simout):
 with open(root+'/pilot/pilot_outcomes.csv',encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
 arms={}
 for r in rows:arms.setdefault(r['arm'],[]).append(r['succeeded'].lower()=='true')
 def rate(a):return sum(a)/len(a) if a else 0
 t,c=arms.get('treatment',[]),arms.get('holdout',[]);rt,rc=rate(t),rate(c);diff=rt-rc;se=math.sqrt(rt*(1-rt)/len(t)+rc*(1-rc)/len(c));ci=(diff-1.96*se,diff+1.96*se)
 sim=json.load(open(simout+'/simulator_report.json',encoding='utf-8'));lat=json.load(open(out+'/latency_report.json',encoding='utf-8'));acts=readj(out+'/actions.jsonl');outcomes=readj(out+'/outcomes.jsonl');summary={}
 for x in outcomes:
  if x['goal_id']:summary.setdefault(x['goal_id'],{'succeeded':0,'failed':0,'inconclusive':0})[x['status']]+=1
 report=f"""# Impact report\n\n## Historical randomized pilot re-analysis (intention-to-treat)\n\n- Treatment: {sum(t)}/{len(t)} = {rt:.3%}\n- Holdout: {sum(c)}/{len(c)} = {rc:.3%}\n- Difference: {diff:+.3%}; 95% Wald CI [{ci[0]:+.3%}, {ci[1]:+.3%}]\n\nThis uses randomized assignment, regardless of whether the user was served. Served-vs-unserved comparisons are biased by selection because users who receive interventions can already be more active.\n\n## Replay diagnostics\n\n- Triggered users: {sim.get('triggered_users')}\n- Agent actions: {len(acts)}\n- Simulator policy problems: {sim.get('policy_problem_count')}\n- Max local decision time: {lat['max_decision_ms']} ms; all within 60 seconds: {lat['within_60_seconds']}\n- Goal judgments: `{json.dumps(summary,sort_keys=True)}`\n\nReplay results are operational diagnostics, not causal proof; the simulator covers triggered users only.\n"""
 open(out+'/impact_report.md','w',encoding='utf-8').write(report)
 open(out+'/final_report.md','w',encoding='utf-8').write(f"# Final report\n\nDecisions: {lat['decisions']}\n\nActions: {lat['actions']}\n\nNo-action decisions: {lat['no_action']}\n\nMax local decision time: {lat['max_decision_ms']} ms\n\nWithin 60 seconds: {lat['within_60_seconds']}\n\nHistorical pilot ITT: {diff:+.3%} (95% CI {ci[0]:+.3%}, {ci[1]:+.3%}).\n\nG10 is excluded because it has no measurable success event. The baseline is deterministic and avoids external model calls.")
