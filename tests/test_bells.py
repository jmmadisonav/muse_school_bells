import json
from datetime import date, datetime

import pytest

import bells
from bells import ValidationError

MON_1100 = datetime(2026, 10, 12, 11, 0, 30)  # 2026-10-12 is a Monday


def bell(**changes):
    b = {'label': 'Recess', 'time': '11:00', 'days': ['mon', 'tue', 'wed', 'thu', 'fri'],
         'sound': 'recess.wav', 'volume': 90}
    b.update(changes)
    return b


def state_with(*bell_list, enabled=True):
    return dict(bells.default_state(), enabled=enabled, bells=bells.validate_bells(list(bell_list)))


def test_validate_assigns_ids_sorts_and_orders_days():
    out = bells.validate_bells([bell(days=['fri', 'mon']), bell(label='Start', time='08:45')])
    assert [b['time'] for b in out] == ['08:45', '11:00']
    assert out[1]['days'] == ['mon', 'fri']
    assert all(len(b['id']) == 8 for b in out)
    assert out[0]['id'] != out[1]['id']


def test_validate_keeps_valid_id_and_replaces_duplicate():
    out = bells.validate_bells([bell(id='abc'), bell(id='abc', time='12:00')])
    assert out[0]['id'] == 'abc'
    assert out[1]['id'] != 'abc'


@pytest.mark.parametrize('field,value', [
    ('time', '24:00'), ('time', '8:45'), ('time', None),
    ('days', []), ('days', ['mon', 'xyz']), ('days', 'mon'),
    ('volume', 101), ('volume', -1), ('volume', True), ('volume', '50'),
    ('sound', ''), ('sound', None), ('label', 5),
])
def test_validate_rejects_bad_fields(field, value):
    with pytest.raises(ValidationError):
        bells.validate_bells([bell(**{field: value})])


def test_validate_rejects_clash_and_names_both_bells():
    with pytest.raises(ValidationError, match='"Recess" and "Lunch" both ring at 11:00 on Wed'):
        bells.validate_bells([bell(), bell(label='Lunch', days=['wed'])])


def test_validate_allows_same_time_on_different_days():
    assert len(bells.validate_bells([bell(days=['mon']), bell(label='Lunch', days=['tue'])])) == 2


def test_validate_checks_sound_exists_when_asked():
    with pytest.raises(ValidationError, match='recess.wav'):
        bells.validate_bells([bell()], sound_exists=lambda name: False)


def test_due_bell_rings_in_its_minute():
    state = state_with(bell(id='r1'))
    assert [b['id'] for b in bells.due_bells(state, MON_1100, set())] == ['r1']
    assert bells.due_bells(state, datetime(2026, 10, 12, 11, 1), set()) == []


def test_sunday_maps_to_sun():
    state = state_with(bell(id='s1', days=['sun']))
    assert bells.due_bells(state, datetime(2026, 10, 11, 11, 0), set())
    assert not bells.due_bells(state, datetime(2026, 10, 12, 11, 0), set())


def test_due_skips_when_disabled_or_already_rung():
    assert bells.due_bells(state_with(bell(id='r1'), enabled=False), MON_1100, set()) == []
    assert bells.due_bells(state_with(bell(id='r1')), MON_1100, {('r1', '2026-10-12')}) == []


def test_midnight_bell_rings_again_next_day():
    state = state_with(bell(id='m1', time='00:00', days=list(bells.DAYS)))
    rung = {('m1', '2026-10-12')}
    assert bells.due_bells(state, datetime(2026, 10, 13, 0, 0, 5), rung)


def test_next_bell_later_today_then_next_school_day():
    state = state_with(bell(id='st', label='Start', time='08:45'), bell(id='re'))
    assert bells.next_bell(state, datetime(2026, 10, 12, 10, 52)) == {
        'id': 're', 'label': 'Recess', 'time': '11:00', 'date': '2026-10-12'}
    friday_after_last = datetime(2026, 10, 16, 11, 0)
    assert bells.next_bell(state, friday_after_last)['date'] == '2026-10-19'


def test_next_bell_wraps_to_same_weekday_next_week_and_none_when_disabled():
    state = state_with(bell(id='a1', time='08:45', days=['mon']))
    assert bells.next_bell(state, datetime(2026, 10, 12, 9, 0))['date'] == '2026-10-19'
    assert bells.next_bell(state_with(bell(), enabled=False), MON_1100) is None


def test_save_and_load_round_trip(tmp_path, log):
    path = str(tmp_path / 'bells.json')
    state = state_with(bell(id='r1'))
    bells.save_state(path, state)
    assert bells.load_state(path, log) == state
    assert not (tmp_path / 'bells.json.tmp').exists()


def test_load_missing_file_gives_default(tmp_path, log):
    assert bells.load_state(str(tmp_path / 'none.json'), log) == bells.default_state()


def test_load_corrupt_file_keeps_bad_copy(tmp_path, log):
    path = tmp_path / 'bells.json'
    path.write_text('{nope')
    assert bells.load_state(str(path), log) == bells.default_state()
    assert (tmp_path / 'bells.json.bad').read_text() == '{nope'
    assert log.errors


def test_store_set_settings_merges_partial_update(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    assert store.set_settings({'master_volume': 50}) == {'enabled': True, 'master_volume': 50}
    assert json.loads((tmp_path / 'bells.json').read_text())['master_volume'] == 50
    with pytest.raises(ValidationError):
        store.set_settings({'enabled': 'yes'})


def test_store_rejects_invalid_bells_without_changing_state(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    store.set_bells([bell(id='r1')])
    with pytest.raises(ValidationError):
        store.set_bells([bell(time='99:99')])
    assert [b['id'] for b in store.get()['bells']] == ['r1']


def test_store_bells_using(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    store.set_bells([bell(), bell(label='', time='12:00'), bell(label='Lunch', time='13:00', sound='x.wav')])
    assert store.bells_using('recess.wav') == ['Recess', '12:00']


def test_hold_stops_due_bells_on_its_date_only():
    state = dict(state_with(bell(id='r1')), held_on='2026-10-12')
    assert bells.due_bells(state, MON_1100, set()) == []
    assert bells.due_bells(state, datetime(2026, 10, 13, 11, 0), set())


def test_next_bell_skips_held_day_and_ring_target_ignores_hold_and_switch():
    state = dict(state_with(bell(id='re')), held_on='2026-10-12')
    morning = datetime(2026, 10, 12, 10, 52)
    assert bells.next_bell(state, morning)['date'] == '2026-10-13'
    assert bells.ring_target(state, morning)['date'] == '2026-10-12'
    assert bells.ring_target(dict(state, enabled=False), morning)['id'] == 're'
    assert bells.ring_target(state_with(), MON_1100) is None


def test_store_set_held_persists_and_validates(tmp_path, log):
    path = tmp_path / 'bells.json'
    store = bells.Store(str(path), log)
    store.set_held(True, date(2026, 10, 12))
    assert store.get()['held_on'] == '2026-10-12'
    assert bells.Store(str(path), log).get()['held_on'] == '2026-10-12'
    store.set_held(False, date(2026, 10, 12))
    assert store.get()['held_on'] is None
    with pytest.raises(ValidationError):
        store.set_held('yes', date(2026, 10, 12))


def test_load_ignores_unreadable_held_on(tmp_path, log):
    path = tmp_path / 'bells.json'
    path.write_text(json.dumps(dict(bells.default_state(), held_on='someday')))
    assert bells.load_state(str(path), log)['held_on'] is None
    assert not log.errors
