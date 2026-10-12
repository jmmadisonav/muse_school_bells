import struct

import audio


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
