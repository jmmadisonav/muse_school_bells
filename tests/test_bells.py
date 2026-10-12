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
    state = dict(bells.default_state(), enabled=enabled)
    state['schedules'] = [dict(state['schedules'][0], bells=bells.validate_bells(list(bell_list)))]
    return state


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
    assert store.set_settings({'master_volume': 50}) == {'enabled': True, 'master_volume': 50,
                                                         'time_format': '24h'}
    assert json.loads((tmp_path / 'bells.json').read_text())['master_volume'] == 50
    with pytest.raises(ValidationError):
        store.set_settings({'enabled': 'yes'})


def test_store_rejects_invalid_bells_without_changing_state(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    store.set_bells([bell(id='r1')])
    with pytest.raises(ValidationError):
        store.set_bells([bell(time='99:99')])
    assert [b['id'] for b in store.bells()] == ['r1']


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


def test_time_format_defaults_validates_and_merges(tmp_path, log):
    assert bells.default_state()['time_format'] == '24h'
    assert bells.validate_settings({'enabled': True, 'master_volume': 80})['time_format'] == '24h'
    with pytest.raises(ValidationError):
        bells.validate_settings({'enabled': True, 'master_volume': 80, 'time_format': '12'})
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    assert store.set_settings({'time_format': '12h'})['time_format'] == '12h'
    assert store.get()['master_volume'] == 80
    assert bells.Store(str(tmp_path / 'bells.json'), log).get()['time_format'] == '12h'


def test_bells_get_enabled_and_skip_on_defaults_and_validation():
    [b] = bells.validate_bells([bell()])
    assert b['enabled'] is True and b['skip_on'] is None
    [b] = bells.validate_bells([bell(enabled=False, skip_on='2026-10-13')])
    assert b['enabled'] is False and b['skip_on'] == '2026-10-13'
    for field, value in (('enabled', 'no'), ('skip_on', 'someday'), ('skip_on', 5)):
        with pytest.raises(ValidationError):
            bells.validate_bells([bell(**{field: value})])


def test_disabled_bell_does_not_ring_or_count_as_next():
    state = state_with(bell(id='off', enabled=False), bell(id='on', label='Lunch', time='13:00'))
    assert bells.due_bells(state, MON_1100, set()) == []
    assert bells.next_bell(state, datetime(2026, 10, 12, 10, 52))['id'] == 'on'
    assert bells.ring_target(state, datetime(2026, 10, 12, 10, 52))['id'] == 'on'


def test_skip_on_blocks_only_that_date():
    state = state_with(bell(id='r1', skip_on='2026-10-12'))
    assert bells.due_bells(state, MON_1100, set()) == []
    assert bells.skipped_bells(state, MON_1100, set())[0]['id'] == 'r1'
    assert bells.due_bells(state, datetime(2026, 10, 13, 11, 0), set())
    assert bells.skipped_bells(state, datetime(2026, 10, 13, 11, 0), set()) == []
    assert bells.next_bell(state, datetime(2026, 10, 12, 10, 52))['date'] == '2026-10-13'
    assert bells.ring_target(state, datetime(2026, 10, 12, 10, 52))['date'] == '2026-10-13'


def test_skipped_bells_ignores_disabled_held_and_rung():
    state = state_with(bell(id='r1', skip_on='2026-10-12'))
    assert bells.skipped_bells(state, MON_1100, {('r1', '2026-10-12')}) == []
    assert bells.skipped_bells(dict(state, held_on='2026-10-12'), MON_1100, set()) == []
    assert bells.skipped_bells(dict(state, enabled=False), MON_1100, set()) == []


def test_next_occurrence():
    b = bells.validate_bells([bell(days=['mon', 'wed'])])[0]
    assert bells.next_occurrence(b, datetime(2026, 10, 12, 10, 52)) == '2026-10-12'
    assert bells.next_occurrence(b, datetime(2026, 10, 12, 11, 0)) == '2026-10-14'
    assert bells.next_occurrence(b, datetime(2026, 10, 14, 12, 0)) == '2026-10-19'


def test_store_set_skip(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    store.set_bells([bell(id='r1')])
    assert store.set_skip('r1', True, datetime(2026, 10, 12, 11, 30))['skip_on'] == '2026-10-13'
    assert bells.Store(str(tmp_path / 'bells.json'), log).bells()[0]['skip_on'] == '2026-10-13'
    assert store.set_skip('r1', False, datetime(2026, 10, 12, 11, 30))['skip_on'] is None
    with pytest.raises(KeyError):
        store.set_skip('nope', True, MON_1100)


def test_skip_next_on_a_held_day_skips_the_next_real_ring(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    store.set_bells([bell(id='r1')])
    store.set_held(True, date(2026, 10, 12))
    assert store.set_skip('r1', True, datetime(2026, 10, 12, 9, 0))['skip_on'] == '2026-10-13'


# ---- Multiple schedules ----

SUMMER = {'from': '10-01', 'to': '04-30'}


def two_schedules(override=None):
    """Standard (default, 09:00) plus Summer (1 Oct to 30 Apr, 08:30), Monday to Friday."""
    state = bells.default_state()
    standard = dict(state['schedules'][0], bells=bells.validate_bells([bell(id='std', label='Start', time='09:00')]))
    summer = {'id': 'sum', 'name': 'Summer', 'default': False, 'range': dict(SUMMER),
              'bells': bells.validate_bells([bell(id='sm', label='Start', time='08:30')])}
    return dict(state, schedules=[standard, summer], override=override)


def test_default_state_has_one_default_schedule():
    [schedule] = bells.default_state()['schedules']
    assert (schedule['id'], schedule['name'], schedule['default'], schedule['range'], schedule['bells']) == \
        ('standard', 'Standard', True, None, [])
    assert bells.default_state()['override'] is None


def test_old_file_migrates_to_a_standard_schedule(tmp_path, log):
    path = tmp_path / 'bells.json'
    path.write_text(json.dumps({'enabled': True, 'master_volume': 70, 'bells': [bell(id='r1')]}))
    state = bells.load_state(str(path), log)
    [schedule] = state['schedules']
    assert (schedule['id'], schedule['name'], schedule['default']) == ('standard', 'Standard', True)
    assert [b['id'] for b in schedule['bells']] == ['r1']
    assert 'bells' not in state and state['master_volume'] == 70 and not log.errors


@pytest.mark.parametrize('day,inside', [('2026-10-01', True), ('2026-12-31', True), ('2026-01-01', True),
                                        ('2026-04-30', True), ('2026-05-01', False), ('2026-09-30', False)])
def test_in_range_wraps_past_new_year(day, inside):
    assert bells.in_range(SUMMER, date.fromisoformat(day)) is inside


def test_in_range_without_wrap_and_on_29_february():
    assert bells.in_range({'from': '02-01', 'to': '02-29'}, date(2028, 2, 29))
    assert not bells.in_range({'from': '03-01', 'to': '06-30'}, date(2026, 2, 28))


@pytest.mark.parametrize('value', [{'from': '13-01', 'to': '01-31'}, {'from': '02-30', 'to': '03-01'},
                                   {'from': '1-5', 'to': '02-01'}, {'from': '01-05'}, 'summer'])
def test_check_range_rejects_bad_ranges(value):
    with pytest.raises(ValidationError):
        bells.check_range(value)


def test_schedule_for_uses_ranges_then_default():
    state = two_schedules()
    assert bells.schedule_for(state, date(2026, 11, 2))['name'] == 'Summer'
    assert bells.schedule_for(state, date(2026, 6, 1))['name'] == 'Standard'


def test_due_and_next_bell_use_each_dates_schedule():
    state = two_schedules()
    assert [b['id'] for b in bells.due_bells(state, datetime(2026, 10, 12, 8, 30), set())] == ['sm']
    assert bells.due_bells(state, datetime(2026, 10, 12, 9, 0), set()) == []
    # Thursday 30 April is the last Summer day; the next bell is Friday 1 May from Standard.
    assert bells.next_bell(state, datetime(2026, 4, 30, 10, 0)) == {
        'id': 'std', 'label': 'Start', 'time': '09:00', 'date': '2026-05-01'}


def test_manual_pick_lasts_until_the_automatic_schedule_changes():
    state = two_schedules(override={'schedule': 'standard', 'from': '2026-04-20', 'until': '2026-05-01'})
    assert bells.schedule_for(state, date(2026, 4, 19))['name'] == 'Summer'
    assert bells.schedule_for(state, date(2026, 4, 20))['name'] == 'Standard'
    assert bells.schedule_for(state, date(2026, 4, 30))['name'] == 'Standard'
    assert bells.schedule_for(state, date(2026, 10, 5))['name'] == 'Summer'


def test_store_set_active_computes_until_and_clears_on_automatic_pick(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    summer = store.create_schedule('Summer')
    store.update_schedule(summer['id'], {'range': SUMMER})
    store.set_active(store.get()['schedules'][0]['id'], date(2026, 4, 20))
    assert store.get()['override'] == {'schedule': 'standard', 'from': '2026-04-20', 'until': '2026-05-01'}
    store.set_active(summer['id'], date(2026, 4, 21))  # Summer is the automatic schedule that day
    assert store.get()['override'] is None
    store.set_active(summer['id'], date(2026, 6, 1))
    assert store.get()['override']['until'] == '2026-10-01'
    store.set_active(None, date(2026, 6, 1))
    assert store.get()['override'] is None
    with pytest.raises(KeyError):
        store.set_active('nope', date(2026, 6, 1))


def test_store_create_duplicate_rename_and_delete(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    store.set_bells([bell(id='r1', skip_on='2026-10-13')])
    copy = store.create_schedule('Winter', copy_from='standard')
    assert copy['default'] is False and copy['range'] is None
    [copied] = copy['bells']
    assert copied['id'] != 'r1' and copied['label'] == 'Recess' and copied['skip_on'] is None
    with pytest.raises(ValidationError, match='already a schedule'):
        store.create_schedule('winter')
    with pytest.raises(ValidationError):
        store.create_schedule('  ')
    assert store.update_schedule(copy['id'], {'name': 'Cold'})['name'] == 'Cold'
    with pytest.raises(ValidationError, match='default'):
        store.delete_schedule('standard')
    store.delete_schedule(copy['id'])
    assert [s['id'] for s in store.get()['schedules']] == ['standard']
    with pytest.raises(KeyError):
        store.delete_schedule(copy['id'])
    assert bells.Store(str(tmp_path / 'bells.json'), log).get()['schedules'] == store.get()['schedules']


def test_store_ranges_overlap_and_default_rules(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    summer = store.create_schedule('Summer')
    winter = store.create_schedule('Winter')
    store.update_schedule(summer['id'], {'range': SUMMER})
    with pytest.raises(ValidationError, match='overlap'):
        store.update_schedule(winter['id'], {'range': {'from': '04-01', 'to': '09-30'}})
    store.update_schedule(winter['id'], {'range': {'from': '05-01', 'to': '09-30'}})
    with pytest.raises(ValidationError, match='default'):
        store.update_schedule('standard', {'range': {'from': '01-01', 'to': '01-31'}})
    made = store.update_schedule(summer['id'], {'default': True})
    assert made['default'] is True and made['range'] is None
    assert [s['default'] for s in store.get()['schedules']] == [False, True, False]


def test_changing_ranges_clears_a_manual_pick(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    summer = store.create_schedule('Summer')
    store.set_active(summer['id'], date(2026, 6, 1))
    store.update_schedule(summer['id'], {'range': SUMMER})
    assert store.get()['override'] is None


def test_bells_per_schedule_with_ids_unique_across_schedules(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    summer = store.create_schedule('Summer')
    store.set_bells([bell(id='r1')])
    clean = store.set_bells([bell(id='r1', label='Summer recess')], schedule_id=summer['id'])
    assert clean[0]['id'] != 'r1'  # ids stay unique across schedules
    # The clash rule applies only within a schedule.
    assert store.bells() and store.bells(summer['id'])[0]['time'] == '11:00'
    with pytest.raises(KeyError):
        store.set_bells([], schedule_id='nope')
    assert store.bells_using('recess.wav') == ['Recess (Standard)', 'Summer recess (Summer)']


def test_skip_next_finds_the_next_date_its_schedule_is_active(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    summer = store.create_schedule('Summer')
    store.update_schedule(summer['id'], {'range': SUMMER})
    [b] = store.set_bells([bell(label='Summer recess')], schedule_id=summer['id'])
    # After 11:00 on Thursday 30 April, Summer isn't active again until Thursday 1 October.
    assert store.set_skip(b['id'], True, datetime(2026, 4, 30, 12, 0))['skip_on'] == '2026-10-01'


def test_skip_next_on_a_schedule_never_in_use_is_refused(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    spare = store.create_schedule('Spare')  # no range and not the default, so it never applies
    [b] = store.set_bells([bell()], schedule_id=spare['id'])
    with pytest.raises(ValidationError, match='Spare'):
        store.set_skip(b['id'], True, MON_1100)
    assert store.bells(spare['id'])[0]['skip_on'] is None


def test_deleting_a_ranged_schedule_clears_a_manual_pick(tmp_path, log):
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    term = store.create_schedule('Term')
    summer = store.create_schedule('Summer')
    store.update_schedule(term['id'], {'range': {'from': '10-01', 'to': '12-01'}})
    store.set_active(summer['id'], date(2026, 10, 12))
    store.delete_schedule(term['id'])
    assert store.get()['override'] is None
