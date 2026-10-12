"""Bell schedules: validation, storage, and due-bell logic. No USB or web code."""
import copy
import json
import os
import re
import secrets
import threading
from datetime import date, timedelta

DAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')  # index matches datetime.weekday()
TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
ID_RE = re.compile(r'^[a-z0-9]{1,16}$')
MONTH_DAY_RE = re.compile(r'^\d\d-\d\d$')
MAX_LABEL = 60
MAX_SCHEDULE_NAME = 40
DEFAULT_ID = 'standard'  # id of the schedule created for a new or migrated bells.json


class ValidationError(ValueError):
    """A problem staff can fix. The message appears on the page."""


def _schedule(schedule_id, name, default=False, date_range=None, bell_list=None):
    return {'id': schedule_id, 'name': name, 'default': default, 'range': date_range,
            'bells': bell_list or []}


def default_state():
    return {'enabled': True, 'master_volume': 80, 'time_format': '24h', 'held_on': None,
            'schedules': [_schedule(DEFAULT_ID, 'Standard', default=True)], 'override': None}


def check_volume(value, what):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise ValidationError('%s must be a whole number from 0 to 100' % what)
    return value


def validate_settings(data):
    if not isinstance(data, dict):
        raise ValidationError('Settings must be a JSON object')
    if not isinstance(data.get('enabled'), bool):
        raise ValidationError('enabled must be true or false')
    time_format = data.get('time_format', '24h')
    if time_format not in ('12h', '24h'):
        raise ValidationError('time_format must be "12h" or "24h"')
    return {'enabled': data['enabled'],
            'master_volume': check_volume(data.get('master_volume'), 'Master volume'),
            'time_format': time_format}


def _new_id(taken):
    while True:
        candidate = secrets.token_hex(4)
        if candidate not in taken:
            return candidate


def validate_bells(bells, sound_exists=None, taken=()):
    """Return a clean, time-sorted copy of one schedule's bell list, or raise ValidationError.

    Pass sound_exists to also require that each bell's sound file exists. Ids in taken
    (bells in other schedules) are replaced, so bell ids stay unique across schedules.
    """
    if not isinstance(bells, list):
        raise ValidationError('bells must be a list')
    result, ids, slots = [], set(), {}
    for raw in bells:
        if not isinstance(raw, dict):
            raise ValidationError('Each bell must be a JSON object')
        label = raw.get('label', '')
        if not isinstance(label, str):
            raise ValidationError('Bell labels must be text')
        label = label.strip()[:MAX_LABEL]
        time = raw.get('time')
        if not isinstance(time, str) or not TIME_RE.match(time):
            raise ValidationError('Bell "%s": time must be 24-hour HH:MM' % (label or '?'))
        name = label or time
        days = raw.get('days')
        if not isinstance(days, list) or not days or any(d not in DAYS for d in days):
            raise ValidationError('Bell "%s": choose at least one weekday' % name)
        days = [d for d in DAYS if d in days]
        sound = raw.get('sound')
        if not isinstance(sound, str) or not sound:
            raise ValidationError('Bell "%s": choose a sound' % name)
        if sound_exists is not None and not sound_exists(sound):
            raise ValidationError('Bell "%s": sound %s does not exist' % (name, sound))
        volume = check_volume(raw.get('volume'), 'Bell "%s" volume' % name)
        enabled = raw.get('enabled', True)
        if not isinstance(enabled, bool):
            raise ValidationError('Bell "%s": enabled must be true or false' % name)
        skip_on = raw.get('skip_on')
        if skip_on is not None and not _is_iso_date(skip_on):
            raise ValidationError('Bell "%s": skip_on must be a date' % name)
        bell_id = raw.get('id')
        if not isinstance(bell_id, str) or not ID_RE.match(bell_id) or bell_id in ids or bell_id in taken:
            bell_id = _new_id(ids | set(taken))
        ids.add(bell_id)
        for day in days:
            other = slots.get((time, day))
            if other is not None:
                raise ValidationError('Bells "%s" and "%s" both ring at %s on %s'
                                      % (other, name, time, day.capitalize()))
            slots[(time, day)] = name
        result.append({'id': bell_id, 'label': label, 'time': time, 'days': days,
                       'sound': sound, 'volume': volume, 'enabled': enabled, 'skip_on': skip_on})
    result.sort(key=lambda b: (b['time'], b['label']))
    return result


