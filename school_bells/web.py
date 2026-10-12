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
                adapter_connected=audio.adapter_connected, test_tone_path=None):
    """Return a server for the bell page and API. Call serve_forever() on it."""

    class Handler(BaseHTTPRequestHandler):
        server_version = 'SchoolBells/1.0'

        def log_message(self, fmt, *args):
            log.info('%s %s' % (self.address_string(), fmt % args))

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
            self._body_read = False
            try:
                if method == 'GET' and path == '/':
                    return self._index()
                if method == 'GET' and path.startswith('/static/fonts/'):
                    return self._font(path[len('/static/fonts/'):])
                if method == 'GET' and path == '/api/state':
                    return self._send_json(200, self._state())
                if method == 'PUT' and path == '/api/bells':
                    return self._put_bells()
                if method == 'PUT' and path == '/api/settings':
                    return self._put_settings()
                if method == 'POST' and path == '/api/sounds':
                    return self._upload(query)
                if method == 'DELETE' and path.startswith('/api/sounds/'):
                    return self._delete_sound(unquote(path[len('/api/sounds/'):]))
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
                    length = int(self.headers.get('Content-Length') or 0)
                except ValueError:
                    length = 0
                if 0 < length <= MAX_JSON_BYTES:
                    self._read_body(length)
            self.close_connection = True
            self._send_json(status, {'error': message})

        def _read_body(self, length):
            self._body_read = True
            return self.rfile.read(length)

        def _read_json(self):
            try:
                length = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                raise bells.ValidationError('Invalid Content-Length')
            if length > MAX_JSON_BYTES:
                raise bells.ValidationError('Request is too large')
            try:
                return json.loads(self._read_body(length) or b'null')
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
            return {
                'time': now.astimezone().isoformat(timespec='seconds'),
                'weekday': bells.DAYS[now.weekday()],
                'enabled': state['enabled'],
                'master_volume': state['master_volume'],
                'held': bells.is_held(state, now),
                'bells': [dict(b, missing_sound=not sounds.sound_exists(sounds_dir, b['sound']))
                          for b in state['bells']],
                'sounds': sounds.list_sounds(sounds_dir),
                'playing': player.playing,
                'next_bell': bells.next_bell(state, now),
                'ring_target': bells.ring_target(state, now),
                'adapter': {'connected': adapter_connected(),
                            'last_playback': getattr(player, 'last_playback', None)},
            }

        def _put_settings(self):
            body = self._read_json()
            if not isinstance(body, dict):
                raise bells.ValidationError('Settings must be a JSON object')
            if 'held' in body and not isinstance(body['held'], bool):
                raise bells.ValidationError('held must be true or false')
            others = {k: v for k, v in body.items() if k != 'held'}
            if others:
                store.set_settings(others)
            if 'held' in body:
                store.set_held(body['held'], clock().date())
            state = store.get()
            self._send_json(200, {'enabled': state['enabled'], 'master_volume': state['master_volume'],
                                  'held': bells.is_held(state, clock())})

        def _ring(self):
            state = store.get()
            target = bells.ring_target(state, clock())
            if target is None:
                return self._error(409, 'No bells are scheduled, so there is nothing to ring')
            bell = next(b for b in state['bells'] if b['id'] == target['id'])
            if not sounds.sound_exists(sounds_dir, bell['sound']):
                return self._error(404, 'Sound %s does not exist' % bell['sound'])
            gain = state['master_volume'] / 100 * bell['volume'] / 100
            player.play(os.path.join(sounds_dir, bell['sound']), gain)
            self._send_json(200, {'playing': bell['sound']})

        def _test_tone(self):
            if not test_tone_path or not os.path.isfile(test_tone_path):
                return self._error(404, 'The test tone is not available')
            player.play(test_tone_path, store.get()['master_volume'] / 100)
            self._send_json(200, {'playing': os.path.basename(test_tone_path)})

        def _put_bells(self):
            body = self._read_json()
            if not isinstance(body, dict):
                raise bells.ValidationError('Body must be {"bells": [...]}')
            clean = store.set_bells(body.get('bells'),
                                    lambda name: sounds.sound_exists(sounds_dir, name))
            self._send_json(200, {'bells': clean})

        def _upload(self, query):
            length_header = self.headers.get('Content-Length')
            if length_header is None:
                return self._error(411, 'Content-Length is required')
            try:
                length = int(length_header)
            except ValueError:
                raise bells.ValidationError('Invalid Content-Length')
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
                raise bells.ValidationError('Body must be {"sound": "<name>"}')
            name = body.get('sound')
            if not sounds.sound_exists(sounds_dir, name):
                return self._error(404, 'Sound %s does not exist' % name)
            volume = bells.check_volume(body.get('volume', 100), 'Volume')
            gain = store.get()['master_volume'] / 100 * volume / 100
            player.play(os.path.join(sounds_dir, name), gain)
            self._send_json(200, {'playing': name})

    return ThreadingHTTPServer((host, port), Handler)
