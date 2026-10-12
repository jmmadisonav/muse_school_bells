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
| Page design | Today tab built from the Claude Design handoff; Schedules and Device tabs in the same MGE style. See [Page](#page). |
| Ring now | Plays the next scheduled bell's sound at its volume. |
| Hold | Hold pauses scheduled bells until midnight; the separate on/off switch stays for holidays. |
| Font | Hurme Geometric Sans 1, served from the controller. |

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
  "held_on": null,
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
- `held_on`: the ISO date that a hold applies to, or `null`. A hold applies
  only on that date, so it clears itself at midnight. An unreadable value loads
  as `null`.
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
- While bells are held (`held_on` is today), the scheduler rings nothing, and
  the next bell skips to the first bell after today. Ring now, manual play, and
  the test tone still work.
- Ring now plays the next bell after the current minute, ignoring the master
  switch and any hold, at that bell's volume. When no bell is scheduled at all,
  there's nothing to ring.
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
| `GET /static/fonts/<name>` | Serves a `.woff2` font file from `static/fonts/`. Only file names made of letters, digits, and `-` are served. |
| `GET /api/state` | Returns the controller time (ISO with offset) and weekday, `enabled`, `master_volume`, `held`, `bells` (each with `missing_sound: bool`), `sounds` (name and duration in seconds), `playing` (sound name or `null`), `next_bell` (id, label, time, and date, or `null`), `ring_target` (the bell Ring now would play, in the same form, or `null`), and `adapter` (`connected: bool`, and `last_playback`: `{"time", "failed_transfers"}` or `null`). |
| `PUT /api/bells` | Replaces the whole bell list. Assigns ids to new bells. Validates time format, days, volume, that each sound exists, and that no bells clash. |
| `PUT /api/settings` | Sets any of `enabled`, `master_volume`, and `held` (boolean). Returns all three. |
| `POST /api/ring` | Plays the ring target's sound at its volume. Returns 409 when there's nothing to ring. |
| `POST /api/test-tone` | Plays the built-in test tone (1000 Hz, 3 s, level 0.25, about −12 dBFS) at the master volume. The program generates the tone once, as `<data>/test-tone.wav`, outside the sounds folder. |
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
| `held` | Param, `boolean` | setter `set_held` | Holds scheduled bells for the rest of today, or resumes them. Accepts the same loose values as `enabled`. |
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

The page's look comes from the Claude Design handoff in
`design/design_handoff_school_bells/` (its `README.md` and
`School Bells.dc.html`), which uses the Madison Group Enterprises (MGE) design
system. That handoff designs only the Today tab, and it was drawn before the
scheduler existed, so its sample timetables and tone-only playback are
placeholders. Where the design and this section differ on behavior, this
section wins. Where they differ on look, the design wins.

`static/index.html` is one file. The only other files it loads are the three
Hurme Geometric Sans 1 weights (400, 600, 700) in `static/fonts/`, served by
the program. It loads nothing from the internet, because staff browsers might
not have internet access. The Hurme licence is pageview-capped; the user
confirmed its use for this internal page.

### Layout

- **Header**, **nav**, and **footer** follow the design. The nav has three
  tabs: Today, Schedules, and Device. The URL hash (`#today`, `#schedules`,
  `#device`) keeps the current tab, and Today is the default.
- **Header status indicator**, in order of priority:
  - "Ringing" (red), while a sound plays.
  - "Bells held" (`#909dab`), while held.
  - "Adapter not found" (`#909dab`), when the adapter isn't connected.
  - "Adapter connected" (red), otherwise.
- **Header clock:** the controller's time, ticking every second.
- **Footer:** the design's footer, with the line
  `This page has no login. Keep it on a restricted network.` under the left
  text.
- **Error banner:** API errors appear in a banner under the header, with a
  dismiss button. It has a red left border on white.

### Today tab (as designed)

At the user's request, the Today tab uses tighter spacing than the design, so it
fits a 1920×1080 screen. On displays at least 1000 px wide and 640 px tall, the
tab fills the window with no page scrolling. A schedule too long to fit
scrolls inside its panel and keeps the NEXT row in view.

- **Hero:**
  - Eyebrow: "Next bell · {weekday D month}", in `en-AU` form.
  - The next bell's time and label, from `next_bell`.
  - A countdown that reads "In 12 min 05 s", or "In 1 h 05 min" when the bell
    is an hour or more away. When the next bell isn't today, the countdown
    reads "All bells done for today", and the label gets " tomorrow" or
    " on {Weekday}" added. When no bell is scheduled at all, the hero shows
    "No bells scheduled".
- **Hero buttons:**
  - **RING NOW** calls `POST /api/ring`. It's disabled when `ring_target` is
    `null` or a sound is playing.
  - **HOLD BELLS** or **RESUME BELLS** sets `held`.
  - The note under the buttons reads "Hold pauses scheduled bells for the rest
    of today.", or "Scheduled bells are paused until midnight." while held.
  - The ringing indicator shows while a sound plays: "Ringing · {sound name}".
- **Today's schedule** lists today's bells in time order, with the header
  "Weekday timetable · {n} bells".
  - Rows are marked RUNG (time at or before now), NEXT (the next bell today),
    or nothing (later today). While held, every un-rung row is tagged HELD.
  - When the master switch is off, a line under the header reads "Bells are
    switched off".
- **Bell tone** panel: the design's key/value grid (Frequency 1000 Hz,
  Duration 3 s, Level −12 dBFS) and **PLAY TEST TONE**, which calls
  `POST /api/test-tone`.
