# School bells

School bells is an AMX MUSE controller program that rings school bells on a
weekly timetable. It plays sounds through a USB audio adapter plugged into the
controller. You manage it from a web page that the program serves, and other
MUSE programs can control it through touch points.

## Features

- **Weekly timetable:** set a time, weekdays, sound, and volume for each bell.
- **Playback controls:**
  - Ring now plays the next bell.
  - A built-in 1 kHz test tone checks the speakers.
  - You can play any uploaded sound on demand.
- **Hold and switches:**
  - Hold pauses bells for the rest of today.
  - A master switch turns all bells off, for example during holidays.
- **Per-bell control:** turn individual bells off, or skip a bell's next ring.
- **Uploads:** upload MP3, WAV, M4A, or any other format your browser can play.
  The browser converts each file to 48 kHz, 16-bit stereo WAV before uploading
  it.
- **Bell log:** the log records every playback and every change to what rings,
  and keeps 30 days of history.
- **Time format:** a 12-hour or 24-hour display, shared by everyone who uses
  the page.
- **Touch points:** other MUSE programs can read the bell state, hold bells,
  play sounds, and react when a bell rings.

## Requirements

- An AMX MUSE controller running firmware that includes Python 3.10. The
  program was developed on firmware with Linux 5.4 (aarch64) and Python
  3.10.13.
- A USB audio adapter with a C-Media chipset, USB ID `0d8c:0014`, such as the
  Unitek Y-247A. The adapter must support 48 kHz, 16-bit stereo playback.
- Internet access from the controller the first time you load the program, so
  MUSE can install the `libusb1` package listed in
  `school_bells/requirements.txt`.
- A browser on the same network as the controller.

### Why the program drives the USB adapter directly

The MUSE firmware is built without Linux sound support, so the usual audio
libraries can't play sound on the controller. Instead, `audio.py` streams audio
to the adapter's isochronous USB endpoint through `libusb`. The firmware lets
programs open the adapter's USB device file directly.

## Repository layout

```
school_bells/                 repository root (development files)
├─ school_bells/              the MUSE program. Load this folder.
│  ├─ program.json            program metadata and touch points
│  ├─ main.py                 startup: wires the modules together
│  ├─ bells.py                timetable rules and storage
│  ├─ scheduler.py            rings due bells once a second
│  ├─ audio.py                USB audio playback through libusb
│  ├─ sounds.py               sound file rules and the test tone
│  ├─ history.py              bell log
│  ├─ web.py                  web page server and JSON API
│  ├─ touchpoints.py          touch points for other MUSE programs
│  ├─ static/                 the web page and its fonts
│  └─ requirements.txt        libusb1
├─ tools/
│  ├─ usb_probe/              diagnostic program: USB devices and sound support
│  ├─ tp_check/               diagnostic program: exercises the touch points
│  └─ dev_server.py           runs the web page on your PC with a stand-in player
├─ tests/                     pytest suite
├─ docs/superpowers/          design spec and implementation plan
└─ design/                    the Claude Design handoff the page is based on
```

## Install on the controller

To install or update the program, do the following:

1. Plug the USB audio adapter into the controller's USB port and connect
   speakers to the adapter's output.
1. In VS Code with the MUSE extension, load the `school_bells` folder (the
   inner folder, not the repository root) to the controller.
1. Attach to the program's output and confirm that it logs
   `School bells running on port 8080`.
1. Open `http://<controller-ip>:8080/` in a browser.

Loading a program replaces its whole folder on the controller, so the program
keeps its data in a separate folder next to it, `school_bells_data/`. Reloading
or updating the program keeps your bells, sounds, settings, and log.

| File in `school_bells_data/` | Contents |
|---|---|
| `bells.json` | The timetable and settings. |
| `sounds/` | Uploaded sounds, stored as 48 kHz, 16-bit stereo WAV files. |
| `history.jsonl` | The bell log, one JSON entry per line. |
| `test-tone.wav` | The built-in test tone, generated on first start. |

## Use the web page

The page has five tabs:

| Tab | What you can do |
|---|---|
| **Today** | See the next bell and a countdown, ring the next bell now, play the test tone, hold or resume today's bells, and skip upcoming bells. |
| **Schedules** | Add, edit, and delete bells. Turn bells on or off, skip a bell's next ring, upload sounds, and switch all bells off. |
| **Device** | Set the master volume, stop playback, check the adapter, and see the touch-point list. |
| **Log** | Review the last 30 days of playback and schedule changes. |
| **Preferences** | Choose a 12-hour or 24-hour time format. |

### How bells ring

- **Timing:** each bell rings once, during the minute it's set for, on the
  weekdays you choose. The program uses the controller's local clock.
