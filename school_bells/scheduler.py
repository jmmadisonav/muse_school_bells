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
        state = dict(self._store.get(), enabled=True, held_on=None)
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
