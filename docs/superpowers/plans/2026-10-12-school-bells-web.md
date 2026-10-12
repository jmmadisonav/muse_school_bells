# School Bells Web Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve a web page from the AMX Muse `school_bells` program that schedules bells by time and weekday, uploads sounds, and plays them through the USB audio adapter.

**Architecture:** The deployable MUSE program lives in `school_bells/`, apart from tests, docs, and tools. It has six small Python modules: `bells` (schedule logic and storage), `sounds` (WAV rules), `audio` (libusb player), `scheduler` (ring thread), `web` (standard-library HTTP server and JSON API), and `touchpoints` (params, commands, and events for other MUSE programs). `main.py` wires them together. One self-contained `school_bells/static/index.html` page converts uploads to WAV in the browser and calls the API.

**Tech Stack:** Python 3.10 standard library (`http.server`, `wave`, `audioop`, `json`, `threading`), pip `libusb1` on the controller, `pytest` on the PC, and vanilla HTML, CSS, and JavaScript with the Web Audio API.

**Spec:** `docs/superpowers/specs/2026-10-12-school-bells-web-design.md`

## Global Constraints

- The controller runs Python 3.10.13 on aarch64. On the PC, use the repository venv (`.venv\Scripts\python`, Python 3.14) with `audioop-lts`. Write code that runs on Python 3.10: no `match` statements, and no standard-library features added after 3.10.
- Program modules live in `school_bells/`. `pyproject.toml` puts `school_bells/` and `tests/` on the pytest path, so tests import modules by bare name (`import bells`).
- Each program folder, `school_bells/` and each folder under `tools/` except `dev_server.py`, holds a `program.json` in the `.metadata` form: `$schema`, a `.metadata` object (`id` and `name` equal to the folder name, `provider`, `script`, `disabled`, and `description`), and touch points as top-level keys.
- The only controller dependency is `libusb1>=3.0,<4` in `school_bells/requirements.txt`. Everything else uses the standard library. `pytest` goes in `requirements-dev.txt` only, and never in `requirements.txt`.
- Only the `main.py` of each program folder imports `mojo`. Every other module receives a `log` object and calls only `log.info(str)` and `log.error(str)`.
- Sounds are 48 kHz, 16-bit, 2-channel PCM WAV files, up to 50 MB each.
- Sound names match `^[A-Za-z0-9_\-][A-Za-z0-9 _.\-]{0,79}\.wav$`.
- Bell times are 24-hour `HH:MM`. Days are `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, and `sun`. Volumes are integers from 0 to 100.
- Gain is `master_volume / 100 × bell volume / 100`. A manual play from the sounds list uses the master volume only.
- `school_bells/static/index.html` is one file with no external scripts, fonts, or stylesheets. It works at phone width. Its footer reads exactly: `This page has no login. Keep it on a restricted network.`
- Follow the Google developer documentation style guide for comments and docs: second person, active voice, present tense.
- Commit messages never carry a `Co-Authored-By` trailer, a `Claude-Session:` line, or any other Claude or Anthropic attribution.
- Work happens on the `bells-web` branch.
- Run every command from the repository root, `C:\Users\Jim\Developer\Muse Programs\school_bells`, in PowerShell.

## Review Focus

1. **Path tricks in sound names:** a name like `../main.py` or `a/b.wav`, in an upload, a delete, a bell, or a play request, must be rejected and must never touch a file outside `sounds/`. Tested in Task 3 (`check_name`, `sound_exists`) and Task 6 (upload and delete).
2. **Weekday mapping:** Python's `weekday()` returns 0 for Monday. Getting this off by one rings every bell on the wrong day. Tested in Task 2 (`test_sunday_maps_to_sun`).
3. **Adapter failure at bell time:** if the adapter is unplugged, an exception must not kill the scheduler, and later bells must still ring. Tested in Task 5 (`test_player_failure_does_not_stop_later_bells`).
4. **Midnight:** a 00:00 bell must ring on consecutive days, even though the rung record from yesterday is still in memory. Tested in Task 2 and Task 5.
5. **Oversized or unsized uploads:** the server must refuse an upload over 50 MB, or one with no `Content-Length`, before reading the body. Tested in Task 6 (411 and 413).

---

### Task 0: PC development setup (done)

Completed on 2026-10-12, before the restructure:
- `.venv` (Python 3.14, created by the user) with `pytest` and `audioop-lts`, listed in `requirements-dev.txt`.
- `.gitignore`, git initialized with a baseline commit on `main`, and work on the `bells-web` branch.
- `pyproject.toml` sets `pythonpath = ["school_bells", "tests"]` and `testpaths = ["tests"]`.
- `tests/helpers.py` holds `ListLog`, `FakePlayer`, and `make_wav`, and `tests/conftest.py` provides the `log` fixture.
- The program files moved into `school_bells/`, and the USB probe moved into `tools/usb_probe/` with its own `program.json`.

**Interfaces:**
- Produces: the `log` pytest fixture, a `ListLog` with `.infos` and `.errors` lists. `helpers.FakePlayer(fail=None)` has `.plays` (a list of `(path, gain)` pairs), `.stops` (int), `.playing` (str or None), `.fail` (an exception to raise on `play`, or None), `play(path, gain)`, and `stop()`. `helpers.make_wav(seconds=1.0, rate=48000, channels=2, width=2, tone_hz=440) -> bytes`.

---

### Task 1: Controller environment probe (Phase 0)

A probe program, kept in `tools/env_probe/`, that answers the spec's Phase 0 questions. Its result sets `DATA_DIR` in Task 8.

**Files:**
- Create: `tools/env_probe/program.json`
- Create: `tools/env_probe/main.py`
- Modify: `docs/superpowers/specs/2026-10-12-school-bells-web-design.md` (add the results)

**Interfaces:**
- Produces: a "Phase 0 results" section in the spec that records the data folder, the port, and whether `__file__` is defined. Task 8 reads it.

- [ ] **Step 1: Write the probe program**

`tools/env_probe/program.json`:
```json
{
  "$schema": "https://developer.amx.com/schema/amx-mojo-program-1.0.json",
  ".metadata": {
    "id": "env_probe",
    "name": "env_probe",
    "provider": "python",
    "script": "main.py",
    "disabled": false,
    "description": "Diagnostic: checks the web port, persistent folders, and clock for school_bells"
  }
}
```

`tools/env_probe/main.py`:
```python
"""Checks what the school_bells program needs from the controller: see Phase 0 in the spec."""
import glob
import os
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mojo import context

log = context.log
MARKER = 'bells_probe_marker.txt'
PORT = 8080


def candidate_dirs():
    dirs = []
    if '__file__' in globals():
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
    dirs += [os.getcwd(), os.path.expanduser('~'), '/data', '/mnt/data', '/var/lib', '/tmp']
    dirs += sorted(glob.glob('/mnt/*'))
    unique = []
    for d in dirs:
        if d not in unique:
            unique.append(d)
    return unique


def probe_paths():
    log.info('__file__: %r' % globals().get('__file__'))
    log.info('cwd: %s' % os.getcwd())
    log.info('sys.path[:4]: %s' % sys.path[:4])
    for d in candidate_dirs():
        marker = os.path.join(d, MARKER)
        earlier = None
        try:
            with open(marker) as f:
                earlier = f.read().strip()
        except OSError:
            pass
        try:
            with open(marker, 'w') as f:
                f.write(time.strftime('%Y-%m-%d %H:%M:%S'))
            free_mb = shutil.disk_usage(d).free // (1024 * 1024)
            log.info('%s: writable, %d MB free, marker from an earlier run: %s'
                     % (d, free_mb, earlier or 'none'))
        except OSError as e:
            log.info('%s: not writable (%s)' % (d, e.strerror))


def probe_clock():
    log.info('local time: %s' % time.strftime('%Y-%m-%d %H:%M:%S %Z (UTC%z)'))
    log.info('time.tzname: %s, TZ: %r' % (time.tzname, os.environ.get('TZ')))
    log.info('/etc/localtime -> %s' % os.path.realpath('/etc/localtime'))
    for path in ('/etc/timezone', '/etc/systemd/timesyncd.conf', '/etc/ntp.conf',
                 '/etc/chrony.conf', '/etc/chrony/chrony.conf'):
        log.info('%s exists: %s' % (path, os.path.exists(path)))


