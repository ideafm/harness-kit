import unittest

from harness.timings import stage_timings


def event(kind, stamp, **data):
    return {'kind': kind, 'time': stamp, 'data': data}


class TimingTests(unittest.TestCase):
    def test_attempts_sum_and_waits_are_excluded(self):
        events = [event('stage_started', 10, stage='implement'), event('question', 15),
                  event('stage_started', 100, stage='implement'), event('stage_finished', 112, stage='implement', next='check'),
                  event('stage_started', 113, stage='check'), event('checks_finished', 118)]
        self.assertEqual(stage_timings({'state': 'review', 'stage': 'done'}, events, now=200),
                         {'implement': 17, 'check': 5})

    def test_running_time_and_paused_time(self):
        events = [event('stage_started', 10, stage='plan')]
        self.assertEqual(stage_timings({'state': 'running', 'stage': 'plan'}, events, now=25), {'plan': 15})
        self.assertEqual(stage_timings({'state': 'paused', 'stage': 'plan'}, events, now=25), {})
        events.append(event('pause_requested', 14))
        self.assertEqual(stage_timings({'state': 'paused', 'stage': 'plan'}, events, now=200), {'plan': 4})

    def test_acceptance_wait_stops_at_decision(self):
        events = [event('stage_started', 10, stage='review'), event('stage_finished', 20, stage='review', next='done')]
        self.assertEqual(stage_timings({'state': 'review', 'stage': 'done'}, events, now=50), {'review': 10, 'acceptance': 30})
        events.append(event('accepted', 35))
        self.assertEqual(stage_timings({'state': 'accepted', 'stage': 'done'}, events, now=100), {'review': 10, 'acceptance': 15})

    def test_restart_does_not_include_unobserved_downtime(self):
        events = [event('stage_started', 10, stage='plan'), event('started', 100),
                  event('stage_started', 105, stage='plan'), event('stage_finished', 115, stage='plan')]
        self.assertEqual(stage_timings({'state': 'review', 'stage': 'done'}, events), {'plan': 10})
