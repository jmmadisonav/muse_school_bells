import glob
import os
import platform
import shutil
import subprocess

from mojo import context

log = context.log


def read(path):
    """Return the stripped contents of a small text file, or None if unreadable."""
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


def section(title):
    log.info('===== ' + title + ' =====')


def probe_environment():
    section('Environment')
    log.info('platform: ' + platform.platform())
    log.info('python: ' + platform.python_version())
    try:
        log.info('uid: ' + str(os.getuid()) + ' euid: ' + str(os.geteuid()))
    except Exception as e:
        log.info('uid lookup failed: ' + repr(e))


def probe_usb_devices():
    # Each USB device appears in sysfs with idVendor/idProduct; its interfaces
    # carry bInterfaceClass, where 01 is the USB Audio class.
    section('USB devices (/sys/bus/usb/devices)')
    devices = sorted(glob.glob('/sys/bus/usb/devices/*'))
    if not devices:
        log.info('No entries found, or /sys is not visible to this program.')
        return
    for dev in devices:
        vid = read(os.path.join(dev, 'idVendor'))
        if vid is None:
            continue  # interface entries are handled below
        pid = read(os.path.join(dev, 'idProduct'))
        maker = read(os.path.join(dev, 'manufacturer')) or '?'
        product = read(os.path.join(dev, 'product')) or '?'
        log.info('%s  %s:%s  %s / %s' % (os.path.basename(dev), vid, pid, maker, product))
        for intf in sorted(glob.glob(dev + '/' + os.path.basename(dev) + ':*')):
            cls = read(os.path.join(intf, 'bInterfaceClass'))
            driver = os.path.realpath(os.path.join(intf, 'driver'))
            driver = os.path.basename(driver) if os.path.exists(driver) else 'none'
            tag = '  <-- USB AUDIO' if cls == '01' else ''
            log.info('    %s class=%s driver=%s%s' % (os.path.basename(intf), cls, driver, tag))


def probe_alsa():
    # If a kernel driver (snd-usb-audio) claimed the adapter, ALSA lists it here.
    section('ALSA sound cards')
    for path in ('/proc/asound/cards', '/proc/asound/pcm'):
        content = read(path)
        log.info(path + ':')
        log.info(content if content else '    (missing or empty)')
    try:
        log.info('/dev/snd: ' + ', '.join(sorted(os.listdir('/dev/snd'))))
    except Exception as e:
        log.info('/dev/snd not accessible: ' + repr(e))


def probe_commands():
    section('System tools')
    for cmd in (['lsusb'], ['aplay', '-l']):
        if shutil.which(cmd[0]) is None:
            log.info(cmd[0] + ': not installed')
            continue
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            log.info(' '.join(cmd) + ' (exit ' + str(out.returncode) + '):')
            log.info(out.stdout.strip() or out.stderr.strip() or '(no output)')
        except Exception as e:
            log.info(' '.join(cmd) + ' failed: ' + repr(e))


def probe_kernel_sound():
    # Tells apart "sound support not built" from "built as modules but not loaded".
    section('Kernel sound support')
    release = platform.release()
    try:
        import gzip
        with gzip.open('/proc/config.gz', 'rt') as f:
            lines = [l.strip() for l in f if l.startswith(('CONFIG_SND=', 'CONFIG_SND_USB', 'CONFIG_SOUND='))
                     or l.startswith(('# CONFIG_SND ', '# CONFIG_SND_USB_AUDIO ', '# CONFIG_SOUND '))]
        log.info('/proc/config.gz: ' + ('; '.join(lines) if lines else 'no CONFIG_SND/SOUND lines'))
    except Exception as e:
        log.info('/proc/config.gz not readable: ' + repr(e))
    found = glob.glob('/lib/modules/' + release + '/**/snd*usb*', recursive=True)
    log.info('snd usb modules on disk: ' + (', '.join(found) if found else 'none'))
    log.info('/sys/module/snd loaded: ' + str(os.path.isdir('/sys/module/snd')))


def probe_userspace_usb():
    # Checks whether Python could drive the adapter directly through libusb.
    section('Userspace USB access')
    try:
        log.info('groups: ' + str(os.getgroups()))
    except Exception as e:
        log.info('groups lookup failed: ' + repr(e))
    libs = sorted(set(glob.glob('/usr/lib/**/libusb-1.0.so*', recursive=True)
                      + glob.glob('/lib/**/libusb-1.0.so*', recursive=True)))
    log.info('libusb-1.0 libraries: ' + (', '.join(libs) if libs else 'none found'))
    for dev in sorted(glob.glob('/sys/bus/usb/devices/*')):
        intf_classes = [read(p) for p in glob.glob(dev + '/*:*/bInterfaceClass')]
        if '01' not in intf_classes:
            continue
        bus, num = read(os.path.join(dev, 'busnum')), read(os.path.join(dev, 'devnum'))
        if bus is None or num is None:
            continue
        node = '/dev/bus/usb/%03d/%03d' % (int(bus), int(num))
        try:
            st = os.stat(node)
            log.info('%s mode=%o uid=%d gid=%d readable=%s writable=%s' % (
                node, st.st_mode & 0o777, st.st_uid, st.st_gid,
                os.access(node, os.R_OK), os.access(node, os.W_OK)))
        except Exception as e:
            log.info(node + ' not accessible: ' + repr(e))


for probe in (probe_environment, probe_usb_devices, probe_alsa, probe_commands,
              probe_kernel_sound, probe_userspace_usb):
    try:
        probe()
    except Exception as e:
        log.error(probe.__name__ + ' raised ' + repr(e))

log.info('USB audio probe complete')

# leave this as the last line in the Python script
context.run(globals())
