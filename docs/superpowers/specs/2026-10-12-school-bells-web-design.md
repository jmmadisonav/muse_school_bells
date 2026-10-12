# School bells web scheduler: design

Date: 2026-10-12
Status: Approved 2026-10-12

## Goal

Staff open a web page served by the `school_bells` program on the AMX Muse
controller. From that page they schedule bells by time and weekday, upload
sounds, test-play sounds, and set volume. Bells play automatically through the
USB audio adapter with nobody at the page.

### Success criteria

- Each scheduled bell rings once, at its set minute, on its ticked weekdays.
- Uploads and the schedule survive a controller reboot and a program reload.
- Staff can upload MP3, WAV, M4A, or any other format their browser can decode.
- Staff can play any sound on demand, stop playback, and set master and
  per-bell volume.

## Background

Probes on 2026-10-12 established these facts about the controller:

- The Muse kernel has no sound support (`# CONFIG_SOUND is not set`), so ALSA
  and any package built on it can't work.
- Programs run as uid 998, which can read and write the adapter's
  `/dev/bus/usb` node. `/lib/libusb-1.0.so.0` is present.
- The pip package `libusb1` streams audio to the adapter over isochronous
  transfers. A 3-second 48 kHz, 16-bit stereo tone played cleanly, with 0 failed
  transfers.
- Adapter: Unitek Y-247A (C-Media `0d8c:0014`), interface 1 alt 1, endpoint
  `0x01`, 48000 or 44100 Hz, 16-bit stereo, max packet 200 bytes.
- Python is 3.10.13 on aarch64.

## Decisions

