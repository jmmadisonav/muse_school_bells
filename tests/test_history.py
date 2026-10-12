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
                     'result': 'failed', 'error': 'The USB audio adapter is not connected', 'detail': ''}
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


def test_corrupt_bytes_do_not_stop_startup_or_recording(tmp_path, log):
    path = tmp_path / 'history.jsonl'
    path.write_bytes(b'\xff\xfe not utf-8\n')
    h = history.History(str(path), log, clock=Clock(NOW))
    assert h.entries() == []
    h.record('page', 'x.wav')
    assert [e['sound'] for e in h.entries()] == ['x.wav']


def test_record_never_raises(tmp_path, log):
    h = history.History(str(tmp_path / 'no-such-dir' / 'history.jsonl'), log, clock=Clock(NOW))
    h.record('page', 'x.wav')
    assert log.errors


def test_setting_changes_are_logged_only_when_they_change(tmp_path, log):
    import bells
    h = history.History(str(tmp_path / 'history.jsonl'), log, clock=Clock(NOW))
    before = bells.default_state()
    h.record_setting_changes('page', before, dict(before, enabled=False, held_on='2026-10-12'), NOW)
    h.record_setting_changes('page', before, before, NOW)
    assert sorted(e['result'] for e in h.entries()) == ['bells_off', 'held']
    h.record_setting_changes('touch_point', dict(before, held_on='2026-10-12'), before, NOW)
    assert (h.entries()[0]['source'], h.entries()[0]['result']) == ('touch_point', 'resumed')


def test_bell_changes_log_on_and_off_for_existing_bells_only(tmp_path, log):
    h = history.History(str(tmp_path / 'history.jsonl'), log, clock=Clock(NOW))
    old = [{'id': 'a', 'label': 'Recess', 'time': '11:00', 'sound': 'r.wav', 'enabled': True},
           {'id': 'b', 'label': '', 'time': '12:00', 'sound': 'l.wav', 'enabled': False}]
    new = [dict(old[0], enabled=False), dict(old[1], enabled=True),
           {'id': 'c', 'label': 'New', 'time': '13:00', 'sound': 'n.wav', 'enabled': False}]
    h.record_bell_changes('page', old, new)
    assert sorted((e['label'], e['result']) for e in h.entries()) == [('12:00', 'enabled'), ('Recess', 'disabled')]