class Hello(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'school_bells probe OK\n'
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        log.info('probe http: ' + fmt % args)


def probe_port():
    try:
        server = ThreadingHTTPServer(('', PORT), Hello)
    except OSError as e:
        log.error('Cannot listen on port %d: %s' % (PORT, e))
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info('Listening on port %d. From a PC, run: curl.exe http://<controller-ip>:%d/' % (PORT, PORT))


for probe in (probe_paths, probe_clock, probe_port):
    try:
        probe()
    except Exception as e:
        log.error('%s raised %r' % (probe.__name__, e))

# leave this as the last line in the Python script
context.run(globals())
```

- [ ] **Step 2: Check the JSON and commit**

Run: `.venv\Scripts\python -c "import json; json.load(open('tools/env_probe/program.json'))"`
Expected: no output.

```powershell
git add tools/env_probe
git commit -m "Add the controller environment probe program"
```

- [ ] **Step 3: Run it on the controller (the user does this step)**

Ask the user to:
1. Load the `tools/env_probe` folder as a program and attach to its output.
2. From the PC, run `curl.exe http://<controller-ip>:8080/` and confirm it prints `school_bells probe OK`.
3. Load the `tools/env_probe` folder again, which replaces the program's files, and paste the output.
4. Reboot the controller and paste the output again.
5. Stop or remove the `env_probe` program so it frees port 8080.

Expected: the second and third runs show `marker from an earlier run: <timestamp>` for each folder that keeps files.

- [ ] **Step 4: Decide and record the results**

Apply these rules:
- **Data folder:** the first writable folder, in the probe's listed order, whose marker survived both the reload and the reboot. If that's the program folder, Task 8 uses `os.path.join(HERE, 'data')`. Otherwise, Task 8 uses that folder plus `/school_bells`.
- **Port:** if the `curl.exe` check failed, stop and tell the user. The spec says a blocked port means revising the design.
- **Clock:** if the local time or offset is wrong for the school, tell the user so they can fix the controller's time zone and NTP settings in the Muse web UI before relying on bells.

Append this section to the end of the spec, filled in with the observed values:
```markdown
## Phase 0 results (<date>)

- Port 8080 reachable from the LAN: <yes/no>
- `__file__` defined: <yes/no>; program folder: <path>
- Program folder kept files after a reload: <yes/no>; after a reboot: <yes/no>
- Persistent data folder: <path> (<free MB> MB free)
- Controller local time and offset: <value>; NTP config present: <files found>
```

- [ ] **Step 5: Commit**

```powershell
git add docs/superpowers/specs/2026-10-12-school-bells-web-design.md
git commit -m "Record controller environment probe results"
```

---

### Task 2: Bell schedule logic and storage (`bells.py`)

**Files:**
- Create: `school_bells/bells.py`
- Test: `tests/test_bells.py`

**Interfaces:**
- Produces:
  - `DAYS` tuple and `ValidationError(ValueError)`.
  - `check_volume(value, what) -> int` and `default_state() -> dict`.
  - `validate_settings(data: dict) -> {'enabled': bool, 'master_volume': int}`.
  - `validate_bells(bells: list, sound_exists: Callable[[str], bool] | None = None) -> list[dict]`. Bells come back sorted by time, with the keys `id`, `label`, `time`, `days`, `sound`, and `volume`.
  - `load_state(path, log) -> dict` and `save_state(path, state) -> None`.
  - `due_bells(state, now: datetime, rung: set[tuple[str, str]]) -> list[dict]`. `rung` holds `(bell id, ISO date)` pairs.
  - `next_bell(state, now) -> {'id', 'label', 'time', 'date'} | None`.
  - `Store(path, log)` with `get() -> dict` (a deep copy), `set_bells(bells, sound_exists=None) -> list`, `set_settings(data) -> dict`, and `bells_using(sound) -> list[str]`, which returns labels, or the time for a bell with no label.

- [ ] **Step 1: Write the failing tests**

`tests/test_bells.py`:
```python
import json
from datetime import datetime

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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `.venv\Scripts\python -m pytest tests/test_bells.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'bells'`.

- [ ] **Step 3: Write `bells.py`**

```python
"""Bell schedule: validation, storage, and due-bell logic. No USB or web code."""
import copy
import json
import os
import re
import secrets
import threading
from datetime import timedelta

DAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')  # index matches datetime.weekday()
TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
ID_RE = re.compile(r'^[a-z0-9]{1,16}$')
MAX_LABEL = 60


class ValidationError(ValueError):
    """A problem staff can fix. The message appears on the page."""


def default_state():
    return {'enabled': True, 'master_volume': 80, 'bells': []}


def check_volume(value, what):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise ValidationError('%s must be a whole number from 0 to 100' % what)
    return value


def validate_settings(data):
    if not isinstance(data, dict):
        raise ValidationError('Settings must be a JSON object')
    if not isinstance(data.get('enabled'), bool):
        raise ValidationError('enabled must be true or false')
    return {'enabled': data['enabled'],
            'master_volume': check_volume(data.get('master_volume'), 'Master volume')}


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
                       'sound': sound, 'volume': volume})
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
        return state
    except (OSError, ValueError) as e:
        log.error('Could not read %s (%r). Starting with an empty schedule.' % (path, e))
        try:
            os.replace(path, path + '.bad')
        except OSError:
            pass
        return default_state()


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
    if not state['enabled']:
        return []
    day = DAYS[now.weekday()]
    hhmm = now.strftime('%H:%M')
    date = now.date().isoformat()
    return [b for b in state['bells']
            if b['time'] == hhmm and day in b['days'] and (b['id'], date) not in rung]


def next_bell(state, now):
    """Return the next bell after now's minute, looking up to a week ahead."""
    if not state['enabled']:
        return None
    current = now.strftime('%H:%M')
    for offset in range(8):
        date = (now + timedelta(days=offset)).date()
        day = DAYS[date.weekday()]
        options = [b for b in state['bells']
                   if day in b['days'] and (offset > 0 or b['time'] > current)]
        if options:
            b = min(options, key=lambda b: b['time'])
            return {'id': b['id'], 'label': b['label'], 'time': b['time'], 'date': date.isoformat()}
    return None


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
            merged = {'enabled': self._state['enabled'], 'master_volume': self._state['master_volume']}
            merged.update({k: data[k] for k in ('enabled', 'master_volume') if k in data})
            clean = validate_settings(merged)
            new = dict(self._state, **clean)
            save_state(self._path, new)
            self._state = new
        return clean

    def bells_using(self, sound):
        with self._lock:
            return [b['label'] or b['time'] for b in self._state['bells'] if b['sound'] == sound]
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv\Scripts\python -m pytest tests/test_bells.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add school_bells/bells.py tests/test_bells.py
git commit -m "Add bell schedule validation, storage, and due-bell logic"
```

---

### Task 3: Sound files (`sounds.py`)

**Files:**
- Create: `school_bells/sounds.py`
- Test: `tests/test_sounds.py`

**Interfaces:**
- Consumes: `bells.ValidationError`.
- Produces:
  - Constants: `MAX_UPLOAD_BYTES`, `RATE` (48000), `CHANNELS` (2), `SAMPLE_WIDTH` (2), and `NAME_RE`.
  - `check_name(name) -> str`, which raises ValidationError.
  - `sound_exists(sounds_dir, name) -> bool`.
  - `wav_seconds(data: bytes) -> float`, which raises ValidationError.
  - `list_sounds(sounds_dir) -> list[{'name': str, 'seconds': float | None}]`.
  - `save_sound(sounds_dir, name, data, overwrite=False)`, which raises FileExistsError.
  - `apply_gain(frames: bytes, gain: float) -> bytes`.

- [ ] **Step 1: Write the failing tests**

`tests/test_sounds.py`:
```python
import struct

import pytest

import sounds
from bells import ValidationError
from helpers import make_wav


@pytest.mark.parametrize('name', ['recess.wav', 'Recess bell 2.wav', 'a-b_c.d.wav', '_x.wav'])
def test_check_name_accepts(name):
    assert sounds.check_name(name) == name


@pytest.mark.parametrize('name', ['../x.wav', 'a/b.wav', 'a\\b.wav', '.hidden.wav', ' x.wav',
                                  'x.mp3', '.wav', '', None, 'x' * 90 + '.wav'])
def test_check_name_rejects(name):
    with pytest.raises(ValidationError):
        sounds.check_name(name)


def test_sound_exists_refuses_paths_outside_dir(tmp_path):
    (tmp_path / 'outside.wav').write_bytes(b'x')
    inner = tmp_path / 'sounds'
    inner.mkdir()
    (inner / 'in.wav').write_bytes(b'x')
    assert sounds.sound_exists(str(inner), 'in.wav')
    assert not sounds.sound_exists(str(inner), '../outside.wav')
    assert not sounds.sound_exists(str(inner), 'missing.wav')


def test_wav_seconds_accepts_48k_16bit_stereo():
    assert sounds.wav_seconds(make_wav(1.0)) == pytest.approx(1.0)


@pytest.mark.parametrize('data', [
    make_wav(0.1, rate=44100), make_wav(0.1, channels=1), make_wav(0.1, width=1), b'not a wav',
])
def test_wav_seconds_rejects_other_formats(data):
    with pytest.raises(ValidationError):
        sounds.wav_seconds(data)


def test_list_sounds_sorts_and_flags_unreadable(tmp_path):
    (tmp_path / 'b.wav').write_bytes(make_wav(0.5))
    (tmp_path / 'A.wav').write_bytes(make_wav(0.25))
    (tmp_path / 'broken.wav').write_bytes(b'junk')
    (tmp_path / 'c.wav.tmp').write_bytes(b'partial')
    assert sounds.list_sounds(str(tmp_path)) == [
        {'name': 'A.wav', 'seconds': 0.25},
        {'name': 'b.wav', 'seconds': 0.5},
        {'name': 'broken.wav', 'seconds': None},
    ]


def test_save_sound_refuses_overwrite_unless_asked(tmp_path):
    sounds.save_sound(str(tmp_path), 'a.wav', b'one')
    with pytest.raises(FileExistsError):
        sounds.save_sound(str(tmp_path), 'a.wav', b'two')
    sounds.save_sound(str(tmp_path), 'a.wav', b'two', overwrite=True)
    assert (tmp_path / 'a.wav').read_bytes() == b'two'
    assert not (tmp_path / 'a.wav.tmp').exists()


def test_apply_gain_scales_and_clamps():
    frames = struct.pack('<hh', 1000, -1000)
    assert struct.unpack('<hh', sounds.apply_gain(frames, 0.5)) == (500, -500)
    assert sounds.apply_gain(frames, 1.0) == frames
    assert sounds.apply_gain(frames, 3.0) == frames
    assert struct.unpack('<hh', sounds.apply_gain(frames, -1)) == (0, 0)
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `.venv\Scripts\python -m pytest tests/test_sounds.py -v`
Expected: `ModuleNotFoundError: No module named 'sounds'`.

- [ ] **Step 3: Write `sounds.py`**

```python
"""Stored bell sounds: name rules, WAV format checks, listing, and gain."""
import audioop
import io
import os
import re
import wave

from bells import ValidationError

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
RATE = 48000
CHANNELS = 2
SAMPLE_WIDTH = 2
NAME_RE = re.compile(r'^[A-Za-z0-9_\-][A-Za-z0-9 _.\-]{0,79}\.wav$')


def check_name(name):
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ValidationError('Sound names may use letters, digits, spaces, _, - and ., '
                              'and must end in .wav')
    return name


def sound_exists(sounds_dir, name):
    """True if name is a valid sound name and that file exists in sounds_dir."""
    return (isinstance(name, str) and bool(NAME_RE.match(name))
            and os.path.isfile(os.path.join(sounds_dir, name)))


def wav_seconds(data):
    """Return the length of WAV bytes in seconds, or raise ValidationError if the format is wrong."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            fmt = (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getcomptype())
            frames = w.getnframes()
    except (wave.Error, EOFError) as e:
        raise ValidationError('Not a readable WAV file (%s)' % e)
    if fmt != (RATE, CHANNELS, SAMPLE_WIDTH, 'NONE'):
        raise ValidationError('Sounds must be 48 kHz, 16-bit, stereo PCM WAV files')
    return frames / RATE


def list_sounds(sounds_dir):
    """List stored sounds by name. Unreadable files have seconds set to None so staff can delete them."""
    result = []
    for name in sorted(os.listdir(sounds_dir), key=str.lower):
        if not NAME_RE.match(name):
            continue
        try:
            with wave.open(os.path.join(sounds_dir, name)) as w:
                seconds = w.getnframes() / w.getframerate()
        except (OSError, wave.Error, EOFError):
            seconds = None
        result.append({'name': name, 'seconds': seconds})
    return result


def save_sound(sounds_dir, name, data, overwrite=False):
    path = os.path.join(sounds_dir, check_name(name))
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(name)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def apply_gain(frames, gain):
    """Scale 16-bit PCM frames by gain, clamped to the range 0 to 1."""
    gain = max(0.0, min(1.0, gain))
    if gain >= 1.0:
        return frames
    return audioop.mul(frames, SAMPLE_WIDTH, gain)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv\Scripts\python -m pytest tests/test_sounds.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add school_bells/sounds.py tests/test_sounds.py
git commit -m "Add sound name rules, WAV checks, and gain"
```

