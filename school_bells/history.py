"""Bell log: every playback attempt, kept for a limited number of days."""
import json
import os
import threading
from datetime import datetime, timedelta

import bells


class History:
    """Appends playback entries to a JSON-lines file and drops entries older than keep_days."""

    def __init__(self, path, log, clock=datetime.now, keep_days=30):
        self._path = path
        self._log = log
        self._clock = clock
        self._keep_days = keep_days
        self._lock = threading.Lock()
        self._pruned_on = None
        with self._lock:
            self._prune_locked()

    def record(self, source, sound, result='played', label='', error='', detail=''):
        """Add an entry. source: scheduled, ring_now, test_tone, page, or touch_point.

        Logging is best-effort: a failure here is logged and never reaches the caller,
        so the bell log can't stop a bell from ringing.
        """
        try:
            self._record(source, sound, result, label, error, detail)
        except Exception as e:
            self._log.error('Could not write the bell log: %r' % e)

    def _record(self, source, sound, result, label, error, detail):
        now = self._clock()
        entry = {'time': now.isoformat(timespec='seconds'), 'source': source, 'label': label,
                 'sound': sound, 'result': result, 'error': error, 'detail': detail}
        with self._lock:
            if self._pruned_on != now.date():
                self._prune_locked()
            try:
                with open(self._path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry) + '\n')
            except OSError as e:
                self._log.error('Could not write the bell log: %r' % e)

    def record_setting_changes(self, source, before, after, now):
        """Log a change to the master switch or the hold between two schedule states."""
        if before['enabled'] != after['enabled']:
            self.record(source, '', 'bells_on' if after['enabled'] else 'bells_off')
        held_before, held_after = bells.is_held(before, now), bells.is_held(after, now)
        if held_before != held_after:
            self.record(source, '', 'held' if held_after else 'resumed')

    def record_bell_changes(self, source, before, after):
        """Log each existing bell turned on or off. Added and deleted bells aren't logged."""
        old = {b['id']: b for b in before}
        for bell in after:
            previous = old.get(bell['id'])
            if previous is not None and previous.get('enabled', True) != bell.get('enabled', True):
                self.record(source, bell['sound'], 'enabled' if bell.get('enabled', True) else 'disabled',
                            label=bell['label'] or bell['time'])

    def entries(self, limit=1000):
        """Return up to limit entries, newest first."""
        with self._lock:
            return list(reversed(self._read_locked()))[:limit]

    def prune(self):
        with self._lock:
            self._prune_locked()

    def _read_locked(self):
        try:
            with open(self._path, encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except (OSError, ValueError):
            return []
        result = []
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and isinstance(entry.get('time'), str):
                result.append(entry)
        return result

    def _prune_locked(self):
        now = self._clock()
        self._pruned_on = now.date()
        if not os.path.exists(self._path):
            return
        cutoff = (now - timedelta(days=self._keep_days)).isoformat(timespec='seconds')
        kept = [e for e in self._read_locked() if e['time'] >= cutoff]
        tmp = self._path + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                f.writelines(json.dumps(e) + '\n' for e in kept)
            os.replace(tmp, self._path)
        except OSError as e:
            self._log.error('Could not prune the bell log: %r' % e)
