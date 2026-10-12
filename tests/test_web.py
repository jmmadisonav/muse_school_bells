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
import history
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
    test_tone = tmp_path / 'test-tone.wav'
    bell_log = history.History(str(tmp_path / 'history.jsonl'), log, clock=lambda: NOW)
    server = web.make_server(0, store, player, str(sounds_dir), str(static_dir), log,
                             clock=lambda: NOW, host='127.0.0.1',
                             adapter_connected=lambda: True, test_tone_path=str(test_tone),
                             history=bell_log)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield types.SimpleNamespace(port=server.server_address[1], store=store, player=player,
                                sounds_dir=sounds_dir, static_dir=static_dir,
                                test_tone=test_tone, history=bell_log)
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
    assert app.store.bells()[0]['time'] == '11:00'
    assert call(app, 'PUT', '/api/bells', {'bells': [dict(RECESS, time='25:00')]})[0] == 400
    status, body = call(app, 'PUT', '/api/bells', {'bells': [dict(RECESS, sound='nope.wav')]})
    assert status == 400 and 'nope.wav' in body['error']
    assert call(app, 'PUT', '/api/bells', [RECESS])[0] == 400
    assert call(app, 'PUT', '/api/bells', raw=b'{bad', headers={'Content-Type': 'application/json'})[0] == 400


def test_put_settings_partial(app):
    assert call(app, 'PUT', '/api/settings', {'master_volume': 30}) == (
        200, {'enabled': True, 'master_volume': 30, 'held': False, 'time_format': '24h',
              'active_schedule': {'id': 'standard', 'name': 'Standard', 'manual': False}})
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


def test_fonts_are_served_from_allow_list(app):
    fonts = app.static_dir / 'fonts'
    fonts.mkdir()
    (fonts / 'Hurme-Bold.woff2').write_bytes(b'wOF2data')
    (app.static_dir / 'secret.txt').write_text('x')
    conn = http.client.HTTPConnection('127.0.0.1', app.port, timeout=5)
    conn.request('GET', '/static/fonts/Hurme-Bold.woff2')
    response = conn.getresponse()
    assert response.status == 200
    assert response.getheader('Content-Type') == 'font/woff2'
    assert response.read() == b'wOF2data'
    conn.close()
    assert call(app, 'GET', '/static/fonts/../secret.txt')[0] == 404
    assert call(app, 'GET', '/static/fonts/x.txt')[0] == 404
    assert call(app, 'GET', '/static/fonts/missing.woff2')[0] == 404


def test_state_reports_hold_ring_target_and_adapter(app):
    upload(app, 'recess.wav', make_wav(0.1))
    app.store.set_bells([RECESS])
    state = call(app, 'GET', '/api/state')[1]
    assert state['held'] is False
    assert state['ring_target']['label'] == 'Recess'
    assert state['adapter'] == {'connected': True, 'last_playback': None}
    assert call(app, 'PUT', '/api/settings', {'held': True}) == (
        200, {'enabled': True, 'master_volume': 80, 'held': True, 'time_format': '24h',
              'active_schedule': {'id': 'standard', 'name': 'Standard', 'manual': False}})
    state = call(app, 'GET', '/api/state')[1]
    assert state['held'] is True
    assert state['next_bell']['date'] == '2026-10-13'
    assert state['ring_target']['date'] == '2026-10-12'
    assert call(app, 'PUT', '/api/settings', {'held': 'yes'})[0] == 400


def test_ring_now_plays_ring_target_at_its_volume(app):
    upload(app, 'recess.wav', make_wav(0.1))
    app.store.set_bells([RECESS])
    assert call(app, 'POST', '/api/ring', {}) == (200, {'playing': 'recess.wav'})
    path, gain = app.player.plays[-1]
    assert path.endswith('recess.wav') and round(gain, 2) == 0.4
    app.store.set_bells([])
    assert call(app, 'POST', '/api/ring', {})[0] == 409


def test_test_tone_plays_at_master_volume(app):
    assert call(app, 'POST', '/api/test-tone', {})[0] == 404
    app.test_tone.write_bytes(make_wav(0.1))
    assert call(app, 'POST', '/api/test-tone', {}) == (200, {'playing': 'test-tone.wav'})
    assert app.player.plays[-1] == (str(app.test_tone), 0.8)



def raw_request(app, head, body=b'', gap=0.0):
    """Send head, optionally wait, then body, and return the status line (or the socket error)."""
    import socket
    import time
    sock = socket.create_connection(('127.0.0.1', app.port), timeout=3)
    try:
        sock.sendall(head)
        if gap:
            time.sleep(gap)
        if body:
            sock.sendall(body)
        return sock.recv(4096).split(b'\r\n', 1)[0]
    except OSError as e:
        return repr(e)
    finally:
        sock.close()


