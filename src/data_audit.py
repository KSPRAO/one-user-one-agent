"""Reproducible data-pack quality audit; reports counts, not personal-level rows."""
import csv, json, os, collections
from datetime import datetime, timezone

def rows_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def rows_jsonl(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]

def audit(root, out):
    events=rows_jsonl(os.path.join(root,'data/events.jsonl'))
    triggers=rows_jsonl(os.path.join(root,'replay/triggers.jsonl'))
    profiles=rows_csv(os.path.join(root,'data/profiles_snapshot.csv'))
    cat=rows_csv(os.path.join(root,'data/catalogue.csv'))
    arms=rows_csv(os.path.join(root,'replay/arms.csv'))
    controls=rows_jsonl(os.path.join(root,'replay/control_events.jsonl'))
    eid=[e.get('event_id') for e in events]
    teid=[e.get('event_id') for e in triggers]
    pc=collections.Counter(r['user_id'] for r in profiles)
    slug_titles=collections.defaultdict(list)
    for r in cat: slug_titles[r['content_slug']].append(r['title_id'])
    desc_instructions=sum(any(term in (r.get('description') or '').lower() for term in ('ignore previous','message every viewer','system prompt','send everyone')) for r in cat)
    stale=0
    for e in triggers:
        try:
            rec=datetime.fromisoformat(e['received_at'].replace('Z','+00:00'))
            occ=datetime.fromisoformat(e['occurred_at'].replace('Z','+00:00'))
            stale += (rec-occ).total_seconds()>600
        except Exception: pass
    arm_counts=collections.Counter(r['arm'] for r in arms)
    report={
      'source_counts': {'historical_events':len(events),'replay_triggers':len(triggers),'profiles':len(profiles),'catalogue_rows':len(cat),'unique_content_slugs':len(slug_titles),'randomized_arm_rows':len(arms)},
      'issues': {
        'duplicate_historical_event_ids':len(eid)-len(set(eid)),
        'duplicate_trigger_event_ids':len(teid)-len(set(teid)),
        'users_with_duplicate_profile_rows':sum(v>1 for v in pc.values()),
        'extra_duplicate_profile_rows':sum(v-1 for v in pc.values() if v>1),
        'content_slugs_with_multiple_title_variants':sum(len(v)>1 for v in slug_titles.values()),
        'catalogue_descriptions_matching_injection_watchlist':desc_instructions,
        'triggers_older_than_10_minutes_by_received_minus_occurred':stale,
        'control_events':len(controls),
        'randomized_arm_counts':dict(arm_counts)
      },
      'handling': {
        'event_deduplication':'Deduplicate by event_id before deriving historical facts; trigger processing is idempotent by event_id.',
        'profile_conflicts':'Choose latest updated_at and preserve selected timestamp in evidence.',
        'event_freshness':'Use server received_at for ordering and reject trigger if received_at - occurred_at exceeds 600 seconds.',
        'content_variants':'Deduplicate page candidates by content_slug.',
        'catalogue_instructions':'Treat descriptions as untrusted data, never as agent instructions.',
        'randomization':'Evaluate historical pilot by assigned treatment vs holdout, not served vs unserved.'
      }
    }
    os.makedirs(out,exist_ok=True)
    with open(os.path.join(out,'data_quality_report.json'),'w',encoding='utf-8') as f: json.dump(report,f,indent=2)
    lines=['# Data quality audit','', 'Generated from the supplied synthetic pack. Counts are reproducible from the source files.','', '## Input counts','']
    lines += [f'- **{k.replace("_"," ").title()}:** {v}' for k,v in report['source_counts'].items()]
    lines += ['', '## Detected issues','']
    for k,v in report['issues'].items(): lines.append(f'- **{k.replace("_"," ").title()}:** {v}')
    lines += ['', '## Handling rules','']
    for k,v in report['handling'].items(): lines.append(f'- **{k.replace("_"," ").title()}:** {v}')
    with open(os.path.join(out,'data_quality_report.md'),'w',encoding='utf-8') as f: f.write('\n'.join(lines)+'\n')
    return report