---

### Task 4: USB audio player (`audio.py`)

This task moves the proven streamer out of the current `main.py` and into a `Player` class that plays WAV files on a worker thread and can be stopped. Only the chunking logic can be tested on the PC. Playback is checked on the controller in Task 7.

**Files:**
- Create: `school_bells/audio.py`
- Test: `tests/test_audio.py`

**Interfaces:**
- Consumes: `sounds.RATE`, `sounds.CHANNELS`, `sounds.SAMPLE_WIDTH`, and `sounds.apply_gain`.
- Produces:
  - `AudioError(RuntimeError)`.
  - `iter_chunks(read_frames: Callable[[int], bytes], gain: float)`, which yields `(bytearray, list[int])` pairs.
  - `Player(log)` with `play(path: str, gain: float) -> None`, which returns immediately, raises AudioError if the file or adapter can't be opened, and stops any current sound. It also has `stop() -> None` and a `playing` property (str or None).
  - `_usb1` stays `None` until the first `play()`, so importing `audio` on the PC doesn't need libusb.

- [ ] **Step 1: Write the failing tests**

`tests/test_audio.py`:
```python
import struct

import audio


def reader(data):
    position = [0]

    def read_frames(count):
        chunk = data[position[0]:position[0] + count * 4]
        position[0] += len(chunk)
        return chunk
    return read_frames


def test_iter_chunks_splits_one_second_into_1ms_packets():
    data = bytes(48000 * 4)
    chunks = list(audio.iter_chunks(reader(data), 1.0))
    assert len(chunks) == 32  # 31 full transfers of 1536 frames, then 384 frames
    assert chunks[0][1] == [192] * 32
    assert chunks[-1][1] == [192] * 8
    assert sum(len(d) for d, _ in chunks) == len(data)
    assert all(sum(sizes) == len(d) for d, sizes in chunks)


def test_iter_chunks_ends_with_partial_packet():
    assert list(audio.iter_chunks(reader(bytes(100 * 4)), 1.0)) == [(bytearray(400), [192, 192, 16])]


def test_iter_chunks_applies_gain():
    data = struct.pack('<hh', 1000, -1000) * 48
    [(chunk, sizes)] = list(audio.iter_chunks(reader(data), 0.5))
    assert struct.unpack('<hh', bytes(chunk[:4])) == (500, -500)
    assert sizes == [192]


def test_importing_audio_does_not_load_libusb():
    assert audio._usb1 is None
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `.venv\Scripts\python -m pytest tests/test_audio.py -v`
Expected: `ModuleNotFoundError: No module named 'audio'`.

- [ ] **Step 3: Write `audio.py`**

```python
"""Plays WAV files through the USB audio adapter with libusb.

The Muse kernel has no sound support, so this module streams PCM to the
adapter's isochronous endpoint itself.
"""
import ctypes.util
import os
import threading
import wave

import sounds

VENDOR_ID = 0x0D8C   # C-Media
PRODUCT_ID = 0x0014  # Unitek Y-247A USB audio adapter
FRAMES_PER_PACKET = sounds.RATE // 1000  # one isochronous packet per 1 ms USB frame
PACKETS_PER_TRANSFER = 32
TRANSFERS_IN_FLIGHT = 4  # queued transfers that keep the stream from starving

_usb1 = None


class AudioError(RuntimeError):
    """The adapter or sound file can't be used. The message appears on the page."""


def _load_usb1():
    """Import usb1 on first use. Its library lookup can fail on embedded Linux, so add a fallback."""
    global _usb1
    if _usb1 is None:
        find_library = ctypes.util.find_library

        def find_with_fallback(name):
            found = find_library(name)
            if found is None and name == 'usb-1.0':
                return '/lib/libusb-1.0.so.0'
            return found

        ctypes.util.find_library = find_with_fallback
        import usb1
        _usb1 = usb1
    return _usb1


def iter_chunks(read_frames, gain):
    """Yield (data, packet sizes) per transfer, reading frames with read_frames(count)."""
    frame_bytes = sounds.CHANNELS * sounds.SAMPLE_WIDTH
    packet_bytes = FRAMES_PER_PACKET * frame_bytes
    while True:
        data = read_frames(FRAMES_PER_PACKET * PACKETS_PER_TRANSFER)
        if not data:
            return
        data = sounds.apply_gain(data, gain)
        sizes = [packet_bytes] * (len(data) // packet_bytes)
        if len(data) % packet_bytes:
            sizes.append(len(data) % packet_bytes)
        yield bytearray(data), sizes


def _class_descriptors(extra):
    """Split a setting's extra bytes into USB Audio class-specific descriptors."""
    if isinstance(extra, (list, tuple)):
        extra = b''.join(bytes(d) for d in extra)
    extra = bytes(extra)
    found = []
    i = 0
    while i + 2 < len(extra):
        length = extra[i]
        if length < 3:
            break
        if extra[i + 1] == 0x24:  # CS_INTERFACE
            found.append(extra[i:i + length])
        i += length
    return found


def _playback_settings(device):
    """List the AudioStreaming alternate settings that have an isochronous OUT endpoint."""
    found = []
    for config in device:
        for interface in config:
            for setting in interface:
                if setting.getClass() != 1 or setting.getSubClass() != 2:
                    continue
                endpoints = [ep for ep in setting
                             if ep.getAttributes() & 0x03 == 1 and not ep.getAddress() & 0x80]
                fmt = [d for d in _class_descriptors(setting.getExtra())
                       if d[2] == 0x02 and len(d) >= 8 and d[3] == 1]  # FORMAT_TYPE_I
                if not endpoints or not fmt:
                    continue
                d = fmt[0]
                found.append({
                    'interface': setting.getNumber(),
                    'alt': setting.getAlternateSetting(),
                    'endpoint': endpoints[0].getAddress(),
                    'channels': d[4],
                    'subframe': d[5],
                    'continuous': d[7] == 0,
                    'rates': [int.from_bytes(d[k:k + 3], 'little') for k in range(8, len(d) - 2, 3)],
                })
    return found


def _supports_format(setting):
    rates = setting['rates']
    if setting['continuous'] and len(rates) >= 2:
        rate_ok = rates[0] <= sounds.RATE <= rates[1]
    else:
        rate_ok = sounds.RATE in rates
    return rate_ok and setting['channels'] == sounds.CHANNELS and setting['subframe'] == sounds.SAMPLE_WIDTH


def _unmute(handle, device, usb1):
    # SET_CUR on the mute control of each feature unit, for the master and both
    # channels. Controls a unit doesn't have are rejected, which is fine.
    for config in device:
        for interface in config:
            for setting in interface:
                if setting.getClass() != 1 or setting.getSubClass() != 1:
                    continue
                for d in _class_descriptors(setting.getExtra()):
                    if d[2] != 0x06 or len(d) <= 3:  # FEATURE_UNIT
                        continue
                    for channel in (0, 1, 2):
                        try:
                            handle.controlWrite(0x21, 0x01, 0x0100 | channel,
                                                (d[3] << 8) | setting.getNumber(), b'\x00')
                        except usb1.USBError:
                            pass


class _Session:
    """One open, configured stream to the adapter."""

    def __init__(self, usb, handle, setting):
        self._usb = usb
        self._handle = handle
        self._setting = setting

    @classmethod
    def open(cls):
        usb1 = _load_usb1()
        usb = usb1.USBContext()
        try:
            handle = usb.openByVendorIDAndProductID(VENDOR_ID, PRODUCT_ID)
            if handle is None:
                raise AudioError('The USB audio adapter is not connected')
            device = handle.getDevice()
            matches = [s for s in _playback_settings(device) if _supports_format(s)]
            if not matches:
                raise AudioError('The USB audio adapter does not support 48 kHz 16-bit stereo')
            s = matches[0]
            handle.claimInterface(s['interface'])
            handle.setInterfaceAltSetting(s['interface'], s['alt'])
            try:
                # SET_CUR sampling frequency on the endpoint.
                handle.controlWrite(0x22, 0x01, 0x0100, s['endpoint'], sounds.RATE.to_bytes(3, 'little'))
            except usb1.USBError:
                pass  # single-rate devices reject this request
            _unmute(handle, device, usb1)
            return cls(usb, handle, s)
        except AudioError:
            usb.close()
            raise
        except Exception as e:
            usb.close()
            raise AudioError('Cannot open the USB audio adapter: %r' % e)

    def stream(self, chunks, stop):
        """Send chunks as queued isochronous transfers until done or stop is set. Returns failures."""
        usb1 = _load_usb1()
        state = {'active': 0, 'errors': 0}

        def submit_next(transfer):
            if stop.is_set():
                return
            chunk = next(chunks, None)
            if chunk is None:
                return
            data, sizes = chunk
            transfer.setIsochronous(self._setting['endpoint'], data, callback=on_done,
                                    iso_transfer_length_list=sizes)
            transfer.submit()
            state['active'] += 1

        def on_done(transfer):
            state['active'] -= 1
            if transfer.getStatus() != usb1.TRANSFER_COMPLETED:
                state['errors'] += 1
            submit_next(transfer)

        transfers = [self._handle.getTransfer(iso_packets=PACKETS_PER_TRANSFER)
                     for _ in range(TRANSFERS_IN_FLIGHT)]
        for transfer in transfers:
            submit_next(transfer)
        while state['active']:
            self._usb.handleEvents()
        for transfer in transfers:
            transfer.close()
        return state['errors']

    def close(self):
        interface = self._setting['interface']
        for step in (lambda: self._handle.setInterfaceAltSetting(interface, 0),
                     lambda: self._handle.releaseInterface(interface),
                     self._handle.close, self._usb.close):
            try:
                step()
            except Exception:
                pass


class Player:
    """Plays one WAV file at a time. A new play stops the current one."""

    def __init__(self, log):
        self._log = log
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self._playing = None

    @property
    def playing(self):
        return self._playing

    def play(self, path, gain):
        """Start playing path at gain (0 to 1). Raises AudioError if the file or adapter can't be opened."""
        with self._lock:
            self._stop_locked()
            try:
                wav = wave.open(path, 'rb')
            except (OSError, wave.Error, EOFError) as e:
                raise AudioError('Cannot read %s (%s)' % (os.path.basename(path), e))
            try:
                session = _Session.open()
            except Exception:
                wav.close()
                raise
            stop = threading.Event()
            self._stop = stop
            self._playing = os.path.basename(path)
            self._thread = threading.Thread(target=self._run, args=(session, wav, gain, stop),
                                            daemon=True, name='bell-player')
            self._thread.start()

    def stop(self):
        with self._lock:
            self._stop_locked()

    def _stop_locked(self):
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=2)
            self._thread = None
        self._playing = None

    def _run(self, session, wav, gain, stop):
        name = self._playing
        try:
            errors = session.stream(iter_chunks(wav.readframes, gain), stop)
            if errors:
                self._log.error('%d USB transfers failed while playing %s' % (errors, name))
        except Exception as e:
            self._log.error('Playback of %s failed: %r' % (name, e))
        finally:
            wav.close()
            session.close()
            if self._stop is stop:
                self._playing = None
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv\Scripts\python -m pytest tests/test_audio.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add school_bells/audio.py tests/test_audio.py
git commit -m "Add a stoppable USB audio player for WAV files"
```

---

### Task 5: Scheduler (`scheduler.py`)

**Files:**
- Create: `school_bells/scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `bells.Store.get()`, `bells.due_bells(state, now, rung)`, and `Player.play(path, gain)`.
- Produces: `Scheduler(store, player, sounds_dir, log, clock=datetime.now, events=None)` with `prime(now)`, `tick(now) -> list[str]` (the ids of the bells handled), and `start()`, which primes the scheduler and then ticks every second on a daemon thread.
- `events`, when given, is any object with `bell_rang(bell)` and `error(message)`. Task 7's `TouchPoints` is that object in production. The scheduler calls `bell_rang` after each successful play, and sends errors to `events.error` instead of `log.error`.