def test_negative_content_length_is_rejected_without_reading(app):
    for path in (b'/api/settings', b'/api/sounds?name=a.wav'):
        method = b'PUT' if path == b'/api/settings' else b'POST'
        head = method + b' ' + path + b' HTTP/1.1\r\nHost: x\r\nContent-Length: -1\r\n\r\n'
        assert raw_request(app, head) == b'HTTP/1.0 400 Bad Request'


def test_small_body_sent_after_headers_is_drained(app):
    head = b'POST /api/stop HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n'
    for _ in range(3):
        assert raw_request(app, head, b'{}', gap=0.05) == b'HTTP/1.0 200 OK'


def test_successful_gets_are_not_logged_but_changes_and_errors_are(app, log):
    call(app, 'GET', '/api/state')
    call(app, 'PUT', '/api/settings', {'master_volume': 50})
    call(app, 'GET', '/api/nope')
    assert not [line for line in log.infos if 'GET /api/state' in line]
    assert [line for line in log.infos if 'PUT /api/settings' in line]
    assert [line for line in log.infos if 'GET /api/nope' in line]


def test_time_format_setting(app):
    assert call(app, 'PUT', '/api/settings', {'time_format': '12h'})[1]['time_format'] == '12h'
    assert call(app, 'GET', '/api/state')[1]['time_format'] == '12h'
    assert call(app, 'PUT', '/api/settings', {'time_format': 'am/pm'})[0] == 400


def test_plays_are_logged_with_their_source(app):
    upload(app, 'recess.wav', make_wav(0.1))
    app.store.set_bells([RECESS])
    app.test_tone.write_bytes(make_wav(0.1))
    call(app, 'POST', '/api/play', {'sound': 'recess.wav'})
    call(app, 'POST', '/api/ring', {})
    call(app, 'POST', '/api/test-tone', {})
    app.player.fail = AudioError('The USB audio adapter is not connected')
    call(app, 'POST', '/api/play', {'sound': 'recess.wav'})
    status, body = call(app, 'GET', '/api/history')
    assert status == 200
    assert [(e['source'], e['result'], e['label']) for e in body['entries']] == [
        ('page', 'failed', ''), ('test_tone', 'played', ''), ('ring_now', 'played', 'Recess'),
        ('page', 'played', '')]
    assert 'not connected' in body['entries'][0]['error']


def test_skip_endpoint(app):
    upload(app, 'recess.wav', make_wav(0.1))
    app.store.set_bells([dict(RECESS, id='r1')])
    status, body = call(app, 'POST', '/api/bells/r1/skip', {'skip': True})
    assert status == 200 and body['skip_on'] == '2026-10-12'
    assert call(app, 'GET', '/api/state')[1]['next_bell']['date'] == '2026-10-13'
    assert call(app, 'POST', '/api/bells/r1/skip', {'skip': False})[1]['skip_on'] is None
    assert call(app, 'POST', '/api/bells/nope/skip', {'skip': True})[0] == 404
    assert call(app, 'POST', '/api/bells/r1/skip', {'skip': 'yes'})[0] == 400


def test_schedule_changes_are_logged(app):
    upload(app, 'recess.wav', make_wav(0.1))
    call(app, 'PUT', '/api/bells', {'bells': [dict(RECESS, id='r1')]})
    [b] = app.store.bells()
    call(app, 'PUT', '/api/bells', {'bells': [dict(b, enabled=False)]})
    call(app, 'PUT', '/api/bells', {'bells': [dict(b, enabled=True)]})
    call(app, 'POST', '/api/bells/r1/skip', {'skip': True})
    call(app, 'POST', '/api/bells/r1/skip', {'skip': False})
    call(app, 'PUT', '/api/settings', {'held': True})
    call(app, 'PUT', '/api/settings', {'held': True})
    call(app, 'PUT', '/api/settings', {'enabled': False, 'held': False})
    entries = call(app, 'GET', '/api/history')[1]['entries']
    results = [e['result'] for e in reversed(entries)]
    assert results == ['disabled', 'enabled', 'skip_set', 'skip_cleared', 'held', 'bells_off', 'resumed']
    skip = next(e for e in entries if e['result'] == 'skip_set')
    assert (skip['source'], skip['label'], skip['detail']) == ('page', 'Recess', '2026-10-12')


def test_ring_now_for_a_specific_bell(app):
    upload(app, 'recess.wav', make_wav(0.1))
    call(app, 'PUT', '/api/bells', {'bells': [dict(RECESS, id='r1')]})
    assert call(app, 'POST', '/api/play', {'bell': 'r1'}) == (200, {'playing': 'recess.wav'})
    assert round(app.player.plays[-1][1], 2) == 0.4
    entry = call(app, 'GET', '/api/history')[1]['entries'][0]
    assert (entry['source'], entry['label'], entry['result']) == ('ring_now', 'Recess', 'played')
    assert call(app, 'POST', '/api/play', {'bell': 'nope'})[0] == 404