| Topic | Decision |
|---|---|
| Web server | Python standard library `http.server.ThreadingHTTPServer`. No framework. |
| Schedule model | One weekday timetable. Each bell has a time, weekdays, a sound, and a volume. A master switch turns all scheduled bells on or off. |
| Access control | None. The page is for a restricted network, and its footer says so. |
| Audio formats | The browser converts uploads to 48 kHz, 16-bit stereo WAV before sending them. The controller stores and plays only that format. |
| Playback controls | Play any sound now, stop, per-bell volume, and master volume. |
| Program folder | The deployable program lives in `school_bells/`, named for its program ID. Loading a program uploads its whole folder, so tests, docs, and tools stay outside it. |
| Other MUSE programs | Other programs control and watch the bells through touch points declared in `program.json`. See [Touch points](#touch-points). |

## Phase 0: controller environment probe

Before building, a probe program in `tools/env_probe/` answers these questions
on the controller. It's a separate program, so loading it leaves the bell
program untouched.

1. Can a program listen on TCP port 8080, and can a PC on the LAN reach it?
2. Which directory is writable and survives both a reboot and a program
   reload? Candidates are the program directory, `$HOME`, and anything under
   `/mnt` or `/data`. The probe writes a marker file to each, and you check
   for it after a reload and after a reboot.
3. How much free space does that directory have?
4. What are the controller's local time, time zone, and UTC offset? Is NTP
   configured?

If any answer blocks this design, for example if no port is reachable, stop
and revise the design before building.

## Architecture

### Repository layout

```
school_bells/                 repository (never loaded to the controller)
├─ school_bells/              the MUSE program: load this folder
│  ├─ program.json            program metadata and touch points
│  ├─ main.py  bells.py  sounds.py  audio.py  scheduler.py  web.py  touchpoints.py
│  ├─ static/index.html
│  └─ requirements.txt
├─ tools/
│  ├─ usb_probe/              USB diagnostic program (program.json + main.py)
│  ├─ env_probe/              Phase 0 probe program
│  └─ dev_server.py           runs the web server on the PC with a fake player
├─ tests/  docs/  design/
└─ pyproject.toml             points pytest at school_bells/ and tests/
```

### Program modules

All modules below live in `school_bells/`.

| File | Responsibility |
|---|---|
| `main.py` | Loads state, starts the web server, scheduler, and touch points, adds the touch-point handlers to its globals, then calls `context.run(globals())`. |
| `audio.py` | Owns the USB adapter. `Player.play(path, volume)` and `Player.stop()`. Plays one sound at a time on a worker thread; a new `play` stops the current sound. Streams WAV files in chunks with the standard `wave` module. Applies gain with `audioop.mul`, which is available in Python 3.10. |
| `bells.py` | Pure logic with no USB or web code: bell validation, the bell list and settings, loading and saving `bells.json`, and finding which bells are due. |
| `scheduler.py` | A thread that runs once per second, asks `bells.py` which bells are due, and calls `Player.play`. |
| `web.py` | The HTTP server, static file serving, and the JSON API. |
| `static/index.html` | The single page: HTML, CSS, and vanilla JavaScript in one file. |
| `touchpoints.py` | Handles sets and commands from other MUSE programs, publishes param changes, and dispatches the `bell_rang` event. Talks to MUSE only through the `context.export` object it's given, so tests can pass a fake. |

### Configuration

Two constants at the top of `main.py` hold the settings:

| Constant | Value | Purpose |
|---|---|---|
| `PORT` | `8080` | Web server port. |
| `DATA_DIR` | Set from the Phase 0 result | Folder for `bells.json` and `sounds/`. |

The program doesn't use `envvars`, because the extension project only verified
the `.metadata` form of `program.json`, and `envvars` haven't been tested in it.

## Data

`bells.json` lives in the data folder:

```json
{
  "enabled": true,
  "master_volume": 80,
  "bells": [
    {"id": "b1", "label": "Start of day", "time": "08:45",
     "days": ["mon", "tue", "wed", "thu", "fri"], "sound": "start.wav", "volume": 100}
  ]
}
```

- `id`: a short random string assigned by the server when a bell is created.
- `time`: 24-hour `HH:MM`.
- `days`: any of `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun`.
- `volume` and `master_volume`: integers from 0 to 100.
- Saves write to `bells.json.tmp` and then rename it over `bells.json`, so a
  power cut can't leave a half-written file.
- If `bells.json` is missing, the program starts with an empty, enabled
  schedule. If the file is unreadable, the program logs an error, keeps a copy
  as `bells.json.bad`, and starts empty.

Sounds are stored in `<data>/sounds/<name>.wav`.

## Scheduling rules

- Bells follow the controller's local clock.
- A bell is due when the current local weekday is in its `days`, the current
  `HH:MM` equals its `time`, and it hasn't already rung for that date.
- The scheduler records `(bell id, date)` after each ring. This record lives in
  memory only.
- On startup, the scheduler marks every bell whose time equals the current
  minute as already rung, so a restart can't ring a bell twice.
- Missed bells are never rung late. This covers the controller being off and
  the clock jumping forward.
- If the clock jumps back, the `(bell id, date)` record stops a bell ringing a
  second time.
- When the master switch is off, the scheduler rings nothing. Manual play still
  works.
- The API rejects a bell list where two bells share a time and a weekday, so
  no two scheduled bells can clash.
- If a due bell's sound file is missing, the scheduler logs an error and skips
  that bell.
- Gain is `master_volume / 100 × bell volume / 100`. Manual play of a sound
  from the sounds list uses the master volume only.

## Web API

All bodies are JSON unless stated otherwise. Errors return a 4xx status with
`{"error": "<message for staff>"}`.

| Method and path | Purpose |
|---|---|
| `GET /` | Serves `static/index.html`. |
| `GET /api/state` | Returns the controller time (ISO with offset) and weekday, `enabled`, `master_volume`, `bells` (each with `missing_sound: bool`), `sounds` (name and duration in seconds), `playing` (sound name or `null`), and `next_bell` (id and time, or `null`). |
| `PUT /api/bells` | Replaces the whole bell list. Assigns ids to new bells. Validates time format, days, volume, that each sound exists, and that no bells clash. |
| `PUT /api/settings` | Sets `enabled` and `master_volume`. |
| `POST /api/sounds?name=<name>` | The body is WAV bytes. The server rejects files that aren't 48 kHz, 16-bit, 2-channel PCM or that are larger than 50 MB. Names may use letters, digits, spaces, `_`, `-`, and `.`, and must end in `.wav`. An existing name returns 409 unless `overwrite=1` is set. |
| `DELETE /api/sounds/<name>` | Deletes a sound. Returns 409, naming the bells that use the sound, if any bell uses it. |
| `POST /api/play` | Body `{"sound": "<name>", "volume": 0-100}`. Volume is optional; without it, playback uses the master volume only. |
| `POST /api/stop` | Stops playback. |

The page polls `GET /api/state` every 2 seconds to update the clock, the
"Now playing" indicator, and the next bell.

## Touch points

Other MUSE programs on the controller reach the bell program with
`context.devices.get('school_bells')`. The touch points follow the conventions
that the `muse_control_extension` project verified on firmware v1.4.118.

### Declaration

`program.json` puts the program's details under `.metadata`, and declares each
touch point as a top-level key. The `id` and `name` are both `school_bells`,
matching the folder name.

| Touch point | Kind | Handler | Behavior |
|---|---|---|---|
| `enabled` | Param, `boolean` | setter `set_enabled` | Turns scheduled bells on or off. |
| `master_volume` | Param, `integer`, 0 to 100 | setter `set_master_volume` | Sets the overall output level. |
| `playing` | Param, `string`, read-only | | The sound playing now, or `""`. |
| `next_bell` | Param, `string`, read-only | | The next bell as `Mon 11:00 Recess`, or `""` when none is due. |
| `last_error` | Param, `string`, read-only | | The latest error from a scheduled bell or a touch-point command. |
| `play` | Command, one argument `sound` (`string`) | method `play_sound` | Plays a stored sound at the master volume. |
| `stop` | Command, no arguments | method `stop_sound` | Stops playback. |
| `bell_rang` | Event with `id`, `label`, `time`, and `sound` | | Fires each time the schedule rings a bell. |

### Rules

- Handler names are distinct from the touch-point names (`play_sound`, not
  `play`), so they can't clash with other names in `main.py`'s globals.
- Commands take at most one argument. MUSE passes command arguments by
  position, and the order of multiple arguments hasn't been verified.
- MUSE calls a command handler with one argument: the argument map, or the
  value itself. `play_sound` accepts a map with a `sound` key, a plain string,
  or a one-item list.
- Set handlers accept loosely typed values: `enabled` accepts `true`, `false`,
  `1`, `0`, and the strings `"true"` and `"false"`. `master_volume` accepts any
  whole number from 0 to 100, including a numeric string.
- A handler never raises into MUSE. An invalid value or a failed play is
  logged and stored in `last_error`.
- The program publishes each param when its value changes, whether the change
  came from a touch point, the web page, or the schedule. It checks for changes
  once per second.
- At startup, the program publishes every param and then calls
  `context.export.online()`.

## Page

The page's visual design comes from the Claude Design project at
<https://claude.ai/design/p/4dacea54-3051-4d92-908a-8b172fbad2f7>, exported
into `design/` in this folder. `static/index.html` matches that design and
stays one self-contained file with no external scripts, fonts, or stylesheets,
because staff browsers might not have internet access. Where the design and
this section differ on behavior, this section wins. Where they differ on
look, the design wins.

The wireframe below sets the content and behavior.

```
┌──────────────────────────────────────────────────────────────┐
│ School Bells        Controller time: Mon 10:52:07            │
│ [■ Bells enabled]   Master volume [━━━━━━━●━━] 80%  [■ Stop] │
├──────────────────────────────────────────────────────────────┤
│ Next bell: 11:00  Recess        ▸ in 7 min                   │
├──────────────────────────────────────────────────────────────┤
│ BELLS                                          [+ Add bell]  │
│ 08:45  Start of day   M T W T F   start.wav  100%  [▶] [✎] [✕]│
│ 11:00  Recess         M T W T F   recess.wav  90%  [▶] [✎] [✕]│
├──────────────────────────────────────────────────────────────┤
│ SOUNDS                                    [⇪ Upload sound]   │
│ start.wav     0:04   [▶ Play]  [✕]                           │
└──────────────────────────────────────────────────────────────┘
  This page has no login. Keep it on a restricted network.
```

- The bell list is sorted by time. A bell with a missing sound is flagged.
- **▶** on a bell row plays that bell's sound at its own volume.
- **✎** and **+ Add bell** open an inline editor with a time picker, weekday
  checkboxes, a sound dropdown, and a volume slider.
- The master volume and the enabled switch save as soon as you change them.
- Uploading converts in the browser:
  1. `AudioContext.decodeAudioData` decodes the file.
  2. `OfflineAudioContext` at 48000 Hz with 2 channels resamples it.
  3. The page encodes the result as 16-bit PCM WAV and posts it.

  The page shows "Converting…" and then "Uploading…" while this happens. If
  the browser can't decode a file, the page says so.
- Errors from the API appear in a banner at the top of the page.
- The page works at phone width, so staff can use it from a phone on the
  school network.

## Error handling

- If the adapter is unplugged or fails to open, the error is logged and
  returned to the page for manual plays. The scheduler logs it and moves on,
  and the next play tries to open the adapter again.
- An exception in one bell's playback never stops the scheduler or the web
  server threads.
- The web server logs each request's method, path, and status.

## Testing

- **On the PC:** run unit tests with `pytest` from the repository's `.venv`.
  They cover:
  - `bells.py`: due-bell logic, including the restart, clock-jump, master-switch,
    and clash rules; validation; and atomic save and load.
  - WAV validation and gain.
  - The web API, run against a fake `Player` on a local port.
  - The touch-point handlers and publishing, run against a fake
    `context.export`.
- **On the controller,** check manually:
  1. The page loads from a LAN PC and a phone.
  2. Upload an MP3 and confirm it plays.
  3. Set a bell two minutes ahead and confirm it rings once.
  4. Reload the program inside that bell's minute and confirm it doesn't ring
     twice.
  5. Change master and per-bell volume and confirm the level changes.
  6. Confirm stop works.
  7. Reboot and confirm the bells and sounds are still there.
  8. Load the `tools/tp_check/` program and confirm it reads the params, plays
     a sound with the `play` command, and logs `bell_rang` when a bell rings.

## Out of scope

- Login or user accounts.
- Multiple named timetables, term dates, and holiday calendars.
- Playing two sounds at once.
- Editing or trimming audio in the page.
