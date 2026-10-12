"""Test doubles and fixtures shared by the test modules."""
import io
import math
import os
import struct
import wave


class ListLog:
    """Stands in for context.log and records messages."""

    def __init__(self):
        self.infos = []
        self.errors = []

    def info(self, message):
        self.infos.append(message)

    def error(self, message):
        self.errors.append(message)


class FakePlayer:
    """Stands in for audio.Player and records what it was asked to play."""

    def __init__(self, fail=None):
        self.plays = []
        self.stops = 0
        self.playing = None
        self.fail = fail

    def play(self, path, gain):
        if self.fail is not None:
            raise self.fail
        self.plays.append((path, gain))
        self.playing = os.path.basename(path)

    def stop(self):
        self.stops += 1
        self.playing = None


def make_wav(seconds=1.0, rate=48000, channels=2, width=2, tone_hz=440):
    """Return WAV bytes. 16-bit files hold a sine tone; other widths hold silence."""
    frames = int(seconds * rate)
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        if width == 2:
            samples = (int(8000 * math.sin(2 * math.pi * tone_hz * n / rate)) for n in range(frames))
            w.writeframes(b''.join(struct.pack('<h', s) * channels for s in samples))
        else:
            w.writeframes(bytes([128]) * frames * channels * width)
    return buffer.getvalue()