- [ ] **Step 1: Write the failing tests**

`tests/test_scheduler.py`:
```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `.venv\Scripts\python -m pytest tests/test_scheduler.py -v`
Expected: `ModuleNotFoundError: No module named 'scheduler'`.

- [ ] **Step 3: Write `scheduler.py`**

```python
"""Rings each due bell once, using the controller's local clock."""
import os
import threading
import time
from datetime import datetime, timedelta

import bells


class Scheduler:
    def __init__(self, store, player, sounds_dir, log, clock=datetime.now, events=None):
        self._store = store
        self._player = player
        self._sounds_dir = sounds_dir
        self._log = log
        self._clock = clock
        self._events = events  # has bell_rang(bell) and error(message), or None
        self._rung = set()  # (bell id, ISO date) pairs; memory only

    def _error(self, message):
        if self._events is not None:
            self._events.error(message)
        else:
            self._log.error(message)

    def prime(self, now):
        """Mark bells in now's minute as rung, so a restart can't ring them twice."""
        state = dict(self._store.get(), enabled=True)
        for b in bells.due_bells(state, now, set()):
            self._rung.add((b['id'], now.date().isoformat()))

    def tick(self, now):
        """Ring every bell due at now. Returns the ids of the bells handled."""
        state = self._store.get()
        today = now.date().isoformat()
        yesterday = (now.date() - timedelta(days=1)).isoformat()
        self._rung = {key for key in self._rung if key[1] >= yesterday}
        handled = []
        for b in bells.due_bells(state, now, self._rung):
            self._rung.add((b['id'], today))
            handled.append(b['id'])
            name = b['label'] or b['time']
            path = os.path.join(self._sounds_dir, b['sound'])
            if not os.path.isfile(path):
                self._error('Bell "%s" at %s: sound %s is missing' % (name, b['time'], b['sound']))
                continue
            gain = state['master_volume'] / 100 * b['volume'] / 100
            try:
                self._player.play(path, gain)
            except Exception as e:
                self._error('Bell "%s" at %s failed: %s' % (name, b['time'], e))
                continue
            self._log.info('Rang bell "%s" at %s' % (name, b['time']))
            if self._events is not None:
                self._events.bell_rang(b)
        return handled

    def start(self):
        self.prime(self._clock())
        threading.Thread(target=self._loop, daemon=True, name='bell-scheduler').start()

    def _loop(self):
        while True:
            try:
                self.tick(self._clock())
            except Exception as e:
                self._log.error('Scheduler tick failed: %r' % e)
            time.sleep(1.0)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv\Scripts\python -m pytest tests/test_scheduler.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add school_bells/scheduler.py tests/test_scheduler.py
git commit -m "Add the bell scheduler thread"
```

---

### Task 6: Web server and JSON API (`web.py`)

**Files:**
- Create: `school_bells/web.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `bells.Store` (`get`, `set_bells`, `set_settings`, `bells_using`), `bells.next_bell`, `bells.check_volume`, `bells.DAYS`, `bells.ValidationError`, `sounds.*`, `audio.AudioError`, and the Player interface (`play`, `stop`, `playing`).
- Produces: `make_server(port, store, player, sounds_dir, static_dir, log, clock=datetime.now, host='') -> ThreadingHTTPServer`. The caller runs `serve_forever()`. The routes are as described in the spec's Web API section.

- [ ] **Step 1: Write the failing tests**

`tests/test_web.py`:
```python
import http.client
import json
import threading
import types
import urllib.parse
from datetime import datetime

import pytest

import bells
import web
from audio import AudioError
from helpers import FakePlayer, make_wav

NOW = datetime(2026, 10, 12, 10, 52, 7)  # Monday
RECESS = {'label': 'Recess', 'time': '11:00', 'days': ['mon', 'tue', 'wed', 'thu', 'fri'],
          'sound': 'recess.wav', 'volume': 50}


@pytest.fixture
def app(tmp_path, log):
    sounds_dir = tmp_path / 'sounds'
    sounds_dir.mkdir()
    static_dir = tmp_path / 'static'
    static_dir.mkdir()
    (static_dir / 'index.html').write_text('<h1>bells</h1>')
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    player = FakePlayer()
    server = web.make_server(0, store, player, str(sounds_dir), str(static_dir), log,
                             clock=lambda: NOW, host='127.0.0.1')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield types.SimpleNamespace(port=server.server_address[1], store=store, player=player,
                                sounds_dir=sounds_dir, static_dir=static_dir)
    server.shutdown()
    server.server_close()


def call(app, method, path, body=None, raw=None, headers=None):
    conn = http.client.HTTPConnection('127.0.0.1', app.port, timeout=5)
    headers = dict(headers or {})
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    conn.request(method, path, body=data, headers=headers)
    response = conn.getresponse()
    text = response.read()
    conn.close()
    try:
        return response.status, json.loads(text)
    except ValueError:
        return response.status, text.decode()


def upload(app, name, data, overwrite=False):
    query = '?name=' + urllib.parse.quote(name) + ('&overwrite=1' if overwrite else '')
    return call(app, 'POST', '/api/sounds' + query, raw=data, headers={'Content-Type': 'audio/wav'})


def test_index_is_served_and_missing_index_is_404(app):
    assert call(app, 'GET', '/') == (200, '<h1>bells</h1>')
    (app.static_dir / 'index.html').unlink()
    assert call(app, 'GET', '/')[0] == 404


def test_state_reports_bells_sounds_and_next_bell(app):
    upload(app, 'recess.wav', make_wav(1.0))
    app.store.set_bells([RECESS, dict(RECESS, label='Lunch', time='13:00', sound='gone.wav')])
    status, state = call(app, 'GET', '/api/state')
    assert status == 200
    assert state['time'].startswith('2026-10-12T10:52:07')
    assert state['weekday'] == 'mon'
    assert state['enabled'] is True and state['master_volume'] == 80
    assert [(b['label'], b['missing_sound']) for b in state['bells']] == [('Recess', False), ('Lunch', True)]
    assert state['sounds'] == [{'name': 'recess.wav', 'seconds': 1.0}]
    assert state['playing'] is None
    assert state['next_bell']['label'] == 'Recess'


def test_put_bells_validates_and_saves(app):
    upload(app, 'recess.wav', make_wav(0.1))
    status, body = call(app, 'PUT', '/api/bells', {'bells': [RECESS]})
    assert status == 200 and body['bells'][0]['label'] == 'Recess'
    assert app.store.get()['bells'][0]['time'] == '11:00'
    assert call(app, 'PUT', '/api/bells', {'bells': [dict(RECESS, time='25:00')]})[0] == 400
    status, body = call(app, 'PUT', '/api/bells', {'bells': [dict(RECESS, sound='nope.wav')]})
    assert status == 400 and 'nope.wav' in body['error']
    assert call(app, 'PUT', '/api/bells', [RECESS])[0] == 400
    assert call(app, 'PUT', '/api/bells', raw=b'{bad', headers={'Content-Type': 'application/json'})[0] == 400


def test_put_settings_partial(app):
    assert call(app, 'PUT', '/api/settings', {'master_volume': 30}) == (
        200, {'enabled': True, 'master_volume': 30})
    assert call(app, 'PUT', '/api/settings', {'master_volume': 300})[0] == 400


def test_upload_checks_format_name_and_duplicates(app):
    assert upload(app, 'bell.wav', make_wav(0.5)) == (201, {'name': 'bell.wav', 'seconds': 0.5})
    assert upload(app, 'bell.wav', make_wav(0.5))[0] == 409
    assert upload(app, 'bell.wav', make_wav(0.25), overwrite=True)[0] == 201
    assert upload(app, 'cd.wav', make_wav(0.1, rate=44100))[0] == 400
    assert upload(app, 'junk.wav', b'junk')[0] == 400
    assert upload(app, '../escape.wav', make_wav(0.1))[0] == 400
    assert upload(app, 'a/b.wav', make_wav(0.1))[0] == 400
    assert sorted(p.name for p in app.sounds_dir.iterdir()) == ['bell.wav']


def test_upload_without_length_is_411(app):
    conn = http.client.HTTPConnection('127.0.0.1', app.port, timeout=5)
    conn.putrequest('POST', '/api/sounds?name=a.wav')
    conn.endheaders()
    assert conn.getresponse().status == 411


def test_upload_over_limit_is_413_without_reading_body(app):
    conn = http.client.HTTPConnection('127.0.0.1', app.port, timeout=5)
    conn.putrequest('POST', '/api/sounds?name=a.wav')
    conn.putheader('Content-Length', str(60 * 1024 * 1024))
    conn.endheaders()
    assert conn.getresponse().status == 413


def test_delete_sound_refuses_when_used(app):
    upload(app, 'recess.wav', make_wav(0.1))
    upload(app, 'spare.wav', make_wav(0.1))
    call(app, 'PUT', '/api/bells', {'bells': [RECESS]})
    status, body = call(app, 'DELETE', '/api/sounds/recess.wav')
    assert status == 409 and 'Recess' in body['error']
    assert call(app, 'DELETE', '/api/sounds/spare.wav')[0] == 200
    assert not (app.sounds_dir / 'spare.wav').exists()
    assert call(app, 'DELETE', '/api/sounds/spare.wav')[0] == 404
    assert call(app, 'DELETE', '/api/sounds/..%2Fbells.json')[0] == 400


def test_play_and_stop(app):
    upload(app, 'recess.wav', make_wav(0.1))
    assert call(app, 'POST', '/api/play', {'sound': 'recess.wav', 'volume': 50})[0] == 200
    assert call(app, 'POST', '/api/play', {'sound': 'recess.wav'})[0] == 200
    assert [round(g, 2) for _, g in app.player.plays] == [0.4, 0.8]
    assert call(app, 'POST', '/api/play', {'sound': 'nope.wav'})[0] == 404
    assert call(app, 'POST', '/api/play', {'sound': 'recess.wav', 'volume': 101})[0] == 400
    app.player.fail = AudioError('The USB audio adapter is not connected')
    status, body = call(app, 'POST', '/api/play', {'sound': 'recess.wav'})
    assert status == 503 and 'not connected' in body['error']
    assert call(app, 'POST', '/api/stop', {})[0] == 200
    assert app.player.stops == 1


def test_unknown_route_is_404(app):
    assert call(app, 'GET', '/api/nope')[0] == 404
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `.venv\Scripts\python -m pytest tests/test_web.py -v`
Expected: `ModuleNotFoundError: No module named 'web'`.

- [ ] **Step 3: Write `web.py`**

```python
"""HTTP server for the bell page and its JSON API."""
import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

