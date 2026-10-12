"""Plays WAV files through the USB audio adapter with libusb.

The Muse kernel has no sound support, so this module streams PCM to the
adapter's isochronous endpoint itself.
"""
import ctypes.util
import glob
import os
import threading
import time
import wave
from datetime import datetime

import sounds

VENDOR_ID = 0x0D8C   # C-Media
PRODUCT_ID = 0x0014  # C-Media chipset in the Nextech XC4953 USB audio adapter
FRAMES_PER_PACKET = sounds.RATE // 1000  # one isochronous packet per 1 ms USB frame
PACKETS_PER_TRANSFER = 32
TRANSFERS_IN_FLIGHT = 4  # queued transfers that keep the stream from starving

_usb1 = None


class AudioError(RuntimeError):
    """The adapter or sound file can't be used. The message appears on the page."""


def _load_usb1():
    """Import usb1 on first use. Its library lookup can fail on embedded Linux, so add a fallback."""
    global _usb1
    if _usb1 is None:
        find_library = ctypes.util.find_library

        def find_with_fallback(name):
            found = find_library(name)
            if found is None and name == 'usb-1.0':
                return '/lib/libusb-1.0.so.0'
            return found

        ctypes.util.find_library = find_with_fallback
        import usb1
        _usb1 = usb1
    return _usb1


def adapter_connected(devices_dir='/sys/bus/usb/devices'):
    """True if the adapter is plugged in. Reads sysfs only, so it never opens the device."""
    want = ('%04x' % VENDOR_ID, '%04x' % PRODUCT_ID)
    for device in glob.glob(os.path.join(devices_dir, '*')):
        try:
            with open(os.path.join(device, 'idVendor')) as f:
                vendor = f.read().strip().lower()
            with open(os.path.join(device, 'idProduct')) as f:
                product = f.read().strip().lower()
        except OSError:
            continue
        if (vendor, product) == want:
            return True
    return False


