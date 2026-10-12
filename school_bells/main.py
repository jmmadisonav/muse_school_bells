import os
import sys
import threading

from mojo import context

HERE = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
sys.path.insert(0, HERE)

import audio  # noqa: E402
import bells  # noqa: E402
import history  # noqa: E402
import scheduler  # noqa: E402
import sounds  # noqa: E402
import touchpoints  # noqa: E402
import web  # noqa: E402

log = context.log
PORT = 8080
# Loading a program replaces its whole folder, so keep data in a sibling folder.
DATA_DIR = os.path.join(os.path.dirname(HERE), 'school_bells_data')
SOUNDS_DIR = os.path.join(DATA_DIR, 'sounds')
os.makedirs(SOUNDS_DIR, exist_ok=True)
TEST_TONE = os.path.join(DATA_DIR, 'test-tone.wav')  # outside SOUNDS_DIR, so it isn't listed
if not os.path.exists(TEST_TONE):
    with open(TEST_TONE, 'wb') as f:
        f.write(sounds.make_tone_wav())

store = bells.Store(os.path.join(DATA_DIR, 'bells.json'), log)
player = audio.Player(log)
bell_log = history.History(os.path.join(DATA_DIR, 'history.jsonl'), log)
touch = touchpoints.TouchPoints(context.export, store, player, SOUNDS_DIR, log, history=bell_log)
globals().update(touch.handlers())  # MUSE finds program.json's setters and methods here
scheduler.Scheduler(store, player, SOUNDS_DIR, log, events=touch, history=bell_log).start()
server = web.make_server(PORT, store, player, SOUNDS_DIR, os.path.join(HERE, 'static'), log,
                         test_tone_path=TEST_TONE, history=bell_log)
threading.Thread(target=server.serve_forever, daemon=True, name='bell-web').start()
touch.start()
log.info('School bells running on port %d, data in %s' % (PORT, DATA_DIR))

# leave this as the last line in the Python script
context.run(globals())