- **Missed bells:** if the controller is off or restarting at a bell's time,
  the bell doesn't ring late.
- **Volume:** a bell's volume is the master volume multiplied by the bell's
  own volume.
- **Clashes:** the page doesn't let you save two bells at the same time on the
  same day.
- **Skips:** a skip applies to one ring only. Afterwards, the bell rings
  normally again.
- **Hold:** a hold ends at midnight.

> **Important:** The page has no login. Anyone who can reach the controller on
> the network can change the bells, so keep the controller on a restricted
> network.

## Control the bells from other MUSE programs

Other programs on the controller reach this program as the device
`school_bells`:

```python
from mojo import context

bells = context.devices.get('school_bells')

print(bells.next_bell.value)            # for example: Mon 13:45 Period 5
bells.held.value = True                 # hold today's bells
bells.play('evacuation.wav')            # play a stored sound
bells.listen('bell_rang', lambda event: print(event.arguments))
```

| Touch point | Kind | Description |
|---|---|---|
| `enabled` | Param, boolean | Turns all scheduled bells on or off. |
| `master_volume` | Param, integer, 0 to 100 | Sets the output level. |
| `held` | Param, boolean | Holds bells for the rest of today. |
| `playing` | Param, string, read-only | The sound playing now, or empty. |
| `next_bell` | Param, string, read-only | The next bell, in 24-hour time, or empty. |
| `last_error` | Param, string, read-only | The latest bell or command error. |
| `play` | Command, argument `sound` | Plays a stored sound at the master volume. |
| `stop` | Command | Stops playback. |
| `bell_rang` | Event with `id`, `label`, `time`, `sound` | Fires each time the timetable rings a bell. |

Touch-point changes show on the web page, and are recorded in the log as
coming from "Other program".

## JSON API

The web page uses this API, and you can call it too. Request and response
bodies are JSON, except for sound uploads. Errors return a 4xx or 5xx status
with `{"error": "<message>"}`.

| Method and path | Purpose |
|---|---|
| `GET /api/state` | The clock, settings, bells, sounds, playback, next bell, and adapter status. |
| `PUT /api/bells` | Replaces the bell list. |
| `POST /api/bells/<id>/skip` | Sets (`{"skip": true}`) or clears (`{"skip": false}`) a bell's skip. |
| `PUT /api/settings` | Sets any of `enabled`, `master_volume`, `held`, and `time_format`. |
| `POST /api/sounds?name=<name>.wav` | Uploads a 48 kHz, 16-bit stereo WAV file, up to 50 MB. Add `&overwrite=1` to replace a sound. |
| `DELETE /api/sounds/<name>` | Deletes a sound that no bell uses. |
| `POST /api/play` | Plays `{"sound": "<name>", "volume": 0-100}`. The volume is optional. |
| `POST /api/ring` | Plays the next bell. |
| `POST /api/test-tone` | Plays the test tone. |
| `POST /api/stop` | Stops playback. |
| `GET /api/history` | The bell log, newest first. |

## Develop on your PC

The program modules don't import `mojo`, except `main.py`, so you can test
them on Windows, macOS, or Linux.

To set up a development environment, do the following:

1. Create a virtual environment and install the development requirements:

   ```
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements-dev.txt
   ```

   On macOS or Linux, use `.venv/bin/python`. Python 3.13 and later need the
   `audioop-lts` package, which the requirements file installs.
1. Run the tests:

   ```
   .venv\Scripts\python -m pytest -q
   ```

1. To work on the web page, run the development server, then open
   `http://localhost:8080/`:

   ```
   .venv\Scripts\python tools/dev_server.py
   ```

   The development server uses a stand-in player that prints what it would
   play, and stores its data in your system's temporary folder.

Write code that runs on Python 3.10, because that's the version on the
controller.

## Troubleshoot

| Symptom | What to check |
|---|---|
| The header says **Adapter not found**. | Check that the adapter is plugged in. To list what the controller sees, load the `tools/usb_probe` folder as a program. |
| A bell rang at the wrong time. | Check the controller's clock and time zone. Bells follow the controller's local time. If you change the time zone, reload the program. |
| The page doesn't load. | Check that the program is running and nothing else uses port 8080. |
| A bell is shown in red as missing its sound. | Upload the sound again, or edit the bell to choose another sound. |
| Another program can't control the bells. | Load the `tools/tp_check` folder as a program. It reads, watches, and drives every touch point, and logs the results. |

## Design documents

- `docs/superpowers/specs/2026-10-12-school-bells-web-design.md` is the design
  spec, including the decisions made with the user and the controller facts
  they rest on.
- `docs/superpowers/plans/2026-10-12-school-bells-web.md` is the
  implementation plan.