- **Audio adapter** panel: the design's key/value grid. The USB ID, Format, and
  Endpoint values are fixed text, and Last playback reads
  "Today HH:MM · N failed transfers", or "None yet". Status reads Connected or
  Not found.

### Schedules tab (MGE style; not in the design)

- A **Bells** panel holds the full bell list with weekdays, sound, and volume.
  - Each row has play, edit, and delete buttons. Play uses the bell's volume.
  - A row whose sound is missing is flagged in red.
  - **ADD BELL** and edit open an inline editor with a time picker, weekday
    checkboxes, a sound dropdown, and a volume slider.
- A **Sounds** panel holds the sound list.
  - Each sound has a play button, which uses the master volume, and a delete
    button.
  - **UPLOAD SOUND** converts the file in the browser:
    1. `AudioContext.decodeAudioData` decodes the file.
    2. `OfflineAudioContext` at 48000 Hz with 2 channels resamples it.
    3. The page encodes the result as 16-bit PCM WAV and posts it.

    The page shows "Converting…" and then "Uploading…", and says so if the
    browser can't decode the file.
- A **Bells enabled** switch is for holidays. It saves as soon as you change it.

### Device tab (MGE style; not in the design)

- A **Volume** panel holds the master volume slider, which saves when released,
  and a **STOP** button.
- The **Audio adapter** panel appears here too.
- A **Touch points** panel lists the program's MUSE touch points, so
  integrators can find them.

### Styling rules from the design system

- **Colors:** red `#e31837` for accents and actions only, `#2e3c49`, `#445c6d`,
  `#909dab`, `#e4e5e6`, white, and `#fff4f5` for the next-row tint.
- **Shapes:** 0 radius everywhere. The only shadows are the header shadow and
  the red glow.
- **Buttons:** bold, 14px, uppercase, `.06em` letter spacing, left-aligned, and
  minimum width 200px, with a `›` in the top-right corner. Padding is
  `22px 46px 20px 26px`, or `18px 40px 16px 22px` for small buttons.
- **Button variants:** red, outline white, outline dark, and white. Red darkens
  to `#d01632` on hover, and every transition takes 200ms.
- **Headings** end in a red full stop. The first panel in each column gets the
  red-corner mark. The footer has the 20px red bottom border.
- **Phone width:** the page works with no sideways scrolling. Grids collapse to
  one column, and the nav scrolls sideways if it must.

## Error handling

- If the adapter is unplugged or fails to open, the error is logged and
  returned to the page for manual plays. The scheduler logs it and moves on,
  and the next play tries to open the adapter again.
- An exception in one bell's playback never stops the scheduler or the web
  server threads.
- The web server logs each request's method, path, and status, except
  successful `GET` requests. Most of those are the page's 2-second polls, which
  would flood the controller log.

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
  9. Press Ring now and confirm the next bell's sound plays. Press Play test
     tone and confirm the 1 kHz tone plays.
  10. Hold bells, set a bell a minute ahead, and confirm it doesn't ring. Resume
      and confirm the next one does.
  11. Unplug the adapter and confirm the header reads "Adapter not found".

## Out of scope

- Login or user accounts.
- Multiple named timetables, term dates, and holiday calendars.
- Playing two sounds at once.
- Editing or trimming audio in the page.

## Phase 0 results (2026-10-12)

The user answered the lifecycle questions from experience, so the probe
program wasn't needed.

- **Port 8080:** reachable from the LAN. A deployed build of `school_bells`
  answered `http://172.17.0.55:8080/` from the user's PC.
- **Reload:** loading a program replaces its entire folder, so anything the
  program writes inside it is lost.
- **Reboot:** files a program writes survive a reboot.
- **Data folder:** MUSE defines no standard path. Following the user's
  recommendation, the program keeps its data in `school_bells_data/`, one
  directory up from the program folder and next to the program folders.
  Reloads don't delete it.
- **Clock:** the controller reported `2026-10-12T12:28:42+10:00`, matching the
  PC. The user confirmed the zone is correct. It's a zone without daylight
  saving, so the clock never jumps. If it did, bells would follow the
  controller's wall-clock time. On the night clocks go back, the
  `(bell id, date)` record stops repeats, and on the night clocks go forward,
  bells in the skipped hour don't ring. After changing the controller's time
  zone, reload the program.
- **Reload:** reloading stops the running Python process and starts a new
  one, which frees port 8080 for the new copy.

## Round 2 changes (2026-10-12)

The user requested these after testing on the controller. They supersede
earlier sections wherever the two differ.

