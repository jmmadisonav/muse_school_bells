import http.client
import json
import threading
import types
import urllib.parse
from datetime import datetime

import pytest

import bells
import web
from audio import AudioError
from helpers import FakePlayer, make_wav

NOW = datetime(2026, 10, 12, 10, 52, 7)  # Monday
RECESS = {'label': 'Recess', 'time': '11:00', 'days': ['mon', 'tue', 'wed', 'thu', 'fri'],
          'sound': 'recess.wav', 'volume': 50}


@pytest.fixture
def app(tmp_path, log):
    sounds_dir = tmp_path / 'sounds'
    sounds_dir.mkdir()
    static_dir = tmp_path / 'static'
    static_dir.mkdir()
    (static_dir / 'index.html').write_text('<h1>bells</h1>')
    store = bells.Store(str(tmp_path / 'bells.json'), log)
    player = FakePlayer()
    server = web.make_server(0, store, player, str(sounds_dir), str(static_dir), log,
                             clock=lambda: NOW, host='127.0.0.1')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield types.SimpleNamespace(port=server.server_address[1], store=store, player=player,
                                sounds_dir=sounds_dir, static_dir=static_dir)
    server.shutdown()
    server.server_close()


def call(app, method, path, body=None, raw=None, headers=None):
    conn = http.client.HTTPConnection('127.0.0.1', app.port, timeout=5)
    headers = dict(headers or {})
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    conn.request(method, path, body=data, headers=headers)
    response = conn.getresponse()
    text = response.read()
    conn.close()
    try:
        return response.status, json.loads(text)
    except ValueError:
        return response.status, text.decode()


def upload(app, name, data, overwrite=False):
    query = '?name=' + urllib.parse.quote(name) + ('&overwrite=1' if overwrite else '')
    return call(app, 'POST', '/api/sounds' + query, raw=data, headers={'Content-Type': 'audio/wav'})


def test_index_is_served_and_missing_index_is_404(app):
    assert call(app, 'GET', '/') == (200, '<h1>bells</h1>')
    (app.static_dir / 'index.html').unlink()
    assert call(app, 'GET', '/')[0] == 404


def test_state_reports_bells_sounds_and_next_bell(app):
    upload(app, 'recess.wav', make_wav(1.0))
    app.store.set_bells([RECESS, dict(RECESS, label='Lunch', time='13:00', sound='gone.wav')])
    status, state = call(app, 'GET', '/api/state')
    assert status == 200
    assert state['time'].startswith('2026-10-12T10:52:07')
    assert state['weekday'] == 'mon'
    assert state['enabled'] is True and state['master_volume'] == 80
    assert [(b['label'], b['missing_sound']) for b in state['bells']] == [('Recess', False), ('Lunch', True)]
    assert state['sounds'] == [{'name': 'recess.wav', 'seconds': 1.0}]
    assert state['playing'] is None
    assert state['next_bell']['label'] == 'Recess'


def test_put_bells_validates_and_saves(app):
    upload(app, 'recess.wav', make_wav(0.1))
    status, body = call(app, 'PUT', '/api/bells', {'bells': [RECESS]})
    assert status == 200 and body['bells'][0]['label'] == 'Recess'
    assert app.store.get()['bells'][0]['time'] == '11:00'
    assert call(app, 'PUT', '/api/bells', {'bells': [dict(RECESS, time='25:00')]})[0] == 400
    status, body = call(app, 'PUT', '/api/bells', {'bells': [dict(RECESS, sound='nope.wav')]})
    assert status == 400 and 'nope.wav' in body['error']
    assert call(app, 'PUT', '/api/bells', [RECESS])[0] == 400
    assert call(app, 'PUT', '/api/bells', raw=b'{bad', headers={'Content-Type': 'application/json'})[0] == 400


def test_put_settings_partial(app):
    assert call(app, 'PUT', '/api/settings', {'master_volume': 30}) == (
        200, {'enabled': True, 'master_volume': 30})
    assert call(app, 'PUT', '/api/settings', {'master_volume': 300})[0] == 400


def test_upload_checks_format_name_and_duplicates(app):
    assert upload(app, 'bell.wav', make_wav(0.5)) == (201, {'name': 'bell.wav', 'seconds': 0.5})
    assert upload(app, 'bell.wav', make_wav(0.5))[0] == 409
    assert upload(app, 'bell.wav', make_wav(0.25), overwrite=True)[0] == 201
    assert upload(app, 'cd.wav', make_wav(0.1, rate=44100))[0] == 400
    assert upload(app, 'junk.wav', b'junk')[0] == 400
    assert upload(app, '../escape.wav', make_wav(0.1))[0] == 400
    assert upload(app, 'a/b.wav', make_wav(0.1))[0] == 400
    assert sorted(p.name for p in app.sounds_dir.iterdir()) == ['bell.wav']


def test_upload_without_length_is_411(app):
    conn = http.client.HTTPConnection('127.0.0.1', app.port, timeout=5)
    conn.putrequest('POST', '/api/sounds?name=a.wav')
    conn.endheaders()
    assert conn.getresponse().status == 411


def test_upload_over_limit_is_413_without_reading_body(app):
    conn = http.client.HTTPConnection('127.0.0.1', app.port, timeout=5)
    conn.putrequest('POST', '/api/sounds?name=a.wav')
    conn.putheader('Content-Length', str(60 * 1024 * 1024))
    conn.endheaders()
    assert conn.getresponse().status == 413


def test_delete_sound_refuses_when_used(app):
    upload(app, 'recess.wav', make_wav(0.1))
    upload(app, 'spare.wav', make_wav(0.1))
    call(app, 'PUT', '/api/bells', {'bells': [RECESS]})
    status, body = call(app, 'DELETE', '/api/sounds/recess.wav')
    assert status == 409 and 'Recess' in body['error']
    assert call(app, 'DELETE', '/api/sounds/spare.wav')[0] == 200
    assert not (app.sounds_dir / 'spare.wav').exists()
    assert call(app, 'DELETE', '/api/sounds/spare.wav')[0] == 404
    assert call(app, 'DELETE', '/api/sounds/..%2Fbells.json')[0] == 400


def test_play_and_stop(app):
    upload(app, 'recess.wav', make_wav(0.1))
    assert call(app, 'POST', '/api/play', {'sound': 'recess.wav', 'volume': 50})[0] == 200
    assert call(app, 'POST', '/api/play', {'sound': 'recess.wav'})[0] == 200
    assert [round(g, 2) for _, g in app.player.plays] == [0.4, 0.8]
    assert call(app, 'POST', '/api/play', {'sound': 'nope.wav'})[0] == 404
    assert call(app, 'POST', '/api/play', {'sound': 'recess.wav', 'volume': 101})[0] == 400
    app.player.fail = AudioError('The USB audio adapter is not connected')
    status, body = call(app, 'POST', '/api/play', {'sound': 'recess.wav'})
    assert status == 503 and 'not connected' in body['error']
    assert call(app, 'POST', '/api/stop', {})[0] == 200
    assert app.player.stops == 1


def test_unknown_route_is_404(app):
    assert call(app, 'GET', '/api/nope')[0] == 404