def iter_chunks(read_frames, gain):
    """Yield (data, packet sizes) per transfer, reading frames with read_frames(count)."""
    frame_bytes = sounds.CHANNELS * sounds.SAMPLE_WIDTH
    packet_bytes = FRAMES_PER_PACKET * frame_bytes
    while True:
        data = read_frames(FRAMES_PER_PACKET * PACKETS_PER_TRANSFER)
        if not data:
            return
        data = sounds.apply_gain(data, gain)
        sizes = [packet_bytes] * (len(data) // packet_bytes)
        if len(data) % packet_bytes:
            sizes.append(len(data) % packet_bytes)
        yield bytearray(data), sizes


def _class_descriptors(extra):
    """Split a setting's extra bytes into USB Audio class-specific descriptors."""
    if isinstance(extra, (list, tuple)):
        extra = b''.join(bytes(d) for d in extra)
    extra = bytes(extra)
    found = []
    i = 0
    while i + 2 < len(extra):
        length = extra[i]
        if length < 3:
            break
        if extra[i + 1] == 0x24:  # CS_INTERFACE
            found.append(extra[i:i + length])
        i += length
    return found


def _playback_settings(device):
    """List the AudioStreaming alternate settings that have an isochronous OUT endpoint."""
    found = []
    for config in device:
        for interface in config:
            for setting in interface:
                if setting.getClass() != 1 or setting.getSubClass() != 2:
                    continue
                endpoints = [ep for ep in setting
                             if ep.getAttributes() & 0x03 == 1 and not ep.getAddress() & 0x80]
                fmt = [d for d in _class_descriptors(setting.getExtra())
                       if d[2] == 0x02 and len(d) >= 8 and d[3] == 1]  # FORMAT_TYPE_I
                if not endpoints or not fmt:
                    continue
                d = fmt[0]
                found.append({
                    'interface': setting.getNumber(),
                    'alt': setting.getAlternateSetting(),
                    'endpoint': endpoints[0].getAddress(),
                    'channels': d[4],
                    'subframe': d[5],
                    'continuous': d[7] == 0,
                    'rates': [int.from_bytes(d[k:k + 3], 'little') for k in range(8, len(d) - 2, 3)],
                })
    return found


def _supports_format(setting):
    rates = setting['rates']
    if setting['continuous'] and len(rates) >= 2:
        rate_ok = rates[0] <= sounds.RATE <= rates[1]
    else:
        rate_ok = sounds.RATE in rates
    return rate_ok and setting['channels'] == sounds.CHANNELS and setting['subframe'] == sounds.SAMPLE_WIDTH


def _unmute(handle, device, usb1):
    units = []
    # SET_CUR on the mute control of each feature unit, for the master and both
    # channels. Controls a unit doesn't have are rejected, which is fine.
    for config in device:
        for interface in config:
            for setting in interface:
                if setting.getClass() != 1 or setting.getSubClass() != 1:
                    continue
                for d in _class_descriptors(setting.getExtra()):
                    if d[2] != 0x06 or len(d) <= 3:  # FEATURE_UNIT
                        continue
                    units.append((setting.getNumber(), d[3]))
                    for channel in (0, 1, 2):
                        try:
                            handle.controlWrite(0x21, 0x01, 0x0100 | channel,
                                                (d[3] << 8) | setting.getNumber(), b'\x00')
                        except usb1.USBError:
                            pass
    return units


def _diagnose(handle, setting, units, rate_set):
    """Diagnostic (temporary): the adapter's settings as it reports them back."""
    def read(request_type, request, value, index, length):
        try:
            return handle.controlRead(request_type, request, value, index, length)
        except Exception:
            return None

    def db(raw):
        return '-' if raw is None or len(raw) < 2 else '%.1f' % (int.from_bytes(raw[:2], 'little', signed=True) / 256)

    alt = read(0x81, 0x0A, 0, setting['interface'], 1)  # GET_INTERFACE
    rate = read(0xA2, 0x81, 0x0100, setting['endpoint'], 3)  # GET_CUR sampling frequency
    parts = ['interface %d alt %d (reads %s)' % (setting['interface'], setting['alt'], alt[0] if alt else '-'),
             'rate set %s, reads %s' % (rate_set, int.from_bytes(rate, 'little') if rate else '-')]
    for interface, unit in units:
        index = (unit << 8) | interface
        mutes = [read(0xA1, 0x81, 0x0100 | ch, index, 1) for ch in (0, 1, 2)]
        volumes = [db(read(0xA1, 0x81, 0x0200 | ch, index, 2)) for ch in (0, 1, 2)]
        low, high = db(read(0xA1, 0x82, 0x0201, index, 2)), db(read(0xA1, 0x83, 0x0201, index, 2))
        parts.append('unit %d: mute %s, volume %s dB (range %s..%s)' % (
            unit, '/'.join(str(m[0]) if m else '-' for m in mutes), '/'.join(volumes), low, high))
    return 'Audio open: ' + '; '.join(parts)


class _Session:
    """One open, configured stream to the adapter."""

    def __init__(self, usb, handle, setting):
        self._usb = usb
        self._handle = handle
        self._setting = setting

    @classmethod
    def open(cls, log=None):
        usb1 = _load_usb1()
        usb = usb1.USBContext()
        try:
            handle = usb.openByVendorIDAndProductID(VENDOR_ID, PRODUCT_ID)
            if handle is None:
                raise AudioError('The USB audio adapter is not connected')
            device = handle.getDevice()
            matches = [s for s in _playback_settings(device) if _supports_format(s)]
            if not matches:
                raise AudioError('The USB audio adapter does not support 48 kHz 16-bit stereo')
            s = matches[0]
            handle.claimInterface(s['interface'])
            handle.setInterfaceAltSetting(s['interface'], s['alt'])
            rate_set = 'ok'
            try:
                # SET_CUR sampling frequency on the endpoint.
                handle.controlWrite(0x22, 0x01, 0x0100, s['endpoint'], sounds.RATE.to_bytes(3, 'little'))
            except usb1.USBError as e:
                rate_set = 'rejected (%s)' % e  # single-rate devices reject this request
            units = _unmute(handle, device, usb1)
            if log is not None:
                log.info(_diagnose(handle, s, units, rate_set))
            return cls(usb, handle, s)
        except AudioError:
            usb.close()
            raise
        except Exception as e:
            usb.close()
            raise AudioError('Cannot open the USB audio adapter: %r' % e)

    def stream(self, chunks, stop):
        """Send chunks as queued isochronous transfers until done or stop is set. Returns failures."""
        usb1 = _load_usb1()
        state = {'active': 0, 'errors': 0}

        def submit_next(transfer):
            if stop.is_set():
                return
            chunk = next(chunks, None)
            if chunk is None:
                return
            data, sizes = chunk
            transfer.setIsochronous(self._setting['endpoint'], data, callback=on_done,
                                    iso_transfer_length_list=sizes)
            transfer.submit()
            state['active'] += 1

        def on_done(transfer):
            state['active'] -= 1
            if transfer.getStatus() != usb1.TRANSFER_COMPLETED:
                state['errors'] += 1
            submit_next(transfer)

        transfers = [self._handle.getTransfer(iso_packets=PACKETS_PER_TRANSFER)
                     for _ in range(TRANSFERS_IN_FLIGHT)]
        for transfer in transfers:
            submit_next(transfer)
        while state['active']:
            self._usb.handleEvents()
        for transfer in transfers:
            transfer.close()
        return state['errors']

    def close(self):
        interface = self._setting['interface']
        for step in (lambda: self._handle.setInterfaceAltSetting(interface, 0),
                     lambda: self._handle.releaseInterface(interface),
                     self._handle.close, self._usb.close):
            try:
                step()
            except Exception:
                pass


class Player:
    """Plays one WAV file at a time. A new play stops the current one."""

    def __init__(self, log):
        self._log = log
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self._playing = None
        self.last_playback = None  # {time, failed_transfers} after each completed stream

    @property
    def playing(self):
        return self._playing

    def play(self, path, gain):
        """Start playing path at gain (0 to 1). Raises AudioError if the file or adapter can't be opened."""
        with self._lock:
            self._stop_locked()
            try:
                wav = wave.open(path, 'rb')
            except (OSError, wave.Error, EOFError) as e:
                raise AudioError('Cannot read %s (%s)' % (os.path.basename(path), e))
            try:
                session = _Session.open(self._log)
            except Exception:
                wav.close()
                raise
            stop = threading.Event()
            self._stop = stop
            self._playing = os.path.basename(path)
            self._thread = threading.Thread(target=self._run, args=(session, wav, gain, stop),
                                            daemon=True, name='bell-player')
            self._thread.start()

    def stop(self):
        with self._lock:
            self._stop_locked()

    def _stop_locked(self):
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=2)
            self._thread = None
        self._playing = None

    def _run(self, session, wav, gain, stop):
        name = self._playing
        try:
            # Diagnostic (temporary): count what was streamed, and how long it took.
            started, sent = time.monotonic(), [0]

            def counted(chunks):
                for data, sizes in chunks:
                    sent[0] += len(sizes)
                    yield data, sizes

            errors = session.stream(counted(iter_chunks(wav.readframes, gain)), stop)
            self._log.info('Audio stream: %s, %d packets in %.2f s, %d failed' % (
                name, sent[0], time.monotonic() - started, errors))
            self.last_playback = {'time': datetime.now().isoformat(timespec='seconds'),
                                  'failed_transfers': errors}
            if errors:
                self._log.error('%d USB transfers failed while playing %s' % (errors, name))
        except Exception as e:
            self._log.error('Playback of %s failed: %r' % (name, e))
        finally:
            wav.close()
            session.close()
            if self._stop is stop:
                self._playing = None