def test_state_time_has_milliseconds(app):
    import re
    time = call(app, 'GET', '/api/state')[1]['time']
    assert re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[+-]\d\d:\d\d', time), time


def test_state_lists_schedules_and_the_active_one(app):
    upload(app, 'recess.wav', make_wav(0.1))
    call(app, 'PUT', '/api/bells', {'bells': [RECESS]})
    state = call(app, 'GET', '/api/state')[1]
    [schedule] = state['schedules']
    assert (schedule['id'], schedule['name'], schedule['default'], schedule['range']) == ('standard', 'Standard', True, None)
    assert schedule['bells'][0]['missing_sound'] is False
    assert state['active_schedule'] == {'id': 'standard', 'name': 'Standard', 'manual': False}
    assert [b['label'] for b in state['bells']] == ['Recess']


def test_schedule_endpoints(app):
    upload(app, 'recess.wav', make_wav(0.1))
    call(app, 'PUT', '/api/bells', {'bells': [RECESS]})
    status, winter = call(app, 'POST', '/api/schedules', {'name': 'Winter', 'copy_from': 'standard'})
    assert status == 201 and winter['name'] == 'Winter' and len(winter['bells']) == 1
    assert call(app, 'POST', '/api/schedules', {'name': 'winter'})[0] == 400
    assert call(app, 'POST', '/api/schedules', {'name': 'X', 'copy_from': 'nope'})[0] == 404
    status, body = call(app, 'PUT', '/api/schedules/%s' % winter['id'], {'range': {'from': '05-01', 'to': '09-30'}})
    assert status == 200 and body['range'] == {'from': '05-01', 'to': '09-30'}
    assert call(app, 'PUT', '/api/schedules/standard', {'range': {'from': '01-01', 'to': '01-31'}})[0] == 400
    assert call(app, 'PUT', '/api/schedules/nope', {'name': 'Y'})[0] == 404
    status, bells_body = call(app, 'PUT', '/api/bells?schedule=%s' % winter['id'],
                              {'bells': [dict(RECESS, label='Winter recess', time='10:30')]})
    assert status == 200 and bells_body['bells'][0]['label'] == 'Winter recess'
    assert call(app, 'PUT', '/api/bells?schedule=nope', {'bells': []})[0] == 404
    assert call(app, 'DELETE', '/api/schedules/standard')[0] == 400
    assert call(app, 'DELETE', '/api/schedules/%s' % winter['id'])[0] == 200
    assert call(app, 'DELETE', '/api/schedules/%s' % winter['id'])[0] == 404


def test_manual_pick_through_settings_is_shown_and_logged(app):
    status, summer = call(app, 'POST', '/api/schedules', {'name': 'Summer'})
    body = call(app, 'PUT', '/api/settings', {'active_schedule': summer['id']})[1]
    assert body['active_schedule'] == {'id': summer['id'], 'name': 'Summer', 'manual': True}
    assert call(app, 'GET', '/api/state')[1]['active_schedule']['manual'] is True
    assert call(app, 'PUT', '/api/settings', {'active_schedule': None})[1]['active_schedule']['id'] == 'standard'
    assert call(app, 'PUT', '/api/settings', {'active_schedule': 'nope'})[0] == 404
    assert call(app, 'PUT', '/api/settings', {'active_schedule': 5})[0] == 400
    changes = [(e['result'], e['label'], e['detail']) for e in reversed(call(app, 'GET', '/api/history')[1]['entries'])]
    assert changes == [('schedule_changed', 'Summer', 'manual'), ('schedule_changed', 'Standard', 'dates')]


def test_ring_and_skip_find_bells_in_any_schedule(app):
    upload(app, 'recess.wav', make_wav(0.1))
    summer = call(app, 'POST', '/api/schedules', {'name': 'Summer'})[1]
    [b] = call(app, 'PUT', '/api/bells?schedule=%s' % summer['id'], {'bells': [RECESS]})[1]['bells']
    assert call(app, 'POST', '/api/play', {'bell': b['id']})[0] == 200
    # Summer has no range and isn't the default, so it never applies: nothing to skip.
    assert call(app, 'POST', '/api/bells/%s/skip' % b['id'], {'skip': True})[0] == 400
    call(app, 'PUT', '/api/schedules/%s' % summer['id'], {'range': {'from': '10-01', 'to': '04-30'}})
    assert call(app, 'POST', '/api/bells/%s/skip' % b['id'], {'skip': True})[0] == 200
