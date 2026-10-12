import json
from datetime import datetime, timedelta

import history

NOW = datetime(2026, 10, 12, 11, 0, 5)


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def test_record_and_entries_newest_first(tmp_path, log):
    h = history.History(str(tmp_path / 'history.jsonl'), log, clock=Clock(NOW))
    h.record('scheduled', 'recess.wav', label='Recess')
    h.record('page', 'x.wav', result='failed', error='The USB audio adapter is not connected')
    first, second = h.entries()
    assert first == {'time': '2026-10-12T11:00:05', 'source': 'page', 'label': '', 'sound': 'x.wav',
                     'result': 'failed', 'error': 'The USB audio adapter is not connected'}
    assert second['source'] == 'scheduled' and second['label'] == 'Recess' and second['result'] == 'played'


def test_entries_survive_a_restart_and_respect_limit(tmp_path, log):
    path = str(tmp_path / 'history.jsonl')
    h = history.History(path, log, clock=Clock(NOW))
    for n in range(5):
        h.record('page', '%d.wav' % n)
    again = history.History(path, log, clock=Clock(NOW))
    assert [e['sound'] for e in again.entries(limit=2)] == ['4.wav', '3.wav']


def test_old_entries_are_pruned_at_startup_and_on_a_new_day(tmp_path, log):
    path = tmp_path / 'history.jsonl'
    old = {'time': (NOW - timedelta(days=31)).isoformat(timespec='seconds'), 'source': 'page',
           'label': '', 'sound': 'old.wav', 'result': 'played', 'error': ''}
    path.write_text(json.dumps(old) + '\nnot json\n')
    clock = Clock(NOW)
    h = history.History(str(path), log, clock=clock)
    assert h.entries() == []
    h.record('page', 'today.wav')
    clock.now = NOW + timedelta(days=31)
    h.record('page', 'later.wav')
    assert [e['sound'] for e in h.entries()] == ['later.wav']
    assert 'today.wav' not in path.read_text()


def test_missing_file_is_empty(tmp_path, log):
    assert history.History(str(tmp_path / 'none.jsonl'), log).entries() == []
