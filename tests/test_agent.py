import json, os, tempfile, unittest
from datetime import datetime, timezone, timedelta
from src.agent import ViewerAgent, run
from src.reporting import judge_outcomes, make_impact_report
ROOT=os.path.dirname(os.path.dirname(__file__))

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.agent=ViewerAgent(ROOT)

    @staticmethod
    def trigger(user='U-00001', event_id='test-event', at='2026-10-01T12:00:00Z', dialect='d1', occurred=None):
        return {'user_id':user,'event_id':event_id,'event':'app_open','received_at':at,
                'occurred_at':occurred or at,'sent_at':occurred or at,'deliver_at':at,
                'session_id':'session-'+event_id,'app_dialect':dialect,'properties':{}}

    def test_duplicate_trigger_is_idempotent(self):
        e=self.trigger(); self.agent.process(e); n=len(self.agent.decisions); actions=len(self.agent.actions)
        self.agent.process(e)
        self.assertEqual(len(self.agent.decisions),n)
        self.assertEqual(len(self.agent.actions),actions)

    def test_holdout_never_gets_action(self):
        user=next(u for u,a in self.agent.arms.items() if a=='holdout')
        e=self.trigger(user=user,event_id='holdout-test')
        self.agent.process(e)
        self.assertFalse(any(a['user_id']==user for a in self.agent.actions))
        self.assertEqual(self.agent.decisions[-1]['action'],'NONE')
        self.assertIn('holdout',self.agent.decisions[-1]['no_action_reason'].lower())

    def test_stale_trigger_abstains(self):
        user=next(u for u,a in self.agent.arms.items() if a!='holdout')
        e=self.trigger(user=user,event_id='stale-test',at='2026-10-01T12:00:00Z',occurred='2026-10-01T11:00:00Z')
        self.agent.process(e)
        self.assertEqual(self.agent.decisions[-1]['action'],'NONE')
        self.assertIn('Stale/offline',self.agent.decisions[-1]['no_action_reason'])

    def test_app_dialect_is_authoritative_and_conflict_visible(self):
        user=next(u for u,p in self.agent.profiles.items() if p.get('preferred_dialect') and p['preferred_dialect']!='d1' and self.agent.arms.get(u)!='holdout')
        e=self.trigger(user=user,event_id='dialect-test',dialect='d1')
        self.agent.process(e)
        d=self.agent.decisions[-1]
        self.assertEqual(d['dialect']['used'],'d1')
        self.assertIn('profile:'+self.agent.profiles[user]['preferred_dialect'],d['dialect']['conflicts'])

    def test_unmeasurable_goal_is_not_selected(self):
        p={'subscription_status':'active','signup_at':'2026-09-30T00:00:00Z'}
        g=self.agent.goal(p,[],datetime.fromisoformat('2026-10-01T12:00:00+00:00'))
        self.assertNotEqual((g or {}).get('id'),'G10')
        self.assertTrue((g or {}).get('success_event'))

    def test_active_goal_is_retained_until_success_or_expiry(self):
        user=next(u for u,a in self.agent.arms.items() if a!='holdout' and u in self.agent.profiles)
        e1=self.trigger(user=user,event_id='goal-one')
        self.agent.process(e1)
        g1=self.agent.decisions[-1].get('goal')
        if not g1: self.skipTest('Chosen fixture has no measurable eligible goal')
        e2=self.trigger(user=user,event_id='goal-two',at='2026-10-01T12:00:05Z')
        self.agent.process(e2)
        self.assertEqual(self.agent.decisions[-1]['goal']['id'],g1['id'])

    def test_model_fault_is_recorded_and_safe_path_used(self):
        trigger_id,fault=next((eid,f) for eid,f in self.agent.faults.items() if self.agent.arms.get(f['user_id'])!='holdout')
        e=self.trigger(user=fault['user_id'],event_id=trigger_id)
        self.agent.process(e)
        d=self.agent.decisions[-1]
        self.assertTrue(d['fallback_used'])
        self.assertTrue(any(x.startswith('model_fault:') for x in d['evidence']))

    def test_corrected_goal_rule_updates_only_open_goals(self):
        with tempfile.TemporaryDirectory() as out:
            run(ROOT,out)
            with open(out+'/decisions.jsonl',encoding='utf-8') as f: ds=[json.loads(x) for x in f]
            corrected=[d for d in ds if (d.get('goal') or {}).get('id')=='G03' and d.get('rule_updates')]
            self.assertTrue(corrected)
            self.assertEqual(corrected[0]['goal']['success_event'],'play_started')

    def test_generated_actions_obey_holdout_and_page_constraints(self):
        with tempfile.TemporaryDirectory() as out:
            run(ROOT,out)
            with open(out+'/actions.jsonl',encoding='utf-8') as f: actions=[json.loads(x) for x in f]
            with open(ROOT+'/data/catalogue.csv',encoding='utf-8-sig') as cf:
                cat={r['title_id']:r for r in __import__('csv').DictReader(cf)}
            arms=self.agent.arms
            self.assertTrue(any(a['type']=='push' for a in actions), 'replay should exercise push actions')
            self.assertTrue(any(a['type']=='whatsapp' for a in actions), 'replay should exercise WhatsApp actions')
            for a in actions:
                self.assertNotEqual(arms.get(a['user_id']),'holdout')
                if a['type']!='home_page':
                    continue
                self.assertLessEqual(len(a['rows']),6)
                seen=set()
                for row in a['rows']:
                    self.assertGreaterEqual(len(row['title_ids']),3)
                    self.assertLessEqual(len(row['title_ids']),10)
                    for tid in row['title_ids']:
                        self.assertEqual(cat[tid]['dialect'],a['dialect'])
                        self.assertNotIn(cat[tid]['content_slug'],seen)
                        seen.add(cat[tid]['content_slug'])


    def test_message_action_obeys_consent_quiet_hours_and_template(self):
        from datetime import timezone
        at=datetime.fromisoformat('2026-10-01T12:00:00+00:00')
        user=next(u for u,p in self.agent.profiles.items() if p.get('whatsapp_opt_in')=='true' and p.get('preferred_language')=='hin' and self.agent.arms.get(u)!='holdout')
        p=dict(self.agent.profiles[user])
        goal={'id':'G04'}
        event=self.trigger(user=user,event_id='wa-policy-test',at='2026-10-01T12:00:00Z',dialect=p.get('preferred_dialect','d1'))
        action,reason=self.agent.message_action(user,event,p,[],goal,event['app_dialect'],at)
        self.assertIsNotNone(action,reason)
        self.assertEqual(action['type'],'whatsapp')
        ok,error=self.agent.verify_message(action,p,[],at)
        self.assertTrue(ok,error)
        p['whatsapp_opt_in']='false'
        ok,error=self.agent.verify_message(action,p,[],at)
        self.assertFalse(ok)
        self.assertIn('consent',error)

    def test_message_time_is_deferred_out_of_quiet_hours(self):
        at=datetime.fromisoformat('2026-10-01T18:00:00+00:00')  # 23:30 IST
        scheduled=self.agent._message_send_time(at)
        self.assertEqual(scheduled.astimezone(__import__('datetime').timezone(__import__('datetime').timedelta(hours=5,minutes=30))).hour,8)

    def test_push_verifier_rejects_wrong_consent_and_holdout(self):
        at=datetime.fromisoformat('2026-10-01T12:00:00+00:00')
        user=next(u for u,p in self.agent.profiles.items() if self.agent.arms.get(u)!='holdout')
        p=dict(self.agent.profiles[user]);p['notifications_opt_in']='false'
        action={'action_id':'test-push','user_id':user,'type':'push','send_at':'2026-10-01T12:00:00Z','title_id':'T0001','title':'New release: Rava Baya','body':'Watch Rava Baya in d1.','deeplink':'ott://title/T0001','dialect':'d1'}
        ok,error=self.agent.verify_message(action,p,[],at)
        self.assertFalse(ok);self.assertIn('consent',error)
        holdout=next(u for u,a in self.agent.arms.items() if a=='holdout')
        action['user_id']=holdout
        p=dict(self.agent.profiles.get(holdout,{}));p['notifications_opt_in']='true'
        ok,error=self.agent.verify_message(action,p,[],at)
        self.assertFalse(ok);self.assertIn('holdout',error)


    def test_shared_push_whatsapp_daily_cap_is_enforced(self):
        at=datetime.fromisoformat('2026-10-01T12:00:00+00:00')
        user=next(u for u,p in self.agent.profiles.items() if self.agent.arms.get(u)!='holdout')
        self.agent.actions.append({'action_id':'prior-push','user_id':user,'type':'push','send_at':'2026-10-01T12:00:00Z'})
        p=dict(self.agent.profiles.get(user,{}));p['whatsapp_opt_in']='true';p['preferred_language']='hin'
        action={'action_id':'same-day-wa','user_id':user,'type':'whatsapp','send_at':'2026-10-01T13:00:00Z','template_id':'wa_recommend_title_v1','template_variables':{'title_name':'Example','dialect_name':'d1'},'language':'hin','dialect':'d1','title_id':'T0001'}
        ok,error=self.agent.verify_message(action,p,[],at)
        self.assertFalse(ok)
        self.assertIn('daily cap',error)

if __name__=='__main__': unittest.main(verbosity=2)