# ---- Date ranges ----

def check_range(value):
    """Return a clean yearly range {'from': 'MM-DD', 'to': 'MM-DD'}, or None for no range."""
    if value is None:
        return None
    if not isinstance(value, dict) or not all(
            isinstance(value.get(k), str) and MONTH_DAY_RE.match(value[k]) for k in ('from', 'to')):
        raise ValidationError('A date range needs a from and a to date, as MM-DD')
    for key in ('from', 'to'):
        try:
            date.fromisoformat('2024-' + value[key])  # 2024 is a leap year, so 02-29 is allowed
        except ValueError:
            raise ValidationError('%s is not a real day of the year' % value[key])
    return {'from': value['from'], 'to': value['to']}


def in_range(date_range, day):
    """True if day falls in the yearly range. A range whose from is after its to wraps past New Year."""
    month_day = day.strftime('%m-%d')
    if date_range['from'] <= date_range['to']:
        return date_range['from'] <= month_day <= date_range['to']
    return month_day >= date_range['from'] or month_day <= date_range['to']


def _range_days(date_range):
    start = date(2024, 1, 1)
    return {start + timedelta(days=n) for n in range(366) if in_range(date_range, start + timedelta(days=n))}


def _check_overlaps(schedules):
    ranged = [(s, _range_days(s['range'])) for s in schedules if s['range']]
    for i, (first, first_days) in enumerate(ranged):
        for second, second_days in ranged[i + 1:]:
            common = first_days & second_days
            if common:
                day = min(common)
                raise ValidationError('The date ranges of %s and %s overlap on %d %s'
                                      % (first['name'], second['name'], day.day, day.strftime('%B')))


def _clean_name(name, others):
    if not isinstance(name, str) or not name.strip():
        raise ValidationError('Give the schedule a name.')
    name = name.strip()[:MAX_SCHEDULE_NAME]
    if name.lower() in (other.lower() for other in others):
        raise ValidationError('There is already a schedule called %s.' % name)
    return name


def validate_schedules(raw_list):
    """Return a clean schedule list loaded from bells.json, or raise ValidationError."""
    if not isinstance(raw_list, list) or not raw_list:
        raise ValidationError('There must be at least one schedule')
    result, ids, bell_ids = [], set(), set()
    for raw in raw_list:
        if not isinstance(raw, dict):
            raise ValidationError('Each schedule must be a JSON object')
        name = _clean_name(raw.get('name'), [s['name'] for s in result])
        schedule_id = raw.get('id')
        if not isinstance(schedule_id, str) or not ID_RE.match(schedule_id) or schedule_id in ids:
            schedule_id = _new_id(ids)
        ids.add(schedule_id)
        default = raw.get('default') is True and not any(s['default'] for s in result)
        date_range = None if default else check_range(raw.get('range'))
        bell_list = validate_bells(raw.get('bells', []), taken=bell_ids)
        bell_ids.update(b['id'] for b in bell_list)
        result.append(_schedule(schedule_id, name, default, date_range, bell_list))
    if not any(s['default'] for s in result):
        result[0]['default'] = True
        result[0]['range'] = None
    _check_overlaps(result)
    return result


def _check_override(value, schedules):
    if not isinstance(value, dict) or not any(s['id'] == value.get('schedule') for s in schedules):
        return None
    if not _is_iso_date(value.get('from')) or not (value.get('until') is None or _is_iso_date(value.get('until'))):
        return None
    return {'schedule': value['schedule'], 'from': value['from'], 'until': value.get('until')}


# ---- Which schedule applies on a date ----

