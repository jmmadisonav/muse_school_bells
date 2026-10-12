from datetime import datetime

import pytest

import bells
import scheduler
from audio import AudioError
from helpers import FakePlayer

WEEKDAYS = ['mon', 'tue', 'wed', 'thu', 'fri']


def at(day, hour, minute, second=0):
    return datetime(2026, 10, day, hour, minute, second)  # 2026-10-12 is a Monday


@pytest.fixture
def env(tmp_path, log):
    sounds_dir = tmp_path / 'sounds'
    sounds_dir.mkdir()
    (sounds_dir / 'recess.wav').write_bytes(b'x')
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    store.set_settings({'master_volume': 80})
    store.set_bells([{'id': 'r1', 'label': 'Recess', 'time': '11:00', 'days': WEEKDAYS,
                      'sound': 'recess.wav', 'volume': 50}])
    player = FakePlayer()
    sched = scheduler.Scheduler(store, player, str(sounds_dir), log)
    return sched, store, player, sounds_dir


def test_rings_once_in_its_minute_at_combined_gain(env):
    sched, _, player, sounds_dir = env
    assert sched.tick(at(12, 11, 0, 0)) == ['r1']
    assert sched.tick(at(12, 11, 0, 30)) == []
    [(path, gain)] = player.plays
    assert path == str(sounds_dir / 'recess.wav')
    assert gain == pytest.approx(0.4)


def test_prime_blocks_the_startup_minute_only(env):
    sched, _, player, _ = env
    sched.prime(at(12, 11, 0, 10))
    sched.tick(at(12, 11, 0, 20))
    assert player.plays == []
    sched.tick(at(13, 11, 0, 5))
    assert len(player.plays) == 1


def test_disabled_rings_nothing(env):
    sched, store, player, _ = env
    store.set_settings({'enabled': False})
    sched.tick(at(12, 11, 0))
    assert player.plays == []


def test_missing_sound_logs_once_and_skips(env, log):
    sched, _, player, sounds_dir = env
    (sounds_dir / 'recess.wav').unlink()
    sched.tick(at(12, 11, 0, 0))
    sched.tick(at(12, 11, 0, 1))
    assert player.plays == []
    assert len(log.errors) == 1 and 'missing' in log.errors[0]


def test_player_failure_does_not_stop_later_bells(env, log):
    sched, _, player, _ = env
    player.fail = AudioError('The USB audio adapter is not connected')
    sched.tick(at(12, 11, 0))
    assert 'not connected' in log.errors[0]
    player.fail = None
    sched.tick(at(13, 11, 0))
    assert len(player.plays) == 1


def test_clock_jumping_back_does_not_ring_twice(env):
    sched, _, player, _ = env
    sched.tick(at(12, 11, 0, 5))
    sched.tick(at(12, 10, 59, 50))
    sched.tick(at(12, 11, 0, 10))
    assert len(player.plays) == 1


def test_midnight_bell_rings_on_consecutive_days(env):
    sched, store, player, _ = env
    store.set_bells([{'id': 'm1', 'label': 'Midnight', 'time': '00:00', 'days': list(bells.DAYS),
                      'sound': 'recess.wav', 'volume': 100}])
    sched.tick(at(12, 0, 0))
    sched.tick(at(13, 0, 0))
    assert len(player.plays) == 2


class RecordingEvents:
    def __init__(self):
        self.rang = []
        self.errors = []

    def bell_rang(self, bell):
        self.rang.append(bell['id'])

    def error(self, message):
        self.errors.append(message)


def test_events_receive_rings_and_errors_instead_of_log(env, log):
    _, store, player, sounds_dir = env
    events = RecordingEvents()
    sched = scheduler.Scheduler(store, player, str(sounds_dir), log, events=events)
    sched.tick(at(12, 11, 0))
    assert events.rang == ['r1']
    player.fail = AudioError('The USB audio adapter is not connected')
    sched.tick(at(13, 11, 0))
    (sounds_dir / 'recess.wav').unlink()
    sched.tick(at(14, 11, 0))
    assert events.rang == ['r1']
    assert 'not connected' in events.errors[0] and 'missing' in events.errors[1]
    assert log.errors == []