import bells
import sounds
from audio import AudioError

MAX_JSON_BYTES = 1024 * 1024


def make_server(port, store, player, sounds_dir, static_dir, log, clock=datetime.now, host=''):
    """Return a server for the bell page and API. Call serve_forever() on it."""

    class Handler(BaseHTTPRequestHandler):
        server_version = 'SchoolBells/1.0'

        def log_message(self, fmt, *args):
            log.info('%s %s' % (self.address_string(), fmt % args))

        def do_GET(self):
            self._route('GET')

        def do_PUT(self):
            self._route('PUT')

        def do_POST(self):
            self._route('POST')

        def do_DELETE(self):
            self._route('DELETE')

        def _route(self, method):
            url = urlsplit(self.path)
            path, query = url.path, parse_qs(url.query)
            try:
                if method == 'GET' and path == '/':
                    return self._index()
                if method == 'GET' and path == '/api/state':
                    return self._send_json(200, self._state())
                if method == 'PUT' and path == '/api/bells':
                    return self._put_bells()
                if method == 'PUT' and path == '/api/settings':
                    return self._send_json(200, store.set_settings(self._read_json()))
                if method == 'POST' and path == '/api/sounds':
                    return self._upload(query)
                if method == 'DELETE' and path.startswith('/api/sounds/'):
                    return self._delete_sound(unquote(path[len('/api/sounds/'):]))
                if method == 'POST' and path == '/api/play':
                    return self._play()
                if method == 'POST' and path == '/api/stop':
                    player.stop()
                    return self._send_json(200, {'playing': None})
                self._error(404, 'Not found')
            except bells.ValidationError as e:
                self._error(400, str(e))
            except AudioError as e:
                self._error(503, str(e))
            except Exception as e:
                log.error('%s %s failed: %r' % (method, path, e))
                self._error(500, 'Internal error: %r' % e)

        def _send_json(self, status, body):
            data = json.dumps(body).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status, message):
            # The request body may be unread, so don't reuse this connection.
            self.close_connection = True
            self._send_json(status, {'error': message})

        def _read_json(self):
            try:
                length = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                raise bells.ValidationError('Invalid Content-Length')
            if length > MAX_JSON_BYTES:
                raise bells.ValidationError('Request is too large')
            try:
                return json.loads(self.rfile.read(length) or b'null')
            except ValueError:
                raise bells.ValidationError('Request body must be JSON')

        def _index(self):
            try:
                with open(os.path.join(static_dir, 'index.html'), 'rb') as f:
                    data = f.read()
            except OSError:
                return self._error(404, 'The bell page is not installed')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def _state(self):
            now = clock()
            state = store.get()
            return {
                'time': now.astimezone().isoformat(timespec='seconds'),
                'weekday': bells.DAYS[now.weekday()],
                'enabled': state['enabled'],
                'master_volume': state['master_volume'],
                'bells': [dict(b, missing_sound=not sounds.sound_exists(sounds_dir, b['sound']))
                          for b in state['bells']],
                'sounds': sounds.list_sounds(sounds_dir),
                'playing': player.playing,
                'next_bell': bells.next_bell(state, now),
            }

        def _put_bells(self):
            body = self._read_json()
            if not isinstance(body, dict):
                raise bells.ValidationError('Body must be {"bells": [...]}')
            clean = store.set_bells(body.get('bells'),
                                    lambda name: sounds.sound_exists(sounds_dir, name))
            self._send_json(200, {'bells': clean})

        def _upload(self, query):
            name = sounds.check_name(query.get('name', [''])[0])
            length_header = self.headers.get('Content-Length')
            if length_header is None:
                return self._error(411, 'Content-Length is required')
            try:
                length = int(length_header)
            except ValueError:
                raise bells.ValidationError('Invalid Content-Length')
            if length > sounds.MAX_UPLOAD_BYTES:
                return self._error(413, 'Sounds are limited to 50 MB')
            data = self.rfile.read(length)
            seconds = sounds.wav_seconds(data)
            try:
                sounds.save_sound(sounds_dir, name, data,
                                  overwrite=query.get('overwrite', ['0'])[0] == '1')
            except FileExistsError:
                return self._error(409, '%s already exists' % name)
            self._send_json(201, {'name': name, 'seconds': seconds})

        def _delete_sound(self, name):
            sounds.check_name(name)
            users = store.bells_using(name)
            if users:
                return self._error(409, '%s is used by these bells: %s' % (name, ', '.join(users)))
            if not sounds.sound_exists(sounds_dir, name):
                return self._error(404, '%s does not exist' % name)
            if player.playing == name:
                player.stop()
            os.remove(os.path.join(sounds_dir, name))
            self._send_json(200, {'deleted': name})

        def _play(self):
            body = self._read_json()
            if not isinstance(body, dict):
                raise bells.ValidationError('Body must be {"sound": "<name>"}')
            name = body.get('sound')
            if not sounds.sound_exists(sounds_dir, name):
                return self._error(404, 'Sound %s does not exist' % name)
            volume = bells.check_volume(body.get('volume', 100), 'Volume')
            gain = store.get()['master_volume'] / 100 * volume / 100
            player.play(os.path.join(sounds_dir, name), gain)
            self._send_json(200, {'playing': name})

    return ThreadingHTTPServer((host, port), Handler)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv\Scripts\python -m pytest tests -v`
Expected: every test in the suite passes.

- [ ] **Step 5: Commit**

```powershell
git add school_bells/web.py tests/test_web.py
git commit -m "Add the bell web server and JSON API"
```

---

### Task 7: Touch points for other MUSE programs (`touchpoints.py`)

**Files:**
- Create: `school_bells/touchpoints.py`
- Modify: `tests/helpers.py` (add `FakeExport`)
- Test: `tests/test_touchpoints.py`

**Interfaces:**
- Consumes: `bells.Store` (`get`, `set_settings`), `bells.next_bell`, `bells.check_volume`, `bells.ValidationError`, `sounds.sound_exists`, and the Player interface (`play`, `stop`, `playing`).
- Produces:
  - `TouchPoints(export, store, player, sounds_dir, log, clock=datetime.now)`.
  - `handlers() -> dict` with plain functions `set_enabled(value)`, `set_master_volume(value)`, `play_sound(args)`, and `stop_sound()`. `main.py` adds them to its globals.
  - `values() -> dict` holds the five param values.
  - `publish()` sends changed params only, and `start()` publishes, goes online, and then republishes changes every second.
  - `error(message)` logs the message and publishes it as `last_error`, and `bell_rang(bell)` dispatches the event. Together these two methods are the `events` object that Task 5's `Scheduler` takes.
  - Helpers: `to_bool(value)`, `to_volume(value)`, `sound_argument(args)`, and `describe_next(next_bell)`.
- MUSE fact this relies on (from `muse_control_extension/docs/reference/mojo.py:1221-1244`): MUSE counts a handler's parameters with `inspect.getfullargspec(f)[0]`. A setter with one parameter gets `f(value)`. A command with zero parameters gets `f()`, and one with one parameter gets `f(args)`. `getfullargspec` counts `self` on a bound method, so handlers must be plain functions, not methods.

- [ ] **Step 1: Add `FakeExport` to `tests/helpers.py`**

Append:
```python
class FakeExport:
    """Stands in for context.export and records what it sends to MUSE."""

    def __init__(self):
        self.updates = []
        self.dispatches = []
        self.calls = []

    def update(self, path, value, normalized=None):
        self.updates.append((path, value))
        self.calls.append('update')

    def dispatch(self, path, args=None):
        self.dispatches.append((path, args))
        self.calls.append('dispatch')

    def online(self):
        self.calls.append('online')

    def offline(self):
        self.calls.append('offline')
```

- [ ] **Step 2: Write the failing tests**

`tests/test_touchpoints.py`:
```python
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
    assert arity == {'set_enabled': 1, 'set_master_volume': 1, 'play_sound': 1, 'stop_sound': 0}


