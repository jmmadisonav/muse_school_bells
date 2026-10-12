"""Bell schedule: validation, storage, and due-bell logic. No USB or web code."""
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
MAX_LABEL = 60


class ValidationError(ValueError):
    """A problem staff can fix. The message appears on the page."""


def default_state():
    return {'enabled': True, 'master_volume': 80, 'time_format': '24h', 'held_on': None, 'bells': []}


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


def validate_bells(bells, sound_exists=None):
    """Return a clean, time-sorted copy of a bell list, or raise ValidationError.

    Pass sound_exists to also require that each bell's sound file exists.
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
        if not isinstance(bell_id, str) or not ID_RE.match(bell_id) or bell_id in ids:
            bell_id = _new_id(ids)
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


def load_state(path, log):
    """Load bells.json. A missing file gives the default; an unreadable one is set aside."""
    if not os.path.exists(path):
        return default_state()
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        state = validate_settings(data)
        state['bells'] = validate_bells(data.get('bells'))
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


def due_bells(state, now, rung):
    """Return the bells that ring in now's minute and haven't rung on now's date."""
    if not state['enabled'] or is_held(state, now):
        return []
    day = DAYS[now.weekday()]
    hhmm = now.strftime('%H:%M')
    date = now.date().isoformat()
    return [b for b in state['bells']
            if b['time'] == hhmm and day in b['days'] and (b['id'], date) not in rung
            and b.get('enabled', True) and b.get('skip_on') != date]


def skipped_bells(state, now, rung):
    """Return the enabled bells whose ring at now's minute is skipped and not yet recorded."""
    if not state['enabled'] or is_held(state, now):
        return []
    day = DAYS[now.weekday()]
    hhmm = now.strftime('%H:%M')
    date = now.date().isoformat()
    return [b for b in state['bells']
            if b['time'] == hhmm and day in b['days'] and (b['id'], date) not in rung
            and b.get('enabled', True) and b.get('skip_on') == date]


def next_occurrence(bell, now):
    """Return the ISO date of the bell's next ring after now's minute, ignoring any skip."""
    current = now.strftime('%H:%M')
    for offset in range(8):
        day = (now + timedelta(days=offset)).date()
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
        date = (now + timedelta(days=offset)).date()
        day = DAYS[date.weekday()]
        options = [b for b in state['bells']
                   if day in b['days'] and (offset > 0 or b['time'] > current)
                   and b.get('enabled', True) and b.get('skip_on') != date.isoformat()]
        if options:
            b = min(options, key=lambda b: b['time'])
            return {'id': b['id'], 'label': b['label'], 'time': b['time'], 'date': date.isoformat()}
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

    def set_bells(self, bells, sound_exists=None):
        clean = validate_bells(bells, sound_exists)
        with self._lock:
            new = dict(self._state, bells=clean)
            save_state(self._path, new)
            self._state = new
        return copy.deepcopy(clean)

    def set_settings(self, data):
        if not isinstance(data, dict):
            raise ValidationError('Settings must be a JSON object')
        with self._lock:
            keys = ('enabled', 'master_volume', 'time_format')
            merged = {k: self._state[k] for k in keys}
            merged.update({k: data[k] for k in keys if k in data})
            clean = validate_settings(merged)
            new = dict(self._state, **clean)
            save_state(self._path, new)
            self._state = new
        return clean

    def set_held(self, held, today):
        """Hold scheduled bells for today (they resume at midnight), or resume them."""
        if not isinstance(held, bool):
            raise ValidationError('held must be true or false')
        with self._lock:
            new = dict(self._state, held_on=today.isoformat() if held else None)
            save_state(self._path, new)
            self._state = new
        return held

    def set_skip(self, bell_id, skip, now):
        """Skip the bell's next ring after now, or clear the skip. Raises KeyError for an unknown id."""
        if not isinstance(skip, bool):
            raise ValidationError('skip must be true or false')
        with self._lock:
            updated = copy.deepcopy(self._state['bells'])
            bell = next((b for b in updated if b['id'] == bell_id), None)
            if bell is None:
                raise KeyError(bell_id)
            bell['skip_on'] = next_occurrence(bell, now) if skip else None
            new = dict(self._state, bells=updated)
            save_state(self._path, new)
            self._state = new
            return copy.deepcopy(bell)

    def bells_using(self, sound):
        with self._lock:
            return [b['label'] or b['time'] for b in self._state['bells'] if b['sound'] == sound]
