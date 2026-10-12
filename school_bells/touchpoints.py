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


def to_bool(value, name='enabled'):
    """Accept the loose forms MUSE and other programs might send for a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ('true', 'false', '1', '0'):
        return value.strip().lower() in ('true', '1')
    raise bells.ValidationError('%s must be true or false, not %r' % (name, value))


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
    def __init__(self, export, store, player, sounds_dir, log, clock=datetime.now, history=None):
        self._export = export
        self._store = store
        self._player = player
        self._sounds_dir = sounds_dir
        self._log = log
        self._clock = clock
        self._history = history
        self._last_error = ''
        self._published = {}
        self._lock = threading.Lock()

    def handlers(self):
        """Return the set and command handlers that program.json names.

        These are plain functions, because MUSE counts parameters to decide how
        to call a handler, and a bound method's self would be counted.
        """
        def set_enabled(value):
            self._apply('enabled', lambda: self._change(
                lambda: self._store.set_settings({'enabled': to_bool(value)})))

        def set_master_volume(value):
            self._apply('master_volume',
                        lambda: self._store.set_settings({'master_volume': to_volume(value)}))

        def set_held(value):
            self._apply('held', lambda: self._change(
                lambda: self._store.set_held(to_bool(value, 'held'), self._clock().date())))

        def play_sound(args):
            self._apply('play', lambda: self._play(sound_argument(args)))

        def stop_sound():
            self._apply('stop', self._player.stop)

        return {'set_enabled': set_enabled, 'set_master_volume': set_master_volume,
                'set_held': set_held, 'play_sound': play_sound, 'stop_sound': stop_sound}

    def _change(self, action):
        """Run a settings change and log it if it switched bells on or off, or held them."""
        before = self._store.get()
        action()
        if self._history is not None:
            self._history.record_setting_changes('touch_point', before, self._store.get(), self._clock())

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
        try:
            self._player.play(os.path.join(self._sounds_dir, name), gain)
        except Exception as e:
            if self._history is not None:
                self._history.record('touch_point', name, 'failed', error=str(e))
            raise
        if self._history is not None:
            self._history.record('touch_point', name)

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
            'held': bells.is_held(state, self._clock()),
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
        self.publish()  # MUSE marks a running program's device online itself
        threading.Thread(target=self._loop, daemon=True, name='bell-touchpoints').start()

    def _loop(self):
        while True:
            time.sleep(1.0)
            try:
                self.publish()
            except Exception as e:
                self._log.error('Touch-point publish failed: %r' % e)