def test_publish_sends_everything_once_then_only_changes(tp):
    tp.tp.publish()
    assert dict(tp.export.updates) == {'enabled': True, 'master_volume': 80, 'playing': '',
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
    assert tp.export.calls[:6] == ['update'] * 5 + ['online']
```

- [ ] **Step 3: Run the tests to confirm they fail**

Run: `.venv\Scripts\python -m pytest tests/test_touchpoints.py -v`
Expected: `ModuleNotFoundError: No module named 'touchpoints'`.

- [ ] **Step 4: Write `school_bells/touchpoints.py`**

```python
"""Touch points that let other MUSE programs control and watch the bells.

Other programs reach this program with context.devices.get('school_bells').
program.json declares the touch points, and this module handles them.
"""
import os
import threading
import time
from datetime import date, datetime

import bells
import sounds

DAY_NAMES = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
_UNSET = object()


def to_bool(value):
    """Accept the loose forms MUSE and other programs might send for a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ('true', 'false', '1', '0'):
        return value.strip().lower() in ('true', '1')
    raise bells.ValidationError('enabled must be true or false, not %r' % (value,))


def to_volume(value):
    """Accept a whole number from 0 to 100, as a number or a numeric string."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    elif isinstance(value, str):
        try:
            value = int(value.strip())
        except ValueError:
            raise bells.ValidationError('master_volume must be a whole number from 0 to 100')
    return bells.check_volume(value, 'master_volume')


def sound_argument(args):
    """Return the sound name from a command's arguments: a map, a string, or a one-item list."""
    if isinstance(args, str):
        return args
    if isinstance(args, (list, tuple)) and len(args) == 1:
        return str(args[0])
    getter = getattr(args, 'get', None)
    if getter is not None:
        value = getter('sound')
        if value is not None:
            return str(value)
    raise bells.ValidationError('play needs a sound name')


def describe_next(next_bell):
    """Format bells.next_bell() output as 'Mon 11:00 Recess', or '' for no bell."""
    if next_bell is None:
        return ''
    day = DAY_NAMES[date.fromisoformat(next_bell['date']).weekday()]
    return ('%s %s %s' % (day, next_bell['time'], next_bell['label'])).strip()


class TouchPoints:
    def __init__(self, export, store, player, sounds_dir, log, clock=datetime.now):
        self._export = export
        self._store = store
        self._player = player
        self._sounds_dir = sounds_dir
        self._log = log
        self._clock = clock
        self._last_error = ''
        self._published = {}
        self._lock = threading.Lock()

    def handlers(self):
        """Return the set and command handlers that program.json names.

        These are plain functions, because MUSE counts parameters to decide how
        to call a handler, and a bound method's self would be counted.
        """
        def set_enabled(value):
            self._apply('enabled', lambda: self._store.set_settings({'enabled': to_bool(value)}))

        def set_master_volume(value):
            self._apply('master_volume',
                        lambda: self._store.set_settings({'master_volume': to_volume(value)}))

        def play_sound(args):
            self._apply('play', lambda: self._play(sound_argument(args)))

        def stop_sound():
            self._apply('stop', self._player.stop)

        return {'set_enabled': set_enabled, 'set_master_volume': set_master_volume,
                'play_sound': play_sound, 'stop_sound': stop_sound}

    def _apply(self, what, action):
        # Handlers never raise into MUSE; failures land in last_error.
        try:
            action()
        except Exception as e:
            self.error('%s failed: %s' % (what, e))
        self.publish()

    def _play(self, name):
        if not sounds.sound_exists(self._sounds_dir, name):
            raise bells.ValidationError('sound %s does not exist' % name)
        gain = self._store.get()['master_volume'] / 100
        self._player.play(os.path.join(self._sounds_dir, name), gain)

    def error(self, message):
        """Log message and publish it as last_error."""
        self._log.error(message)
        self._last_error = message
        self.publish()

    def bell_rang(self, bell):
        self._export.dispatch('bell_rang', {'id': bell['id'], 'label': bell['label'],
                                            'time': bell['time'], 'sound': bell['sound']})

    def values(self):
        state = self._store.get()
        return {
            'enabled': state['enabled'],
            'master_volume': state['master_volume'],
            'playing': self._player.playing or '',
            'next_bell': describe_next(bells.next_bell(state, self._clock())),
            'last_error': self._last_error,
        }

    def publish(self):
        """Send each param whose value changed since the last publish."""
        with self._lock:
            for name, value in self.values().items():
                if self._published.get(name, _UNSET) != value:
                    self._export.update(name, value)
                    self._published[name] = value

    def start(self):
        self.publish()
        self._export.online()
        threading.Thread(target=self._loop, daemon=True, name='bell-touchpoints').start()

    def _loop(self):
        while True:
            time.sleep(1.0)
            try:
                self.publish()
            except Exception as e:
                self._log.error('Touch-point publish failed: %r' % e)
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `.venv\Scripts\python -m pytest -q`
Expected: every test in the suite passes.

- [ ] **Step 6: Commit**

```powershell
git add school_bells/touchpoints.py tests/helpers.py tests/test_touchpoints.py
git commit -m "Add touch points for other MUSE programs"
```

---

### Task 8: Wire up `main.py` and smoke-test on the controller

**Files:**
- Modify: `school_bells/program.json` (replace it: `.metadata` form plus touch points)
- Modify: `school_bells/main.py` (replace the whole test-tone script)
- Create: `tools/tp_check/program.json`
- Create: `tools/tp_check/main.py`

**Interfaces:**
- Consumes: `bells.Store(path, log)`, `audio.Player(log)`, `touchpoints.TouchPoints(export, store, player, sounds_dir, log)` with `handlers()` and `start()`, `scheduler.Scheduler(store, player, sounds_dir, log, events=...)` with `start()`, `web.make_server(port, store, player, sounds_dir, static_dir, log)`, and the Phase 0 results in the spec.

- [ ] **Step 1: Replace `school_bells/program.json`**

```json
{
  "$schema": "https://developer.amx.com/schema/amx-mojo-program-1.0.json",
  ".metadata": {
    "id": "school_bells",
    "name": "school_bells",
    "provider": "python",
    "script": "main.py",
    "disabled": false,
    "description": "School bell scheduler: web page on port 8080, USB audio playback, and touch points"
  },
  "enabled": {
    ".kind": "param", ".type": "boolean",
    ".metadata": {"setter": "set_enabled", "desc": "Turns scheduled bells on or off"}
  },
  "master_volume": {
    ".kind": "param", ".type": "integer", ".min": 0, ".max": 100,
    ".metadata": {"setter": "set_master_volume", "desc": "Overall output level, 0 to 100"}
  },
  "playing": {".kind": "param", ".type": "string", ".access": "ro",
              ".metadata": {"desc": "Sound playing now, or empty"}},
  "next_bell": {".kind": "param", ".type": "string", ".access": "ro",
                ".metadata": {"desc": "Next bell, such as Mon 11:00 Recess, or empty"}},
  "last_error": {".kind": "param", ".type": "string", ".access": "ro",
                 ".metadata": {"desc": "Latest scheduled-bell or touch-point error"}},
  "play": {
    ".kind": "command",
    ".arguments": {"sound": {".type": "string"}},
    ".metadata": {"method": "play_sound", "desc": "Plays a stored sound at the master volume"}
  },
  "stop": {".kind": "command", ".metadata": {"method": "stop_sound", "desc": "Stops playback"}},
  "bell_rang": {
    ".kind": "event",
    ".arguments": {"id": {".type": "string"}, "label": {".type": "string"},
                   "time": {".type": "string"}, "sound": {".type": "string"}}
  }
}
```

- [ ] **Step 2: Replace `school_bells/main.py`**

Set `DATA_DIR` from the spec's Phase 0 results. If the program folder keeps files across a reload and a reboot, keep the line below. Otherwise, replace the right side with the recorded folder plus `/school_bells`, as a string.

```python
import os
import sys
import threading

from mojo import context

HERE = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
sys.path.insert(0, HERE)

import audio  # noqa: E402
import bells  # noqa: E402
import scheduler  # noqa: E402
import touchpoints  # noqa: E402
import web  # noqa: E402

log = context.log
PORT = 8080
DATA_DIR = os.path.join(HERE, 'data')  # set from the spec's Phase 0 results
SOUNDS_DIR = os.path.join(DATA_DIR, 'sounds')
os.makedirs(SOUNDS_DIR, exist_ok=True)

store = bells.Store(os.path.join(DATA_DIR, 'bells.json'), log)
player = audio.Player(log)
touch = touchpoints.TouchPoints(context.export, store, player, SOUNDS_DIR, log)
globals().update(touch.handlers())  # MUSE finds program.json's setters and methods here
scheduler.Scheduler(store, player, SOUNDS_DIR, log, events=touch).start()
server = web.make_server(PORT, store, player, SOUNDS_DIR, os.path.join(HERE, 'static'), log)
threading.Thread(target=server.serve_forever, daemon=True, name='bell-web').start()
touch.start()
log.info('School bells running on port %d, data in %s' % (PORT, DATA_DIR))

# leave this as the last line in the Python script
context.run(globals())
```

- [ ] **Step 3: Write the touch-point check program**

`tools/tp_check/program.json`:
```json
{
  "$schema": "https://developer.amx.com/schema/amx-mojo-program-1.0.json",
  ".metadata": {
    "id": "tp_check",
    "name": "tp_check",
    "provider": "python",
    "script": "main.py",
    "disabled": false,
    "description": "Diagnostic: reads, watches, and drives the school_bells touch points"
  }
}
```

`tools/tp_check/main.py`:
```python
"""Checks the school_bells touch points from a second program.

Load this program while school_bells is running, with tone.wav uploaded.
"""
from mojo import context

log = context.log
device = context.devices.get('school_bells')

for name in ('enabled', 'master_volume', 'playing', 'next_bell', 'last_error'):
    try:
        log.info('%s = %r' % (name, getattr(device, name).value))
    except Exception as e:
        log.error('Reading %s failed: %r' % (name, e))

device.playing.watch(lambda event: log.info('playing -> %r' % event.newValue))
device.last_error.watch(lambda event: log.info('last_error -> %r' % event.newValue))
device.listen('bell_rang', lambda event: log.info('bell_rang %r' % event.arguments))

try:
    device.play('tone.wav')
    log.info('Sent play tone.wav')
except Exception as e:
    log.error('play command failed: %r' % e)

# leave this as the last line in the Python script
context.run(globals())
```

- [ ] **Step 4: Check the JSON files and run the suite**

Run:
```powershell
.venv\Scripts\python -c "import json; [json.load(open(p)) for p in ('school_bells/program.json', 'tools/tp_check/program.json')]"
.venv\Scripts\python -m pytest -q
```
Expected: no output from the first command, and every test passes.

- [ ] **Step 5: Commit**

```powershell
git add school_bells/program.json school_bells/main.py tools/tp_check
git commit -m "Run the bell scheduler, web server, and touch points from main.py"
```

- [ ] **Step 6: Make a test sound on the PC**

Run:
```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, 'tests'); from helpers import make_wav; open('tone.wav', 'wb').write(make_wav(2.0, tone_hz=1000))"
```

- [ ] **Step 7: Smoke-test on the controller (the user loads the programs)**

Ask the user to load the `school_bells` folder as a program, attach to it, and confirm that `School bells running on port 8080` appears. Then run, replacing `<controller-ip>`:
```powershell
$CTRL = "http://<controller-ip>:8080"
curl.exe -s "$CTRL/api/state"
curl.exe -s -X POST --data-binary "@tone.wav" -H "Content-Type: audio/wav" "$CTRL/api/sounds?name=tone.wav"
curl.exe -s -X POST -H "Content-Type: application/json" -d '{\"sound\": \"tone.wav\"}' "$CTRL/api/play"
```
Expected: the state JSON has the controller's time, the upload returns `{"name": "tone.wav", "seconds": 2.0}`, and the user hears a 2-second tone at 80% volume. Play it again, call `/api/stop` during playback, and confirm the tone cuts off.

Then schedule a bell two minutes ahead of the controller time shown in the state (example for 10:54 on a Monday):
```powershell
curl.exe -s -X PUT -H "Content-Type: application/json" -d '{\"bells\": [{\"label\": \"Test\", \"time\": \"10:54\", \"days\": [\"mon\"], \"sound\": \"tone.wav\", \"volume\": 100}]}' "$CTRL/api/bells"
```
Expected: the tone plays once at that minute, and the log shows `Rang bell "Test" at 10:54`.

Finally, ask the user to load the `tools/tp_check` folder as a program and paste its output. Expected:
- It logs the five param values, including `next_bell` and `master_volume = 80`.
- It logs `playing -> 'tone.wav'` and the tone plays.
- `playing` returns to `''` when the tone ends.

Schedule another bell two minutes ahead with the same `curl.exe` command and confirm `tp_check` logs `bell_rang`. If any step fails, record the exact output in the ledger before changing code.

- [ ] **Step 8: Remove the test sound file**

```powershell
Remove-Item tone.wav
```

---

### Task 9: The bell page (`school_bells/static/index.html`)

Steps 1 to 3 build a working, plainly styled page with the full behavior. Step 4 restyles it to match the Claude Design export. **Step 4 is blocked until the user exports the design into `design/`.**

**Files:**
- Create: `tools/dev_server.py`
- Create: `school_bells/static/index.html`

**Interfaces:**
- Consumes: the Web API from Task 6.
- Produces: the page's DOM contract, which Step 4 must keep:
  - IDs: `clock`, `enabled`, `master-volume`, `master-volume-value`, `stop`, `now-playing`, `error-banner` (containing `[data-field=message]`), `error-close`, `next-bell`, `add-bell`, `bell-list`, `upload-input`, `upload-button`, `upload-status`, `sound-list`.
  - Templates:
    - `#bell-row`: fields `time`, `label`, `days`, `sound`, and `volume`; actions `play`, `edit`, and `delete`.
    - `#bell-editor`: a `<form>` with inputs named `time`, `label`, `day` (seven checkboxes with values `mon` to `sun`), `sound` (a select), and `volume` (a range); a `[data-field=volume-value]`; and actions `save` (submit) and `cancel`.
    - `#sound-row`: fields `name` and `duration`; actions `play` and `delete`.
  - The `missing` class goes on a bell row whose sound is missing.

- [ ] **Step 1: Write the dev server**

`tools/dev_server.py`:
```python
"""Runs the bell web server on this PC with a fake player, for working on the page.

To use it, run `.venv\Scripts\python tools/dev_server.py`, then open http://localhost:8080/.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAM = os.path.join(ROOT, 'school_bells')
sys.path.insert(0, PROGRAM)

import bells  # noqa: E402
import web  # noqa: E402


class PrintLog:
    def info(self, message):
        print(message)

    def error(self, message):
        print('ERROR', message)


class PrintPlayer:
    playing = None

    def play(self, path, gain):
        print('PLAY %s at gain %.2f' % (path, gain))
        self.playing = os.path.basename(path)

    def stop(self):
        print('STOP')
        self.playing = None


data_dir = os.path.join(tempfile.gettempdir(), 'school_bells_dev')
sounds_dir = os.path.join(data_dir, 'sounds')
os.makedirs(sounds_dir, exist_ok=True)
log = PrintLog()
store = bells.Store(os.path.join(data_dir, 'bells.json'), log)
server = web.make_server(8080, store, PrintPlayer(), sounds_dir, os.path.join(PROGRAM, 'static'), log)
print('Open http://localhost:8080/ (data in %s)' % data_dir)
server.serve_forever()
```

- [ ] **Step 2: Write the working page**

`school_bells/static/index.html`:
```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>School Bells</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 0 auto; max-width: 960px; padding: 16px; }
  [hidden] { display: none !important; }
  .bell-row, .sound-row, .bell-editor { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 6px 0; }
  .missing { color: #b00020; }
  #error-banner { background: #fde7e9; color: #b00020; padding: 8px 12px; }
</style>
</head>
<body>
<header>
  <h1>School Bells</h1>
  <p>Controller time: <span id="clock">—</span></p>
  <label><input type="checkbox" id="enabled"> Bells enabled</label>
  <label>Master volume <input type="range" id="master-volume" min="0" max="100">
    <span id="master-volume-value"></span>%</label>
  <button id="stop" type="button">Stop</button>
  <span id="now-playing" hidden></span>
</header>
<div id="error-banner" role="alert" hidden>
  <span data-field="message"></span>
  <button id="error-close" type="button" aria-label="Dismiss">✕</button>
</div>
<section><p id="next-bell"></p></section>
<section>
  <h2>Bells</h2>
  <button id="add-bell" type="button">+ Add bell</button>
  <div id="bell-list"></div>
</section>
<section>
  <h2>Sounds</h2>
  <input type="file" id="upload-input" accept="audio/*" hidden>
  <button id="upload-button" type="button">Upload sound</button>
  <span id="upload-status"></span>
  <div id="sound-list"></div>
</section>
<footer>This page has no login. Keep it on a restricted network.</footer>

<template id="bell-row">
  <div class="bell-row">
    <span data-field="time"></span>
    <span data-field="label"></span>
    <span data-field="days"></span>
    <span data-field="sound"></span>
    <span data-field="volume"></span>
    <button type="button" data-action="play" aria-label="Play">▶</button>
    <button type="button" data-action="edit" aria-label="Edit">✎</button>
    <button type="button" data-action="delete" aria-label="Delete">✕</button>
  </div>
</template>
<template id="bell-editor">
  <form class="bell-editor">
    <input name="time" type="time" required>
    <input name="label" type="text" maxlength="60" placeholder="Label">
    <label><input type="checkbox" name="day" value="mon">Mon</label>
    <label><input type="checkbox" name="day" value="tue">Tue</label>
    <label><input type="checkbox" name="day" value="wed">Wed</label>
    <label><input type="checkbox" name="day" value="thu">Thu</label>
    <label><input type="checkbox" name="day" value="fri">Fri</label>
    <label><input type="checkbox" name="day" value="sat">Sat</label>
    <label><input type="checkbox" name="day" value="sun">Sun</label>
    <select name="sound" required></select>
    <input name="volume" type="range" min="0" max="100">
    <span><span data-field="volume-value"></span>%</span>
    <button type="submit" data-action="save">Save</button>
    <button type="button" data-action="cancel">Cancel</button>
  </form>
</template>
<template id="sound-row">
  <div class="sound-row">
    <span data-field="name"></span>
    <span data-field="duration"></span>
    <button type="button" data-action="play">▶ Play</button>
    <button type="button" data-action="delete" aria-label="Delete">✕</button>
  </div>
</template>

<script>
const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
const DAY_LETTERS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const $ = (selector, root = document) => root.querySelector(selector);

let state = null;
let editingId = null;  // id of the bell being edited, 'new' for a new bell, or null
let clockBase = null;  // { serverMs, localMs, offsetMs } from the latest state

async function api(method, path, body, contentType) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.body = contentType ? body : JSON.stringify(body);
    options.headers['Content-Type'] = contentType || 'application/json';
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `${response.status} ${response.statusText}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function showError(message) {
  $('#error-banner [data-field=message]').textContent = message;
  $('#error-banner').hidden = false;
}

async function run(action) {
  try {
    await action();
  } catch (error) {
    showError(error.message);
  }
}

async function refresh() {
  state = await api('GET', '/api/state');
  const match = state.time.match(/([+-])(\d\d):(\d\d)$/);
  const offsetMs = match
    ? (match[1] === '-' ? -1 : 1) * (Number(match[2]) * 60 + Number(match[3])) * 60000
    : 0;
  clockBase = { serverMs: Date.parse(state.time), localMs: Date.now(), offsetMs };
  render();
}

// Controller wall-clock time, as a Date whose UTC fields hold the controller's local fields.
function controllerNow() {
  return new Date(clockBase.serverMs + (Date.now() - clockBase.localMs) + clockBase.offsetMs);
}

function dayName(day) {
  return day[0].toUpperCase() + day.slice(1);
}

function renderClock() {
  if (!clockBase) return;
  const now = controllerNow();
  $('#clock').textContent = `${dayName(DAYS[(now.getUTCDay() + 6) % 7])} ${now.toISOString().slice(11, 19)}`;
  renderNextBell(now);
}

function renderNextBell(now) {
  const next = state.next_bell;
  if (!next) {
    $('#next-bell').textContent = state.enabled ? 'No bells scheduled' : 'Bells are off';
    return;
  }
  const [y, m, d] = next.date.split('-').map(Number);
  const [hh, mm] = next.time.split(':').map(Number);
  const minutes = Math.ceil((Date.UTC(y, m - 1, d, hh, mm) - now.getTime()) / 60000);
  let when;
  if (minutes < 60) when = `in ${minutes} min`;
  else if (minutes < 24 * 60) when = `in ${Math.floor(minutes / 60)} h ${minutes % 60} min`;
  else when = `on ${dayName(DAYS[(new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7])}`;
  $('#next-bell').textContent = `Next bell: ${next.time} ${next.label} — ${when}`;
}

function render() {
  $('#enabled').checked = state.enabled;
  if (document.activeElement !== $('#master-volume')) {
    $('#master-volume').value = state.master_volume;
    $('#master-volume-value').textContent = state.master_volume;
  }
  $('#now-playing').hidden = !state.playing;
  $('#now-playing').textContent = state.playing ? `Now playing: ${state.playing}` : '';
  $('#stop').disabled = !state.playing;
  renderClock();
  if (editingId === null) renderBells();
  renderSounds();
}

function fill(templateSelector, fields) {
  const node = $(templateSelector).content.firstElementChild.cloneNode(true);
  for (const [name, value] of Object.entries(fields)) {
    const element = node.querySelector(`[data-field="${name}"]`);
    if (element) element.textContent = value;
  }
  return node;
}

function makeBellRow(bell) {
  const row = fill('#bell-row', {
    time: bell.time,
    label: bell.label,
    days: DAYS.map((day, i) => (bell.days.includes(day) ? DAY_LETTERS[i] : '·')).join(' '),
    sound: bell.missing_sound ? `${bell.sound} (missing)` : bell.sound,
    volume: `${bell.volume}%`,
  });
  row.classList.toggle('missing', bell.missing_sound);
  row.querySelector('[data-action=play]').onclick = () => run(() => play(bell.sound, bell.volume));
  row.querySelector('[data-action=edit]').onclick = () => openEditor(bell.id);
  row.querySelector('[data-action=delete]').onclick = () => run(() => deleteBell(bell));
  return row;
}

function makeEditor(bell) {
  const form = $('#bell-editor').content.firstElementChild.cloneNode(true);
  const draft = bell || { label: '', time: '08:00', days: DAYS.slice(0, 5), sound: '', volume: 100 };
  form.elements.time.value = draft.time;
  form.elements.label.value = draft.label;
  form.querySelectorAll('input[name=day]').forEach((box) => { box.checked = draft.days.includes(box.value); });
  const select = form.elements.sound;
  select.replaceChildren(...state.sounds.map((s) => new Option(s.name, s.name, false, s.name === draft.sound)));
  const volumeValue = form.querySelector('[data-field=volume-value]');
  form.elements.volume.value = draft.volume;
  volumeValue.textContent = draft.volume;
  form.elements.volume.oninput = () => { volumeValue.textContent = form.elements.volume.value; };
  form.querySelector('[data-action=cancel]').onclick = () => { editingId = null; renderBells(); };
  form.onsubmit = (event) => {
    event.preventDefault();
    const edited = {
      id: bell ? bell.id : undefined,
      label: form.elements.label.value.trim(),
      time: form.elements.time.value,
      days: [...form.querySelectorAll('input[name=day]:checked')].map((box) => box.value),
      sound: select.value,
      volume: Number(form.elements.volume.value),
    };
    const others = state.bells.filter((b) => !bell || b.id !== bell.id);
    run(async () => {
      await saveBells([...others, edited]);
      editingId = null;
      await refresh();
    });
  };
  return form;
}

function renderBells() {
  const rows = state.bells.map((bell) => (bell.id === editingId ? makeEditor(bell) : makeBellRow(bell)));
  if (editingId === 'new') rows.push(makeEditor(null));
  $('#bell-list').replaceChildren(...rows);
}

function openEditor(id) {
  editingId = id;
  renderBells();
}

function saveBells(list) {
  return api('PUT', '/api/bells', { bells: list.map(({ missing_sound, ...bell }) => bell) });
}

async function deleteBell(bell) {
  if (!confirm(`Delete the ${bell.time} ${bell.label} bell?`)) return;
  await saveBells(state.bells.filter((b) => b.id !== bell.id));
  await refresh();
}

function formatDuration(seconds) {
  if (seconds === null) return 'unreadable';
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function renderSounds() {
  $('#sound-list').replaceChildren(...state.sounds.map((sound) => {
    const row = fill('#sound-row', { name: sound.name, duration: formatDuration(sound.seconds) });
    row.querySelector('[data-action=play]').onclick = () => run(() => play(sound.name));
    row.querySelector('[data-action=delete]').onclick = () => run(() => deleteSound(sound.name));
    return row;
  }));
}

async function play(sound, volume) {
  await api('POST', '/api/play', volume === undefined ? { sound } : { sound, volume });
  await refresh();
}

async function deleteSound(name) {
  if (!confirm(`Delete ${name}?`)) return;
  await api('DELETE', `/api/sounds/${encodeURIComponent(name)}`);
  await refresh();
}

function soundName(fileName) {
  const base = fileName.replace(/\.[^.]*$/, '').replace(/[^A-Za-z0-9 _.\-]/g, '_')
    .replace(/^[ .]+/, '').slice(0, 76);
  return `${base || 'sound'}.wav`;
}

async function convertToWav(file) {
  const context = new (window.AudioContext || window.webkitAudioContext)();
  let decoded;
  try {
    decoded = await context.decodeAudioData(await file.arrayBuffer());
  } catch {
    throw new Error(`Your browser can't decode ${file.name}. Try an MP3 or WAV file.`);
  } finally {
    context.close();
  }
  const offline = new OfflineAudioContext(2, Math.ceil(decoded.duration * 48000), 48000);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  return encodeWav(await offline.startRendering());
}

function encodeWav(buffer) {
  const frames = buffer.length;
  const dataBytes = frames * 4;
  const view = new DataView(new ArrayBuffer(44 + dataBytes));
  const text = (offset, s) => { for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i)); };
  text(0, 'RIFF'); view.setUint32(4, 36 + dataBytes, true); text(8, 'WAVE');
  text(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 2, true);
  view.setUint32(24, 48000, true); view.setUint32(28, 48000 * 4, true);
  view.setUint16(32, 4, true); view.setUint16(34, 16, true);
  text(36, 'data'); view.setUint32(40, dataBytes, true);
  const left = buffer.getChannelData(0);
  const right = buffer.getChannelData(1);
  const sample = (v) => { const c = Math.max(-1, Math.min(1, v)); return c < 0 ? c * 0x8000 : c * 0x7fff; };
  for (let i = 0, offset = 44; i < frames; i++, offset += 4) {
    view.setInt16(offset, sample(left[i]), true);
    view.setInt16(offset + 2, sample(right[i]), true);
  }
  return new Blob([view.buffer], { type: 'audio/wav' });
}

