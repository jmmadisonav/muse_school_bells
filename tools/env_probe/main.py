"""Checks what the school_bells program needs from the controller: see Phase 0 in the spec."""
import glob
import os
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mojo import context

log = context.log
MARKER = 'bells_probe_marker.txt'
PORT = 8080


def candidate_dirs():
    dirs = []
    if '__file__' in globals():
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
    dirs += [os.getcwd(), os.path.expanduser('~'), '/data', '/mnt/data', '/var/lib', '/tmp']
    dirs += sorted(glob.glob('/mnt/*'))
    unique = []
    for d in dirs:
        if d not in unique:
            unique.append(d)
    return unique


def probe_paths():
    log.info('__file__: %r' % globals().get('__file__'))
    log.info('cwd: %s' % os.getcwd())
    log.info('sys.path[:4]: %s' % sys.path[:4])
    for d in candidate_dirs():
        marker = os.path.join(d, MARKER)
        earlier = None
        try:
            with open(marker) as f:
                earlier = f.read().strip()
        except OSError:
            pass
        try:
            with open(marker, 'w') as f:
                f.write(time.strftime('%Y-%m-%d %H:%M:%S'))
            free_mb = shutil.disk_usage(d).free // (1024 * 1024)
            log.info('%s: writable, %d MB free, marker from an earlier run: %s'
                     % (d, free_mb, earlier or 'none'))
        except OSError as e:
            log.info('%s: not writable (%s)' % (d, e.strerror))


def probe_clock():
    log.info('local time: %s' % time.strftime('%Y-%m-%d %H:%M:%S %Z (UTC%z)'))
    log.info('time.tzname: %s, TZ: %r' % (time.tzname, os.environ.get('TZ')))
    log.info('/etc/localtime -> %s' % os.path.realpath('/etc/localtime'))
    for path in ('/etc/timezone', '/etc/systemd/timesyncd.conf', '/etc/ntp.conf',
                 '/etc/chrony.conf', '/etc/chrony/chrony.conf'):
        log.info('%s exists: %s' % (path, os.path.exists(path)))


class Hello(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'school_bells probe OK\n'
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        log.info('probe http: ' + fmt % args)


def probe_port():
    try:
        server = ThreadingHTTPServer(('', PORT), Hello)
    except OSError as e:
        log.error('Cannot listen on port %d: %s' % (PORT, e))
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info('Listening on port %d. From a PC, run: curl.exe http://<controller-ip>:%d/' % (PORT, PORT))


for probe in (probe_paths, probe_clock, probe_port):
    try:
        probe()
    except Exception as e:
        log.error('%s raised %r' % (probe.__name__, e))

# leave this as the last line in the Python script
context.run(globals())
