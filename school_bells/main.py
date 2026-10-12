import os
import sys
import threading

from mojo import context

HERE = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
sys.path.insert(0, HERE)

import audio  # noqa: E402
import bells  # noqa: E402
import scheduler  # noqa: E402
import sounds  # noqa: E402
import touchpoints  # noqa: E402
import web  # noqa: E402

log = context.log
PORT = 8080
DATA_DIR = os.path.join(HERE, 'data')  # set from the spec's Phase 0 results
SOUNDS_DIR = os.path.join(DATA_DIR, 'sounds')
os.makedirs(SOUNDS_DIR, exist_ok=True)
TEST_TONE = os.path.join(DATA_DIR, 'test-tone.wav')  # outside SOUNDS_DIR, so it isn't listed
if not os.path.exists(TEST_TONE):
    with open(TEST_TONE, 'wb') as f:
        f.write(sounds.make_tone_wav())

store = bells.Store(os.path.join(DATA_DIR, 'bells.json'), log)
player = audio.Player(log)
touch = touchpoints.TouchPoints(context.export, store, player, SOUNDS_DIR, log)
globals().update(touch.handlers())  # MUSE finds program.json's setters and methods here
scheduler.Scheduler(store, player, SOUNDS_DIR, log, events=touch).start()
server = web.make_server(PORT, store, player, SOUNDS_DIR, os.path.join(HERE, 'static'), log,
                         test_tone_path=TEST_TONE)
threading.Thread(target=server.serve_forever, daemon=True, name='bell-web').start()
touch.start()
log.info('School bells running on port %d, data in %s' % (PORT, DATA_DIR))

# leave this as the last line in the Python script
context.run(globals())