async function upload(file) {
  const status = $('#upload-status');
  try {
    status.textContent = 'Converting…';
    const wav = await convertToWav(file);
    if (wav.size > MAX_UPLOAD_BYTES) {
      throw new Error(`${file.name} is too long. Sounds are limited to 50 MB, about 4½ minutes.`);
    }
    const name = soundName(file.name);
    const path = `/api/sounds?name=${encodeURIComponent(name)}`;
    status.textContent = 'Uploading…';
    try {
      await api('POST', path, wav, 'audio/wav');
    } catch (error) {
      if (error.status !== 409) throw error;
      if (!confirm(`${name} already exists. Replace it?`)) return;
      await api('POST', `${path}&overwrite=1`, wav, 'audio/wav');
    }
    await refresh();
  } finally {
    status.textContent = '';
  }
}

$('#enabled').onchange = () => run(async () => {
  await api('PUT', '/api/settings', { enabled: $('#enabled').checked });
  await refresh();
});
$('#master-volume').oninput = () => { $('#master-volume-value').textContent = $('#master-volume').value; };
$('#master-volume').onchange = () => run(async () => {
  await api('PUT', '/api/settings', { master_volume: Number($('#master-volume').value) });
  await refresh();
});
$('#stop').onclick = () => run(async () => { await api('POST', '/api/stop', {}); await refresh(); });
$('#add-bell').onclick = () => openEditor('new');
$('#error-close').onclick = () => { $('#error-banner').hidden = true; };
$('#upload-button').onclick = () => $('#upload-input').click();
$('#upload-input').onchange = () => {
  const file = $('#upload-input').files[0];
  $('#upload-input').value = '';
  if (file) run(() => upload(file));
};

