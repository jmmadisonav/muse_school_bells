import struct
import time

import pytest

import audio
from helpers import make_wav


def reader(data):
    position = [0]

    def read_frames(count):
        chunk = data[position[0]:position[0] + count * 4]
        position[0] += len(chunk)
        return chunk
    return read_frames


def test_iter_chunks_splits_one_second_into_1ms_packets():
    data = bytes(48000 * 4)
    chunks = list(audio.iter_chunks(reader(data), 1.0))
    assert len(chunks) == 32  # 31 full transfers of 1536 frames, then 384 frames
    assert chunks[0][1] == [192] * 32
    assert chunks[-1][1] == [192] * 8
    assert sum(len(d) for d, _ in chunks) == len(data)
    assert all(sum(sizes) == len(d) for d, sizes in chunks)


def test_iter_chunks_ends_with_partial_packet():
    assert list(audio.iter_chunks(reader(bytes(100 * 4)), 1.0)) == [(bytearray(400), [192, 192, 16])]


def test_iter_chunks_applies_gain():
    data = struct.pack('<hh', 1000, -1000) * 48
    [(chunk, sizes)] = list(audio.iter_chunks(reader(data), 0.5))
    assert struct.unpack('<hh', bytes(chunk[:4])) == (500, -500)
    assert sizes == [192]


def test_importing_audio_does_not_load_libusb():
    assert audio._usb1 is None


def test_adapter_connected_reads_sysfs(tmp_path):
    hub = tmp_path / '1-1'
    hub.mkdir()
    (hub / 'idVendor').write_text('0424\n')
    (hub / 'idProduct').write_text('2514\n')
    assert audio.adapter_connected(str(tmp_path)) is False
    adapter = tmp_path / '1-1.3'
    adapter.mkdir()
    (adapter / 'idVendor').write_text('0d8c\n')
    (adapter / 'idProduct').write_text('0014\n')
    assert audio.adapter_connected(str(tmp_path)) is True
    assert audio.adapter_connected(str(tmp_path / 'missing')) is False


class FakeSession:
    def __init__(self):
        self.closed = False
        self.frames = 0

    def stream(self, chunks, stop):
        for data, _ in chunks:
            self.frames += len(data) // 4
        return 2

    def close(self):
        self.closed = True


def test_player_records_last_playback_and_clears_playing(tmp_path, log, monkeypatch):
    path = tmp_path / 'a.wav'
    path.write_bytes(make_wav(0.1))
    session = FakeSession()
    monkeypatch.setattr(audio._Session, 'open', classmethod(lambda cls, log=None: session))
    player = audio.Player(log)
    assert player.last_playback is None
    player.play(str(path), 1.0)
    deadline = time.time() + 2
    while player.playing is not None and time.time() < deadline:
        time.sleep(0.01)
    assert player.playing is None
    assert session.frames == 4800 and session.closed
    assert player.last_playback['failed_transfers'] == 2
    assert len(player.last_playback['time']) == 19  # YYYY-MM-DDTHH:MM:SS
    assert log.errors == ['2 USB transfers failed while playing a.wav']


def test_player_raises_audio_error_for_unreadable_file(tmp_path, log):
    with pytest.raises(audio.AudioError):
        audio.Player(log).play(str(tmp_path / 'nope.wav'), 1.0)
