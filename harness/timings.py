import time


def stage_timings(task, events, now=None):
    now = time.time() if now is None else now
    totals = {}
    active = None
    acceptance = None
    stops = {'question', 'blocked', 'pause_requested', 'paused', 'interrupted',
             'quota_stopped', 'quota_wait', 'rate_limited', 'task_deleted'}
    for event in events:
        kind, stamp, data = event['kind'], event['time'], event['data']
        if kind == 'started':
            active = None
        if kind == 'stage_started':
            stage = data.get('stage')
            active = (stage, stamp) if stage in {'plan', 'implement', 'check', 'review'} else None
        if active and (kind in stops or kind == 'checks_finished'
                       or kind == 'stage_finished' and data.get('stage') == active[0]):
            stage, start = active
            totals[stage] = totals.get(stage, 0) + max(0, stamp - start)
            active = None
        if kind == 'stage_finished' and data.get('next') == 'done':
            acceptance = stamp
        if acceptance is not None and kind in {'accepted', 'rejected', 'changes_requested', 'task_deleted'}:
            totals['acceptance'] = totals.get('acceptance', 0) + max(0, stamp - acceptance)
            acceptance = None
    if active and task['state'] == 'running' and task['stage'] == active[0]:
        totals[active[0]] = totals.get(active[0], 0) + max(0, now - active[1])
    if acceptance is not None and task['state'] == 'review' and task['stage'] == 'done':
        totals['acceptance'] = totals.get('acceptance', 0) + max(0, now - acceptance)
    return {stage: round(seconds, 1) for stage, seconds in totals.items()}
