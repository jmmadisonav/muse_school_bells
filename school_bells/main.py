import ctypes.util
import math

from mojo import context

log = context.log

VENDOR_ID = 0x0D8C   # C-Media
PRODUCT_ID = 0x0014  # Unitek Y-247A USB audio adapter
TONE_HZ = 1000
TONE_SECONDS = 3
TONE_LEVEL = 0.25           # fraction of full scale, about -12 dBFS
PACKETS_PER_TRANSFER = 32   # one isochronous packet per 1 ms USB frame
TRANSFERS_IN_FLIGHT = 4     # queued transfers that keep the stream from starving

# python-libusb1 locates libusb with ctypes.util.find_library, which can fail on
# embedded Linux without ldconfig. Fall back to the library the probe found.
_find_library = ctypes.util.find_library


def _find_library_with_fallback(name):
    found = _find_library(name)
    if found is None and name == 'usb-1.0':
        return '/lib/libusb-1.0.so.0'
    return found


ctypes.util.find_library = _find_library_with_fallback

import usb1  # noqa: E402  (must load after the find_library fallback)


def class_descriptors(extra):
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


def find_playback_settings(device):
    """List the AudioStreaming alternate settings that have an isochronous OUT endpoint."""
    found = []
    for config in device:
        for interface in config:
            for setting in interface:
                if setting.getClass() != 1 or setting.getSubClass() != 2:
                    continue
                endpoints = [ep for ep in setting
                             if ep.getAttributes() & 0x03 == 1 and not ep.getAddress() & 0x80]
                fmt = [d for d in class_descriptors(setting.getExtra())
                       if d[2] == 0x02 and len(d) >= 8 and d[3] == 1]  # FORMAT_TYPE_I
                if not endpoints or not fmt:
                    continue
                d = fmt[0]
                rates = [int.from_bytes(d[k:k + 3], 'little') for k in range(8, len(d) - 2, 3)]
                found.append({
                    'interface': setting.getNumber(),
                    'alt': setting.getAlternateSetting(),
                    'endpoint': endpoints[0].getAddress(),
                    'max_packet': endpoints[0].getMaxPacketSize(),
                    'channels': d[4],
                    'subframe': d[5],
                    'bits': d[6],
                    'continuous': d[7] == 0,
                    'rates': rates,
                })
    return found


def find_feature_units(device):
    """Return (interface, unit ID) pairs for every AudioControl feature unit."""
    units = []
    for config in device:
        for interface in config:
            for setting in interface:
                if setting.getClass() == 1 and setting.getSubClass() == 1:
                    for d in class_descriptors(setting.getExtra()):
                        if d[2] == 0x06 and len(d) > 3:  # FEATURE_UNIT
                            units.append((setting.getNumber(), d[3]))
    return units


def choose_rate(setting):
    rates = setting['rates']
    if setting['continuous'] and len(rates) >= 2:
        low, high = rates[0], rates[1]
        return 48000 if low <= 48000 <= high else high
    for rate in (48000, 44100):
        if rate in rates:
            return rate
    return rates[0]


def unmute(handle, device):
    # SET_CUR on the mute control of each feature unit, for the master and both
    # channels. Controls a unit doesn't have are rejected, which is fine.
    for interface, unit in find_feature_units(device):
        for channel in (0, 1, 2):
            try:
                handle.controlWrite(0x21, 0x01, 0x0100 | channel, (unit << 8) | interface, b'\x00')
                log.info('Unmuted feature unit %d, channel %d' % (unit, channel))
            except usb1.USBError:
                pass


def make_tone(rate, channels, subframe):
    """Return PCM bytes for the test tone, with 10 ms fades to avoid clicks."""
    total = int(rate * TONE_SECONDS)
    fade = int(rate * 0.01)
    peak = TONE_LEVEL * (2 ** (8 * subframe - 1) - 1)
    pcm = bytearray()
    for n in range(total):
        envelope = min(1.0, n / fade, (total - n) / fade)
        value = int(peak * envelope * math.sin(2 * math.pi * TONE_HZ * n / rate))
        pcm += value.to_bytes(subframe, 'little', signed=True) * channels
    return bytes(pcm)