def find_schedule(state, schedule_id):
    return next((s for s in state['schedules'] if s['id'] == schedule_id), None)


def default_schedule(state):
    return next(s for s in state['schedules'] if s['default'])


def auto_schedule(state, day):
    """The schedule whose date range covers day, or the default schedule."""
    for schedule in state['schedules']:
        if schedule['range'] and in_range(schedule['range'], day):
            return schedule
    return default_schedule(state)


def schedule_for(state, day):
    """The schedule in use on day: a manual pick while it lasts, otherwise the automatic one."""
    override = state.get('override')
    if override and override['from'] <= day.isoformat() and (
            override['until'] is None or day.isoformat() < override['until']):
        picked = find_schedule(state, override['schedule'])
        if picked is not None:
            return picked
    return auto_schedule(state, day)


def is_manual(state, day):
    """True when a manual pick, not the dates, decides day's schedule."""
    return schedule_for(state, day)['id'] != auto_schedule(state, day)['id']


def bells_for(state, day):
    return schedule_for(state, day)['bells']


def find_bell(state, bell_id):
    """Return (schedule, bell) for a bell id in any schedule, or (None, None)."""
    for schedule in state['schedules']:
        for bell in schedule['bells']:
            if bell['id'] == bell_id:
                return schedule, bell
    return None, None


def _override_until(state, start):
    """The first day after start whose automatic schedule differs from start's, or None."""
    base = auto_schedule(state, start)['id']
    for n in range(1, 367):
        day = start + timedelta(days=n)
        if auto_schedule(state, day)['id'] != base:
            return day.isoformat()
    return None


# ---- Loading and saving ----

def load_state(path, log):
    """Load bells.json. A missing file gives the default; an unreadable one is set aside.

    A file from before schedules existed loads as one default schedule named Standard.
    """
    if not os.path.exists(path):
        return default_state()
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        state = validate_settings(data)
        if 'schedules' in data:
            state['schedules'] = validate_schedules(data['schedules'])
        else:
            state['schedules'] = [_schedule(DEFAULT_ID, 'Standard', default=True,
                                            bell_list=validate_bells(data.get('bells')))]
        state['override'] = _check_override(data.get('override'), state['schedules'])
        state['held_on'] = data.get('held_on') if _is_iso_date(data.get('held_on')) else None
        return state
    except (OSError, ValueError) as e:
        log.error('Could not read %s (%r). Starting with an empty schedule.' % (path, e))
        try:
            os.replace(path, path + '.bad')
        except OSError:
            pass
        return default_state()


def _is_iso_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def is_held(state, now):
    """True when scheduled bells are held for now's date."""
    return state.get('held_on') == now.date().isoformat()


def save_state(path, state):
    """Write state atomically, so a power cut can't leave a half-written file."""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ---- Due and next bells ----

def due_bells(state, now, rung):
    """Return the bells that ring in now's minute and haven't rung on now's date."""
    if not state['enabled'] or is_held(state, now):
        return []
    day = DAYS[now.weekday()]
    hhmm = now.strftime('%H:%M')
    today = now.date().isoformat()
    return [b for b in bells_for(state, now.date())
            if b['time'] == hhmm and day in b['days'] and (b['id'], today) not in rung
            and b.get('enabled', True) and b.get('skip_on') != today]


def skipped_bells(state, now, rung):
    """Return the enabled bells whose ring at now's minute is skipped and not yet recorded."""
    if not state['enabled'] or is_held(state, now):
        return []
    day = DAYS[now.weekday()]
    hhmm = now.strftime('%H:%M')
    today = now.date().isoformat()
    return [b for b in bells_for(state, now.date())
            if b['time'] == hhmm and day in b['days'] and (b['id'], today) not in rung
            and b.get('enabled', True) and b.get('skip_on') == today]


