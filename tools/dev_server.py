"""Runs the bell web server on this PC with a fake player, for working on the page.

To use it, run `.venv/Scripts/python tools/dev_server.py`, then open http://localhost:8080/.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAM = os.path.join(ROOT, 'school_bells')
sys.path.insert(0, PROGRAM)

import bells  # noqa: E402
import history  # noqa: E402
import sounds  # noqa: E402
import web  # noqa: E402


class PrintLog:
    def info(self, message):
        print(message)

    def error(self, message):
        print('ERROR', message)


class PrintPlayer:
    playing = None
    last_playback = None

    def play(self, path, gain):
        print('PLAY %s at gain %.2f' % (path, gain))
        self.playing = os.path.basename(path)

    def stop(self):
        print('STOP')
        self.playing = None


data_dir = os.path.join(tempfile.gettempdir(), 'school_bells_dev')
sounds_dir = os.path.join(data_dir, 'sounds')
os.makedirs(sounds_dir, exist_ok=True)
test_tone = os.path.join(data_dir, 'test-tone.wav')
if not os.path.exists(test_tone):
    with open(test_tone, 'wb') as f:
        f.write(sounds.make_tone_wav())
log = PrintLog()
store = bells.Store(os.path.join(data_dir, 'bells.json'), log)
server = web.make_server(8080, store, PrintPlayer(), sounds_dir, os.path.join(PROGRAM, 'static'), log,
                         adapter_connected=lambda: True, test_tone_path=test_tone,
                         history=history.History(os.path.join(data_dir, 'history.jsonl'), log))
print('Open http://localhost:8080/ (data in %s)' % data_dir)
server.serve_forever()
