"""Checks the school_bells touch points from a second program.

Load this program while school_bells is running, with tone.wav uploaded.
"""
from mojo import context

log = context.log
device = context.devices.get('school_bells')

for name in ('enabled', 'master_volume', 'playing', 'next_bell', 'last_error'):
    try:
        log.info('%s = %r' % (name, getattr(device, name).value))
    except Exception as e:
        log.error('Reading %s failed: %r' % (name, e))

device.playing.watch(lambda event: log.info('playing -> %r' % event.newValue))
device.last_error.watch(lambda event: log.info('last_error -> %r' % event.newValue))
device.listen('bell_rang', lambda event: log.info('bell_rang %r' % event.arguments))

try:
    device.play('tone.wav')
    log.info('Sent play tone.wav')
except Exception as e:
    log.error('play command failed: %r' % e)

# leave this as the last line in the Python script
context.run(globals())