def next_occurrence(bell, now, from_tomorrow=False, state=None):
    """Return the ISO date of the bell's next ring after now's minute, ignoring any skip.

    With state, only dates on which the bell's schedule is in use count.
    """
    current = now.strftime('%H:%M')
    for offset in range(1 if from_tomorrow else 0, 400 if state is not None else 8):
        day = (now + timedelta(days=offset)).date()
        if state is not None and not any(b['id'] == bell['id'] for b in bells_for(state, day)):
            continue
        if DAYS[day.weekday()] in bell['days'] and (offset > 0 or bell['time'] > current):
            return day.isoformat()
    return None


def next_bell(state, now):
    """Return the next bell that will ring after now's minute, looking up to a week ahead."""
    if not state['enabled']:
        return None
    current = now.strftime('%H:%M')
    for offset in range(8):
        if offset == 0 and is_held(state, now):
            continue
        day = (now + timedelta(days=offset)).date()
        weekday = DAYS[day.weekday()]
        options = [b for b in bells_for(state, day)
                   if weekday in b['days'] and (offset > 0 or b['time'] > current)
                   and b.get('enabled', True) and b.get('skip_on') != day.isoformat()]
        if options:
            b = min(options, key=lambda b: b['time'])
            return {'id': b['id'], 'label': b['label'], 'time': b['time'], 'date': day.isoformat()}
    return None


def ring_target(state, now):
    """Return the bell Ring now plays: the next bell, ignoring the master switch and any hold."""
    return next_bell(dict(state, enabled=True, held_on=None), now)


