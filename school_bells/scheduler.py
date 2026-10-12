"""Rings each due bell once, using the controller's local clock."""
import os
import threading
import time
from datetime import datetime, timedelta

import bells


class Scheduler:
    def __init__(self, store, player, sounds_dir, log, clock=datetime.now, events=None, history=None):
        self._store = store
        self._player = player
        self._sounds_dir = sounds_dir
        self._log = log
        self._clock = clock
        self._events = events  # has bell_rang(bell) and error(message), or None
        self._history = history  # history.History, or None
        self._rung = set()  # (bell id, ISO date) pairs; memory only
        self._seen = None  # (ISO date, automatic schedule id) at the last tick

    def _record(self, bell, result, error=''):
        if self._history is not None:
            self._history.record('scheduled', bell['sound'], result, label=bell['label'] or bell['time'],
                                 error=error)

    def _note_changeover(self, state, now):
        # A new day whose automatic schedule differs from yesterday's means a date range
        # started or ended. Manual picks are logged where they're made.
        auto = bells.auto_schedule(state, now.date())
        seen = (now.date().isoformat(), auto['id'])
        if self._seen and self._seen[0] != seen[0] and self._seen[1] != seen[1] and self._history:
            self._history.record('scheduled', '', 'schedule_changed', label=auto['name'], detail='dates')
        self._seen = seen

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
        self._note_changeover(state, now)
        for b in bells.skipped_bells(state, now, self._rung):
            self._rung.add((b['id'], today))
            self._record(b, 'skipped')
        for b in bells.due_bells(state, now, self._rung):
            self._rung.add((b['id'], today))
            handled.append(b['id'])
            name = b['label'] or b['time']
            path = os.path.join(self._sounds_dir, b['sound'])
            if not os.path.isfile(path):
                message = 'Bell "%s" at %s: sound %s is missing' % (name, b['time'], b['sound'])
                self._error(message)
                self._record(b, 'failed', message)
                continue
            gain = state['master_volume'] / 100 * b['volume'] / 100
            try:
                self._player.play(path, gain)
            except Exception as e:
                self._error('Bell "%s" at %s failed: %s' % (name, b['time'], e))
                self._record(b, 'failed', str(e))
                continue
            self._record(b, 'played')
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
