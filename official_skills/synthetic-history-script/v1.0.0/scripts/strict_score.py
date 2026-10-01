"""Pure scoring arithmetic. Config and a verified search reference are caller-owned."""
from math import isfinite

def bounded_quality(scores, weights, delivery_status, critical_error, caps):
    if set(scores)!=set(weights) or not scores:raise ValueError('rubric inventory mismatch')
    if any(type(v) is not int or v not in (0,1,2) for v in scores.values()):raise ValueError('score must be 0/1/2')
    if any(isinstance(w,bool) or not isinstance(w,(int,float)) or not isfinite(w) or w<=0 for w in weights.values()):raise ValueError('invalid weight')
    if delivery_status not in ('complete','partial','none_or_deferred'):raise ValueError('unknown delivery status')
    if set(caps)!={'complete','partial','none_or_deferred','critical_error'}:raise ValueError('cap fields')
    if any(type(v) not in (int,float) or not 0<=v<=100 for v in caps.values()):raise ValueError('cap value')
    if type(critical_error) is not bool:raise ValueError('critical_error must be bool')
    quality=100*sum(weights[k]*scores[k]/2 for k in scores)/sum(weights.values())
    ceiling=min(caps[delivery_status],caps['critical_error'] if critical_error else 100)
    return {'quality_before_caps':quality,'quality':min(quality,ceiling),'ceiling':ceiling,'delivery_status':delivery_status}

def efficiency_penalty(actual_searches, reference, policy):
    if type(actual_searches) is not int or actual_searches<0:raise ValueError('invalid call count')
    if reference.get('status')!='verified_replay':
        return {'status':'not_scored','penalty':None,'reason':'reference_not_verified'}
    required=('search_budget','frozen_before_target_run','same_snapshot_and_tool_config','necessary_facts_verified')
    if any(k not in reference for k in required):raise ValueError('incomplete reference certificate')
    if type(reference['search_budget']) is not int or reference['search_budget']<0:raise ValueError('invalid reference budget')
    if any(reference[k] is not True for k in required[1:]):raise ValueError('ineligible reference')
    if set(policy)!={'tolerance','tiers','cap'}:raise ValueError('efficiency policy fields')
    if type(policy['tolerance']) is not int or policy['tolerance']<0:raise ValueError('tolerance')
    remaining=max(0,actual_searches-reference['search_budget']-policy['tolerance']);excess=remaining;penalty=0
    for tier in policy['tiers']:
        if set(tier)!={'width','points_per_call'}:raise ValueError('tier fields')
        width=tier['width'];points=tier['points_per_call']
        if width is not None and (type(width) is not int or width<1):raise ValueError('tier width')
        if type(points) not in (int,float) or points<0:raise ValueError('tier points')
        used=remaining if width is None else min(remaining,width)
        penalty+=used*points;remaining-=used
    if remaining:raise ValueError('tiers do not cover all excess calls')
    return {'status':'scored','penalty':min(policy['cap'],penalty),'excess_after_tolerance':excess}

def final_score(quality, efficiency):
    return None if efficiency['penalty'] is None else max(0,quality-efficiency['penalty'])
