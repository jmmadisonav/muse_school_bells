"""HTTP server for the bell page and its JSON API."""
import json
import os
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

import bells
import sounds
import audio
from audio import AudioError

MAX_JSON_BYTES = 1024 * 1024
FONT_RE = re.compile(r'^[A-Za-z0-9-]+\.woff2$')


def make_server(port, store, player, sounds_dir, static_dir, log, clock=datetime.now, host='',
                adapter_connected=audio.adapter_connected, test_tone_path=None, history=None):
    """Return a server for the bell page and API. Call serve_forever() on it."""

    class Handler(BaseHTTPRequestHandler):
        server_version = 'SchoolBells/1.0'

        def log_message(self, fmt, *args):
            log.info('%s %s' % (self.address_string(), fmt % args))

        def log_request(self, code='-', size='-'):
            # Successful GETs are mostly the page's 2-second polls. Logging them would
            # flood the controller log, so log only changes and errors.
            if self.command == 'GET' and isinstance(code, int) and code < 400:
                return
            super().log_request(code, size)

        def do_GET(self):
            self._route('GET')

        def do_PUT(self):
            self._route('PUT')

        def do_POST(self):
            self._route('POST')

        def do_DELETE(self):
            self._route('DELETE')

        def _route(self, method):
            url = urlsplit(self.path)
            path, query = url.path, parse_qs(url.query)
            self._body = b''
            self._body_read = False
            try:
                if not (method == 'POST' and path == '/api/sounds'):
                    # Read every small body up front, even for handlers that ignore it:
                    # closing the socket with unread bytes resets the connection, and
                    # the client loses the response.
                    length = self._content_length() or 0
                    if length > MAX_JSON_BYTES:
                        raise bells.ValidationError('Request is too large')
                    self._body = self._read_body(length)
                if method == 'GET' and path == '/':
                    return self._index()
                if method == 'GET' and path.startswith('/static/fonts/'):
                    return self._font(path[len('/static/fonts/'):])
                if method == 'GET' and path == '/api/state':
                    return self._send_json(200, self._state())
                if method == 'PUT' and path == '/api/bells':
                    return self._put_bells(query)
                if method == 'POST' and path == '/api/schedules':
                    return self._create_schedule()
                if method == 'PUT' and path.startswith('/api/schedules/'):
                    return self._update_schedule(unquote(path[len('/api/schedules/'):]))
                if method == 'DELETE' and path.startswith('/api/schedules/'):
                    return self._delete_schedule(unquote(path[len('/api/schedules/'):]))
                if method == 'PUT' and path == '/api/settings':
                    return self._put_settings()
                if method == 'POST' and path == '/api/sounds':
                    return self._upload(query)
                if method == 'DELETE' and path.startswith('/api/sounds/'):
                    return self._delete_sound(unquote(path[len('/api/sounds/'):]))
                if method == 'GET' and path == '/api/history':
                    return self._send_json(200, {'entries': history.entries() if history else []})
                if method == 'POST' and path.startswith('/api/bells/') and path.endswith('/skip'):
                    return self._skip(unquote(path[len('/api/bells/'):-len('/skip')]))
                if method == 'POST' and path == '/api/play':
                    return self._play()
                if method == 'POST' and path == '/api/ring':
                    return self._ring()
                if method == 'POST' and path == '/api/test-tone':
                    return self._test_tone()
                if method == 'POST' and path == '/api/stop':
                    player.stop()
                    return self._send_json(200, {'playing': None})
                self._error(404, 'Not found')
            except bells.ValidationError as e:
                self._error(400, str(e))
            except AudioError as e:
                self._error(503, str(e))
            except Exception as e:
                log.error('%s %s failed: %r' % (method, path, e))
                self._error(500, 'Internal error: %r' % e)

        def _send_json(self, status, body):
            data = json.dumps(body).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status, message):
            # Closing a socket with unread request bytes resets the connection, and the
            # client never sees this response. Drain a small unread body first.
            if not self._body_read:
                try:
                    length = self._content_length() or 0
                except bells.ValidationError:
                    length = 0
                if 0 < length <= MAX_JSON_BYTES:
                    self._read_body(length)
            self.close_connection = True
            self._send_json(status, {'error': message})

        def _content_length(self):
            """Return the request's Content-Length, None if absent, or raise for a bad value."""
            header = self.headers.get('Content-Length')
            if header is None:
                return None
            try:
                length = int(header)
            except ValueError:
                length = -1
            if length < 0:
                raise bells.ValidationError('Invalid Content-Length')
            return length

        def _read_body(self, length):
            self._body_read = True
            return self.rfile.read(length)

        def _read_json(self):
            try:
                return json.loads(self._body or b'null')
            except ValueError:
                raise bells.ValidationError('Request body must be JSON')

        def _index(self):
            try:
                with open(os.path.join(static_dir, 'index.html'), 'rb') as f:
                    data = f.read()
            except OSError:
                return self._error(404, 'The bell page is not installed')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def _font(self, name):
            path = os.path.join(static_dir, 'fonts', name)
            if not FONT_RE.match(name) or not os.path.isfile(path):
                return self._error(404, 'Not found')
            with open(path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'font/woff2')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'max-age=86400')
            self.end_headers()
            self.wfile.write(data)

        def _state(self):
            now = clock()
            state = store.get()
            active = bells.schedule_for(state, now.date())
            with_sounds = lambda bell_list: [dict(b, missing_sound=not sounds.sound_exists(sounds_dir, b['sound']))
                                             for b in bell_list]
            return {
                'time': now.astimezone().isoformat(timespec='milliseconds'),  # the page's clock needs the fraction
                'weekday': bells.DAYS[now.weekday()],
                'enabled': state['enabled'],
                'master_volume': state['master_volume'],
                'time_format': state['time_format'],
                'held': bells.is_held(state, now),
                'bells': with_sounds(active['bells']),
                'schedules': [dict(s, bells=with_sounds(s['bells'])) for s in state['schedules']],
                'active_schedule': self._active(state, now),
                'sounds': sounds.list_sounds(sounds_dir),
                'playing': player.playing,
                'next_bell': bells.next_bell(state, now),
                'ring_target': bells.ring_target(state, now),
                'adapter': {'connected': adapter_connected(),
                            'last_playback': getattr(player, 'last_playback', None)},
            }

        def _active(self, state, now):
            active = bells.schedule_for(state, now.date())
            return {'id': active['id'], 'name': active['name'], 'manual': bells.is_manual(state, now.date())}

        def _logged_change(self, action):
            """Run a schedule change and log any change of active schedule it causes."""
            before = store.get()
            result = action()
            if history is not None:
                history.record_setting_changes('page', before, store.get(), clock())
            return result

        def _create_schedule(self):
            body = self._read_json()
            if not isinstance(body, dict):
                raise bells.ValidationError('Body must be {"name": "<name>"}')
            try:
                schedule = store.create_schedule(body.get('name'), body.get('copy_from'))
            except KeyError:
                return self._error(404, 'No schedule with id %s' % body.get('copy_from'))
            self._send_json(201, schedule)

        def _update_schedule(self, schedule_id):
            body = self._read_json()
            try:
                schedule = self._logged_change(lambda: store.update_schedule(schedule_id, body))
            except KeyError:
                return self._error(404, 'No schedule with id %s' % schedule_id)
            self._send_json(200, schedule)

        def _delete_schedule(self, schedule_id):
            try:
                self._logged_change(lambda: store.delete_schedule(schedule_id))
            except KeyError:
                return self._error(404, 'No schedule with id %s' % schedule_id)
            self._send_json(200, {'deleted': schedule_id})

        def _put_settings(self):
            body = self._read_json()
            if not isinstance(body, dict):
                raise bells.ValidationError('Settings must be a JSON object')
            if 'held' in body and not isinstance(body['held'], bool):
                raise bells.ValidationError('held must be true or false')
            if 'active_schedule' in body and not (body['active_schedule'] is None
                                                  or isinstance(body['active_schedule'], str)):
                raise bells.ValidationError('active_schedule must be a schedule id, or null to follow the dates')
            before = store.get()
            others = {k: v for k, v in body.items() if k not in ('held', 'active_schedule')}
            if others:
                store.set_settings(others)
            if 'held' in body:
                store.set_held(body['held'], clock().date())
            if 'active_schedule' in body:
                try:
                    store.set_active(body['active_schedule'], clock().date())
                except KeyError:
                    return self._error(404, 'No schedule with id %s' % body['active_schedule'])
            state = store.get()
            if history is not None:
                history.record_setting_changes('page', before, state, clock())
            self._send_json(200, {'enabled': state['enabled'], 'master_volume': state['master_volume'],
                                  'held': bells.is_held(state, clock()),
                                  'time_format': state['time_format'],
                                  'active_schedule': self._active(state, clock())})

        def _skip(self, bell_id):
            body = self._read_json()
            if not isinstance(body, dict):
                raise bells.ValidationError('Body must be {"skip": true or false}')
            try:
                bell = store.set_skip(bell_id, body.get('skip'), clock())
            except KeyError:
                return self._error(404, 'No bell with id %s' % bell_id)
            if history is not None:
                history.record('page', bell['sound'], 'skip_set' if bell['skip_on'] else 'skip_cleared',
                               label=bell['label'] or bell['time'], detail=bell['skip_on'] or '')
            self._send_json(200, bell)

        def _play_logged(self, source, path, gain, sound, label=''):
            """Play and record the attempt in the bell log, then report what's playing."""
            try:
                player.play(path, gain)
            except Exception as e:
                if history is not None:
                    history.record(source, sound, 'failed', label=label, error=str(e))
                raise
            if history is not None:
                history.record(source, sound, label=label)
            self._send_json(200, {'playing': sound})

        def _ring(self):
            state = store.get()
            target = bells.ring_target(state, clock())
            if target is None:
                return self._error(409, 'No bells are scheduled, so there is nothing to ring')
            _, bell = bells.find_bell(state, target['id'])
            if not sounds.sound_exists(sounds_dir, bell['sound']):
                return self._error(404, 'Sound %s does not exist' % bell['sound'])
            gain = state['master_volume'] / 100 * bell['volume'] / 100
            self._play_logged('ring_now', os.path.join(sounds_dir, bell['sound']), gain, bell['sound'],
                              label=bell['label'] or bell['time'])

        def _test_tone(self):
            if not test_tone_path or not os.path.isfile(test_tone_path):
                return self._error(404, 'The test tone is not available')
            self._play_logged('test_tone', test_tone_path, store.get()['master_volume'] / 100,
                              os.path.basename(test_tone_path))

        def _put_bells(self, query):
            body = self._read_json()
            if not isinstance(body, dict):
                raise bells.ValidationError('Body must be {"bells": [...]}')
            # Without ?schedule=, edit the schedule in use today.
            schedule_id = query.get('schedule', [None])[0] or bells.schedule_for(store.get(), clock().date())['id']
            try:
                before = store.bells(schedule_id)
                clean = store.set_bells(body.get('bells'),
                                        lambda name: sounds.sound_exists(sounds_dir, name), schedule_id)
            except KeyError:
                return self._error(404, 'No schedule with id %s' % schedule_id)
            if history is not None:
                history.record_bell_changes('page', before, clean)
            self._send_json(200, {'bells': clean})

        def _upload(self, query):
            length = self._content_length()
            if length is None:
                return self._error(411, 'Content-Length is required')
            if length > sounds.MAX_UPLOAD_BYTES:
                return self._error(413, 'Sounds are limited to 50 MB')
            data = self._read_body(length)
            name = sounds.check_name(query.get('name', [''])[0])
            seconds = sounds.wav_seconds(data)
            try:
                sounds.save_sound(sounds_dir, name, data,
                                  overwrite=query.get('overwrite', ['0'])[0] == '1')
            except FileExistsError:
                return self._error(409, '%s already exists' % name)
            self._send_json(201, {'name': name, 'seconds': seconds})

        def _delete_sound(self, name):
            sounds.check_name(name)
            users = store.bells_using(name)
            if users:
                return self._error(409, '%s is used by these bells: %s' % (name, ', '.join(users)))
            if not sounds.sound_exists(sounds_dir, name):
                return self._error(404, '%s does not exist' % name)
            if player.playing == name:
                player.stop()
            os.remove(os.path.join(sounds_dir, name))
            self._send_json(200, {'deleted': name})

        def _play(self):
            body = self._read_json()
            if not isinstance(body, dict):
                raise bells.ValidationError('Body must be {"sound": "<name>"} or {"bell": "<id>"}')
            if 'bell' in body:
                # Ring a specific bell now: its sound at its volume, logged as Ring now.
                state = store.get()
                _, bell = bells.find_bell(state, body['bell'])
                if bell is None:
                    return self._error(404, 'No bell with id %s' % body['bell'])
                if not sounds.sound_exists(sounds_dir, bell['sound']):
                    return self._error(404, 'Sound %s does not exist' % bell['sound'])
                gain = state['master_volume'] / 100 * bell['volume'] / 100
                return self._play_logged('ring_now', os.path.join(sounds_dir, bell['sound']), gain,
                                         bell['sound'], label=bell['label'] or bell['time'])
            name = body.get('sound')
            if not sounds.sound_exists(sounds_dir, name):
                return self._error(404, 'Sound %s does not exist' % name)
            volume = bells.check_volume(body.get('volume', 100), 'Volume')
            gain = store.get()['master_volume'] / 100 * volume / 100
            self._play_logged('page', os.path.join(sounds_dir, name), gain, name)

    return ThreadingHTTPServer((host, port), Handler)