### Time format preference

- **Setting:** `time_format` (`"24h"` or `"12h"`, default `"24h"`) is stored
  in `bells.json`, returned in `GET /api/state`, and set through
  `PUT /api/settings`. It applies to everyone.
- **Storage stays 24-hour:** bell times are still stored as 24-hour `HH:MM`.
  The setting changes only what the page shows and how times are entered.
- **Display:** every time on the page follows the setting: the header clock,
  the hero, today's schedule, the bell list, Last playback, and the log.
  12-hour times read `1:45 pm`.
- **Entry:** the bell editor uses hour and minute dropdowns, plus AM/PM in
  12-hour mode, instead of the browser's time picker, which follows the
  computer's region settings.
- **Touch points:** values such as `next_bell` stay in 24-hour form.
- **Preferences tab:** a new tab holds the setting.

### Footer

The footer no longer names Madison Group Enterprises.

### Bell log

- **What's recorded:** each playback attempt is appended to
  `<data>/history.jsonl` as
  `{"time", "source", "label", "sound", "result", "error"}`.
  - `source` is one of `scheduled`, `ring_now`, `test_tone`, `page`, or
    `touch_point`.
  - `result` is one of `played`, `failed`, or `skipped`.
- **Skipped rings:** when a skipped bell's minute arrives, the scheduler
  records it as `skipped`, once. Disabled bells aren't recorded.
- **Retention:** entries older than 30 days are dropped at startup and on the
  first write of each new day. Unreadable lines are ignored.
- **API:** `GET /api/history` returns `{"entries": [...]}`, newest first.
- **Log tab:** a new tab lists entries grouped by day, with failures shown in
  red.
- **Schedule changes:** the log also records changes to what rings, from the
  page (`source` `page`) or another MUSE program (`touch_point`). Changes show
  in grey. Each entry has a `detail` field, which holds the skipped date for
  `skip_set`. The `result` values are:
  - `enabled` or `disabled`: an existing bell turned on or off. Adding or
    deleting a bell isn't logged.
  - `skip_set` or `skip_cleared`: a skip set or removed.
  - `held` or `resumed`: bells held for today, or resumed.
  - `bells_off` or `bells_on`: the master switch turned off or on.

### Per-bell disable and skip

- **New fields on each bell:**
  - `enabled` (boolean, default `true`).
  - `skip_on` (an ISO date, or `null`).
  - `PUT /api/bells` validates both.
- **Disable:** a disabled bell never rings and isn't counted as the next bell
  or the Ring now target. It still counts in the clash rule.
- **Skip next:**
  - `POST /api/bells/<id>/skip` with `{"skip": true}` sets `skip_on` to the
    date of the bell's next ring after the current minute.
  - `{"skip": false}` clears it.
  - An unknown id returns 404.
  - The bell doesn't ring on `skip_on`. After that date, the value no longer
    matters.
- **Next bell and Ring now** pass over disabled bells and skipped rings.
- **Today tab:** each upcoming row has Skip and Undo controls. Rows are tagged
  OFF or SKIPPED.
- **Schedules tab:** each bell has an on/off switch and Skip next or Undo
  skip, and shows "Skipping {date}" while a skip is set.

## Round 3: Schedules tab design (2026-10-12)

The Schedules tab follows `design/design_handoff_school_bells/Schedules.dc.html`
and its README section, with these decisions from the user:

- The editor keeps the hour, minute, and am/pm dropdowns that follow the time
  format preference, instead of the design's browser time picker.
- Every bell needs a name. The page won't save a bell without one. Existing
  bells without names keep working and show their time.

Notes:

- Ring now from a bell's ⋯ menu calls `POST /api/play` with `{"bell": "<id>"}`,
  which plays that bell at its volume and logs it as Ring now with the bell's
  name.
- Saving the editor takes the bell's on/off state and skip from the latest
  state, so a change made elsewhere while the editor is open isn't undone.
- Deleting a sound still asks for confirmation, although the design doesn't
  show one, because an uploaded file can't be recovered.
- The "Scheduled bells are off" banner shows under the nav on every tab.

## Connection loss (2026-10-12)

- **Timeout:** each state poll gives up after 5 seconds.
- **Detecting the loss:** two failed polls in a row, or one before the page
  has any data, put the page in a disconnected state:
  - A red banner reads "Can't reach the bell controller. Retrying… Last update
    at HH:MM.", using the controller's time from the last successful poll.
  - The header status reads "Not connected".
  - The clock, hero time, and countdown freeze and dim, so nobody trusts stale
    times.
  - The tabs' content dims and becomes inert, so controls can't be used.
- **Recovery:** the next successful poll clears the state, redraws the page,
  and shows "Reconnected to the bell controller." for 3 seconds.
- **Failed actions:** an action that fails because the controller can't be
  reached shows "Can't reach the bell controller. Check the network, then try
  again." in the normal error banner, instead of the browser's generic
  message.
- **Limit:** from the browser's side, a stopped program and a network outage
  look the same, so the page reports both as "Can't reach the bell controller".