class Store:
    """Thread-safe schedule holder. Each change is saved to disk before it takes effect."""

    def __init__(self, path, log):
        self._path = path
        self._lock = threading.Lock()
        self._state = load_state(path, log)

    def get(self):
        with self._lock:
            return copy.deepcopy(self._state)

    def _commit(self, new):
        save_state(self._path, new)
        self._state = new

    def bells(self, schedule_id=None):
        """A copy of one schedule's bells: the default schedule's unless an id is given."""
        with self._lock:
            schedule = (find_schedule(self._state, schedule_id) if schedule_id
                        else default_schedule(self._state))
            if schedule is None:
                raise KeyError(schedule_id)
            return copy.deepcopy(schedule['bells'])

    def set_bells(self, bells, sound_exists=None, schedule_id=None):
        """Replace one schedule's bells (the default schedule's unless an id is given)."""
        with self._lock:
            new = copy.deepcopy(self._state)
            target = find_schedule(new, schedule_id) if schedule_id else default_schedule(new)
            if target is None:
                raise KeyError(schedule_id)
            taken = {b['id'] for s in new['schedules'] if s is not target for b in s['bells']}
            target['bells'] = validate_bells(bells, sound_exists, taken)
            self._commit(new)
            return copy.deepcopy(target['bells'])

    def set_settings(self, data):
        if not isinstance(data, dict):
            raise ValidationError('Settings must be a JSON object')
        with self._lock:
            keys = ('enabled', 'master_volume', 'time_format')
            merged = {k: self._state[k] for k in keys}
            merged.update({k: data[k] for k in keys if k in data})
            clean = validate_settings(merged)
            self._commit(dict(self._state, **clean))
        return clean

    def set_held(self, held, today):
        """Hold scheduled bells for today (they resume at midnight), or resume them."""
        if not isinstance(held, bool):
            raise ValidationError('held must be true or false')
        with self._lock:
            self._commit(dict(self._state, held_on=today.isoformat() if held else None))
        return held

    def set_skip(self, bell_id, skip, now):
        """Skip the bell's next ring after now, or clear the skip. Raises KeyError for an unknown id."""
        if not isinstance(skip, bool):
            raise ValidationError('skip must be true or false')
        with self._lock:
            new = copy.deepcopy(self._state)
            schedule, bell = find_bell(new, bell_id)
            if bell is None:
                raise KeyError(bell_id)
            skip_on = None
            if skip:
                # On a held day, today's ring won't happen anyway, so skip the next real one.
                skip_on = next_occurrence(bell, now, from_tomorrow=is_held(new, now), state=new)
                if skip_on is None:
                    raise ValidationError("The %s schedule isn't in use on any coming date, "
                                          'so there is no ring to skip.' % schedule['name'])
            bell['skip_on'] = skip_on
            self._commit(new)
            return copy.deepcopy(bell)

    def bells_using(self, sound):
        """Labels of the bells that use a sound, with the schedule name when there are several."""
        with self._lock:
            several = len(self._state['schedules']) > 1
            return ['%s (%s)' % (b['label'] or b['time'], s['name']) if several else b['label'] or b['time']
                    for s in self._state['schedules'] for b in s['bells'] if b['sound'] == sound]

    def create_schedule(self, name, copy_from=None):
        """Add a schedule, empty or copied from another (new bell ids, no skips). Raises KeyError."""
        with self._lock:
            new = copy.deepcopy(self._state)
            clean_name = _clean_name(name, [s['name'] for s in new['schedules']])
            bell_list = []
            if copy_from is not None:
                source = find_schedule(new, copy_from)
                if source is None:
                    raise KeyError(copy_from)
                taken = {b['id'] for s in new['schedules'] for b in s['bells']}
                for bell in source['bells']:
                    bell_id = _new_id(taken)
                    taken.add(bell_id)
                    bell_list.append(dict(bell, id=bell_id, skip_on=None))
            schedule = _schedule(_new_id({s['id'] for s in new['schedules']}), clean_name,
                                 bell_list=bell_list)
            new['schedules'].append(schedule)
            self._commit(new)
            return copy.deepcopy(schedule)

    def update_schedule(self, schedule_id, changes):
        """Change a schedule's name, range, or default flag. Range and default changes clear any manual pick."""
        if not isinstance(changes, dict):
            raise ValidationError('Schedule changes must be a JSON object')
        with self._lock:
            new = copy.deepcopy(self._state)
            schedule = find_schedule(new, schedule_id)
            if schedule is None:
                raise KeyError(schedule_id)
            if 'name' in changes:
                schedule['name'] = _clean_name(
                    changes['name'], [s['name'] for s in new['schedules'] if s is not schedule])
            if changes.get('default') is True and not schedule['default']:
                for other in new['schedules']:
                    other['default'] = other is schedule
                schedule['range'] = None
                new['override'] = None
            if 'range' in changes:
                date_range = check_range(changes['range'])
                if schedule['default'] and date_range is not None:
                    raise ValidationError("The default schedule can't have a date range. "
                                          'Make another schedule the default first.')
                schedule['range'] = date_range
                _check_overlaps(new['schedules'])
                new['override'] = None
            self._commit(new)
            return copy.deepcopy(schedule)

    def delete_schedule(self, schedule_id):
        """Delete a schedule other than the default. Raises KeyError for an unknown id."""
        with self._lock:
            schedule = find_schedule(self._state, schedule_id)
            if schedule is None:
                raise KeyError(schedule_id)
            if schedule['default']:
                raise ValidationError("You can't delete the default schedule. "
                                      'Make another schedule the default first.')
            new = copy.deepcopy(self._state)
            new['schedules'] = [s for s in new['schedules'] if s['id'] != schedule_id]
            # Removing a range changes which schedule the dates give, like editing one does.
            if new['override'] and (new['override']['schedule'] == schedule_id or schedule['range']):
                new['override'] = None
            self._commit(new)

    def set_active(self, schedule_id, today):
        """Pick a schedule by hand from today until the automatic schedule next changes.

        None, or the schedule the dates already give, follows the dates. Raises KeyError.
        """
        with self._lock:
            new = copy.deepcopy(self._state)
            if schedule_id is None or auto_schedule(new, today)['id'] == schedule_id:
                if schedule_id is not None and find_schedule(new, schedule_id) is None:
                    raise KeyError(schedule_id)
                new['override'] = None
            else:
                if find_schedule(new, schedule_id) is None:
                    raise KeyError(schedule_id)
                new['override'] = {'schedule': schedule_id, 'from': today.isoformat(),
                                   'until': _override_until(new, today)}
            self._commit(new)
            return new['override']