run(refresh);
setInterval(() => { if (!document.hidden) run(refresh); }, 2000);
setInterval(renderClock, 1000);
</script>
</body>
</html>
```

- [ ] **Step 3: Check the page on the PC**

Run: `.venv\Scripts\python tools/dev_server.py`, then open `http://localhost:8080/` and confirm each item:
1. The clock ticks every second and matches the PC's time.
2. Upload an MP3. The page shows "Converting…" and then "Uploading…", and the sound appears with the right duration.
3. Add a bell for Monday to Friday at 11:00 with that sound. It appears with `M T W T F · ·`, and "Next bell" updates.
4. Add a second bell at 11:00 on Wednesday. A banner reports the clash.
5. Delete the sound while a bell uses it. A banner names the bell.
6. Press ▶ on a bell and on a sound. The dev server prints `PLAY ... at gain 0.xx`, with the bell's volume included only for the bell.
7. In the browser's dev tools, at 375 px wide, nothing scrolls sideways.

- [ ] **Step 4: Restyle to match the design export (blocked until `design/` exists)**

1. Open the exported files in `design/`.
2. Rewrite the markup and `<style>` in `school_bells/static/index.html` to match the design's layout, colors, type, and spacing.
3. Keep the `<script>` block exactly as written, and keep every part of the DOM contract in this task's Interfaces. Inline all CSS and any icons as SVG.
4. Remove anything that loads from the network, then confirm nothing remains:

```powershell
Select-String -Path school_bells/static/index.html -Pattern '<link|src=|@import|url\(http|https?://'
```
Expected: no matches.

- [ ] **Step 5: Recheck the page on the PC**

Repeat every check in Step 3 against the restyled page.

- [ ] **Step 6: Run the spec's controller checklist (the user loads the program)**

Load the program and work through the spec's controller checks:
1. The page loads from a LAN PC and a phone.
2. Upload an MP3 and confirm it plays.
3. Set a bell two minutes ahead and confirm it rings once.
4. Reload the program inside that bell's minute and confirm it doesn't ring twice.
5. Change master and per-bell volume and confirm the level changes.
6. Confirm stop works.
7. Reboot and confirm the bells and sounds are still there.
8. Load `tools/tp_check` and confirm it reads the params, plays a sound with the `play` command, and logs `bell_rang` when a bell rings.

- [ ] **Step 7: Commit**

```powershell
git add school_bells/static/index.html tools/dev_server.py design
git commit -m "Add the bell page"
```