def packet_sizes(total_bytes, rate, frame_bytes):
    """Split the stream into 1 ms packets, spreading fractional rates like 44.1 kHz."""
    sizes = []
    remainder = 0
    sent = 0
    while sent < total_bytes:
        remainder += rate
        frames, remainder = divmod(remainder, 1000)
        size = min(frames * frame_bytes, total_bytes - sent)
        sizes.append(size)
        sent += size
    return sizes


def stream(usb, handle, endpoint, pcm, sizes):
    """Send the PCM as queued isochronous transfers. Returns the failed-transfer count."""
    chunks = []
    offset = 0
    for i in range(0, len(sizes), PACKETS_PER_TRANSFER):
        group = sizes[i:i + PACKETS_PER_TRANSFER]
        chunks.append((bytearray(pcm[offset:offset + sum(group)]), group))
        offset += sum(group)
    pending = iter(chunks)
    state = {'active': 0, 'errors': 0}

    def submit_next(transfer):
        chunk = next(pending, None)
        if chunk is None:
            return
        data, group = chunk
        transfer.setIsochronous(endpoint, data, callback=on_done, iso_transfer_length_list=group)
        transfer.submit()
        state['active'] += 1

    def on_done(transfer):
        state['active'] -= 1
        if transfer.getStatus() != usb1.TRANSFER_COMPLETED:
            state['errors'] += 1
        submit_next(transfer)

    transfers = [handle.getTransfer(iso_packets=PACKETS_PER_TRANSFER)
                 for _ in range(TRANSFERS_IN_FLIGHT)]
    for transfer in transfers:
        submit_next(transfer)
    while state['active']:
        usb.handleEvents()
    for transfer in transfers:
        transfer.close()
    return state['errors']


def play_test_tone():
    with usb1.USBContext() as usb:
        handle = usb.openByVendorIDAndProductID(VENDOR_ID, PRODUCT_ID)
        if handle is None:
            log.error('USB audio adapter %04x:%04x not found' % (VENDOR_ID, PRODUCT_ID))
            return
        device = handle.getDevice()
        settings = find_playback_settings(device)
        for s in settings:
            log.info('Playback option: %r' % s)
        if not settings:
            log.error('No PCM playback interface found on the adapter')
            handle.close()
            return

        # Prefer 16-bit stereo, the most widely supported format.
        s = sorted(settings, key=lambda s: (s['subframe'] != 2, s['channels'] != 2))[0]
        rate = choose_rate(s)
        frame_bytes = s['channels'] * s['subframe']
        log.info('Using interface %d alt %d, endpoint 0x%02x, %d Hz, %d ch, %d-bit' % (
            s['interface'], s['alt'], s['endpoint'], rate, s['channels'], s['bits']))
        if -(-rate // 1000) * frame_bytes > s['max_packet']:
            log.warn('Packets exceed the endpoint max packet size of %d bytes' % s['max_packet'])

        handle.claimInterface(s['interface'])
        try:
            handle.setInterfaceAltSetting(s['interface'], s['alt'])
            try:
                # SET_CUR sampling frequency on the endpoint.
                handle.controlWrite(0x22, 0x01, 0x0100, s['endpoint'], rate.to_bytes(3, 'little'))
            except usb1.USBError as e:
                log.warn('Sample-rate request rejected (fine for single-rate devices): %r' % e)
            unmute(handle, device)

            pcm = make_tone(rate, s['channels'], s['subframe'])
            sizes = packet_sizes(len(pcm), rate, frame_bytes)
            log.info('Playing %d Hz tone for %d s (%d packets)' % (TONE_HZ, TONE_SECONDS, len(sizes)))
            errors = stream(usb, handle, s['endpoint'], pcm, sizes)
            log.info('Playback finished, %d failed transfers' % errors)
        finally:
            handle.setInterfaceAltSetting(s['interface'], 0)
            handle.releaseInterface(s['interface'])
            handle.close()


try:
    play_test_tone()
except Exception as e:
    log.error('Test tone failed: %r' % e)

# leave this as the last line in the Python script
context.run(globals())
