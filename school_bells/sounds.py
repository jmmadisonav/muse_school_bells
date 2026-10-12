"""Stored bell sounds: name rules, WAV format checks, listing, and gain."""
import array
import audioop
import io
import math
import os
import re
import sys
import wave

from bells import ValidationError

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
RATE = 48000
CHANNELS = 2
SAMPLE_WIDTH = 2
NAME_RE = re.compile(r'^[A-Za-z0-9_\-][A-Za-z0-9 _.\-]{0,79}\.wav$')


def check_name(name):
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ValidationError('Sound names may use letters, digits, spaces, _, - and ., '
                              'and must end in .wav')
    return name


def sound_exists(sounds_dir, name):
    """True if name is a valid sound name and that file exists in sounds_dir."""
    return (isinstance(name, str) and bool(NAME_RE.match(name))
            and os.path.isfile(os.path.join(sounds_dir, name)))


def wav_seconds(data):
    """Return the length of WAV bytes in seconds, or raise ValidationError if the format is wrong."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            fmt = (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getcomptype())
            frames = w.getnframes()
    except (wave.Error, EOFError) as e:
        raise ValidationError('Not a readable WAV file (%s)' % e)
    if fmt != (RATE, CHANNELS, SAMPLE_WIDTH, 'NONE'):
        raise ValidationError('Sounds must be 48 kHz, 16-bit, stereo PCM WAV files')
    return frames / RATE


def list_sounds(sounds_dir):
    """List stored sounds by name. Unreadable files have seconds set to None so staff can delete them."""
    result = []
    for name in sorted(os.listdir(sounds_dir), key=str.lower):
        if not NAME_RE.match(name):
            continue
        try:
            with wave.open(os.path.join(sounds_dir, name)) as w:
                seconds = w.getnframes() / w.getframerate()
        except (OSError, wave.Error, EOFError):
            seconds = None
        result.append({'name': name, 'seconds': seconds})
    return result


def save_sound(sounds_dir, name, data, overwrite=False):
    path = os.path.join(sounds_dir, check_name(name))
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(name)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def apply_gain(frames, gain):
    """Scale 16-bit PCM frames by gain, clamped to the range 0 to 1."""
    gain = max(0.0, min(1.0, gain))
    if gain >= 1.0:
        return frames
    return audioop.mul(frames, SAMPLE_WIDTH, gain)


def make_tone_wav(hz=1000, seconds=3, level=0.25):
    """Return a sine tone as 48 kHz 16-bit stereo WAV bytes, with 10 ms fades to avoid clicks."""
    total = int(RATE * seconds)
    fade = RATE // 100
    peak = level * 32767
    samples = array.array('h')
    for n in range(total):
        envelope = min(1.0, n / fade, (total - n) / fade)
        value = int(peak * envelope * math.sin(2 * math.pi * hz * n / RATE))
        samples.append(value)
        samples.append(value)
    if sys.byteorder == 'big':
        samples.byteswap()
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(RATE)
        w.writeframes(samples.tobytes())
    return buffer.getvalue()
