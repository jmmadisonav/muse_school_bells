import inspect
import types
from datetime import datetime

import pytest

import bells
import touchpoints
from audio import AudioError
from helpers import FakeExport, FakePlayer, make_wav

NOW = datetime(2026, 10, 12, 10, 52, 7)  # Monday


@pytest.fixture
def tp(tmp_path, log):
    sounds_dir = tmp_path / 'sounds'
    sounds_dir.mkdir()
    (sounds_dir / 'recess.wav').write_bytes(make_wav(0.1))
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    store.set_bells([{'id': 'r1', 'label': 'Recess', 'time': '11:00',
                      'days': ['mon', 'tue', 'wed', 'thu', 'fri'], 'sound': 'recess.wav', 'volume': 50}])
    export, player = FakeExport(), FakePlayer()
    points = touchpoints.TouchPoints(export, store, player, str(sounds_dir), log, clock=lambda: NOW)
    return types.SimpleNamespace(tp=points, h=points.handlers(), export=export, player=player,
                                 store=store, log=log)


def test_handler_arities_match_muse_dispatch(tp):
    arity = {name: len(inspect.getfullargspec(f)[0]) for name, f in tp.h.items()}
    assert arity == {'set_enabled': 1, 'set_master_volume': 1, 'set_held': 1,
                     'play_sound': 1, 'stop_sound': 0}


def test_publish_sends_everything_once_then_only_changes(tp):
    tp.tp.publish()
    assert dict(tp.export.updates) == {'enabled': True, 'master_volume': 80, 'held': False, 'playing': '',
                                       'next_bell': 'Mon 11:00 Recess', 'last_error': ''}
    tp.export.updates.clear()
    tp.tp.publish()
    assert tp.export.updates == []
    tp.store.set_settings({'master_volume': 40})  # a change made from the web page
    tp.tp.publish()
    assert tp.export.updates == [('master_volume', 40)]


@pytest.mark.parametrize('value,expected', [(False, False), (0, False), ('false', False),
                                            ('TRUE', True), (1, True)])
def test_set_enabled_accepts_loose_values(tp, value, expected):
    tp.h['set_enabled'](value)
    assert tp.store.get()['enabled'] is expected
    assert ('enabled', expected) in tp.export.updates


@pytest.mark.parametrize('value', ['maybe', 2, None])
def test_set_enabled_rejects_bad_value_without_raising(tp, value):
    tp.h['set_enabled'](value)
    assert tp.store.get()['enabled'] is True
    assert 'enabled' in tp.tp.values()['last_error']
    assert tp.log.errors


@pytest.mark.parametrize('value,expected', [(30, 30), ('45', 45), (60.0, 60)])
def test_set_master_volume_accepts_whole_numbers(tp, value, expected):
    tp.h['set_master_volume'](value)
    assert tp.store.get()['master_volume'] == expected


@pytest.mark.parametrize('value', [101, -1, '1e3', 'loud', True, 12.5])
def test_set_master_volume_rejects_bad_value_without_raising(tp, value):
    tp.h['set_master_volume'](value)
    assert tp.store.get()['master_volume'] == 80
    assert 'master_volume' in tp.tp.values()['last_error']


@pytest.mark.parametrize('args', [{'sound': 'recess.wav'}, 'recess.wav', ['recess.wav']])
def test_play_accepts_map_string_or_list(tp, args):
    tp.h['play_sound'](args)
    [(path, gain)] = tp.player.plays
    assert path.endswith('recess.wav')
    assert gain == pytest.approx(0.8)
    assert ('playing', 'recess.wav') in tp.export.updates


def test_play_unknown_or_unsafe_sound_sets_last_error(tp):
    tp.h['play_sound']({'sound': '../bells.json'})
    assert 'does not exist' in tp.tp.values()['last_error']
    tp.h['play_sound']({})
    assert 'needs a sound name' in tp.tp.values()['last_error']
    assert tp.player.plays == []


def test_play_adapter_failure_sets_last_error(tp):
    tp.player.fail = AudioError('The USB audio adapter is not connected')
    tp.h['play_sound']('recess.wav')
    assert tp.tp.values()['last_error'] == 'play failed: The USB audio adapter is not connected'


def test_stop(tp):
    tp.h['stop_sound']()
    assert tp.player.stops == 1


def test_bell_rang_dispatches_event(tp):
    tp.tp.bell_rang(tp.store.get()['bells'][0])
    assert tp.export.dispatches == [('bell_rang', {'id': 'r1', 'label': 'Recess', 'time': '11:00',
                                                   'sound': 'recess.wav'})]


def test_error_logs_and_publishes(tp):
    tp.tp.error('Bell "Recess" at 11:00: sound recess.wav is missing')
    assert tp.log.errors == ['Bell "Recess" at 11:00: sound recess.wav is missing']
    assert ('last_error', 'Bell "Recess" at 11:00: sound recess.wav is missing') in tp.export.updates


def test_next_bell_is_empty_when_disabled(tp):
    tp.store.set_settings({'enabled': False})
    assert tp.tp.values()['next_bell'] == ''


def test_describe_next_omits_empty_label():
    assert touchpoints.describe_next({'id': 'x', 'label': '', 'time': '08:45',
                                      'date': '2026-10-18'}) == 'Sun 08:45'
    assert touchpoints.describe_next(None) == ''


def test_start_publishes_then_goes_online(tp):
    tp.tp.start()
    assert tp.export.calls[:7] == ['update'] * 6 + ['online']


def test_set_held_holds_today_and_publishes(tp):
    tp.h['set_held']('true')
    assert tp.store.get()['held_on'] == '2026-10-12'
    assert ('held', True) in tp.export.updates
    assert tp.tp.values()['next_bell'] == 'Tue 11:00 Recess'
    tp.h['set_held']('maybe')
    assert 'held' in tp.tp.values()['last_error']
    tp.h['set_held'](False)
    assert tp.store.get()['held_on'] is None
