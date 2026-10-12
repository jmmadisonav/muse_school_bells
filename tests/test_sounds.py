import struct

import pytest

import sounds
from bells import ValidationError
from helpers import make_wav


@pytest.mark.parametrize('name', ['recess.wav', 'Recess bell 2.wav', 'a-b_c.d.wav', '_x.wav'])
def test_check_name_accepts(name):
    assert sounds.check_name(name) == name


@pytest.mark.parametrize('name', ['../x.wav', 'a/b.wav', 'a\\b.wav', '.hidden.wav', ' x.wav',
                                  'x.mp3', '.wav', '', None, 'x' * 90 + '.wav'])
def test_check_name_rejects(name):
    with pytest.raises(ValidationError):
        sounds.check_name(name)


def test_sound_exists_refuses_paths_outside_dir(tmp_path):
    (tmp_path / 'outside.wav').write_bytes(b'x')
    inner = tmp_path / 'sounds'
    inner.mkdir()
    (inner / 'in.wav').write_bytes(b'x')
    assert sounds.sound_exists(str(inner), 'in.wav')
    assert not sounds.sound_exists(str(inner), '../outside.wav')
    assert not sounds.sound_exists(str(inner), 'missing.wav')


def test_wav_seconds_accepts_48k_16bit_stereo():
    assert sounds.wav_seconds(make_wav(1.0)) == pytest.approx(1.0)


@pytest.mark.parametrize('data', [
    make_wav(0.1, rate=44100), make_wav(0.1, channels=1), make_wav(0.1, width=1), b'not a wav',
], ids=['44k', 'mono', '8bit', 'junk'])
def test_wav_seconds_rejects_other_formats(data):
    with pytest.raises(ValidationError):
        sounds.wav_seconds(data)


def test_list_sounds_sorts_and_flags_unreadable(tmp_path):
    (tmp_path / 'b.wav').write_bytes(make_wav(0.5))
    (tmp_path / 'A.wav').write_bytes(make_wav(0.25))
    (tmp_path / 'broken.wav').write_bytes(b'junk')
    (tmp_path / 'c.wav.tmp').write_bytes(b'partial')
    assert sounds.list_sounds(str(tmp_path)) == [
        {'name': 'A.wav', 'seconds': 0.25},
        {'name': 'b.wav', 'seconds': 0.5},
        {'name': 'broken.wav', 'seconds': None},
    ]


def test_save_sound_refuses_overwrite_unless_asked(tmp_path):
    sounds.save_sound(str(tmp_path), 'a.wav', b'one')
    with pytest.raises(FileExistsError):
        sounds.save_sound(str(tmp_path), 'a.wav', b'two')
    sounds.save_sound(str(tmp_path), 'a.wav', b'two', overwrite=True)
    assert (tmp_path / 'a.wav').read_bytes() == b'two'
    assert not (tmp_path / 'a.wav.tmp').exists()


def test_apply_gain_scales_and_clamps():
    frames = struct.pack('<hh', 1000, -1000)
    assert struct.unpack('<hh', sounds.apply_gain(frames, 0.5)) == (500, -500)
    assert sounds.apply_gain(frames, 1.0) == frames
    assert sounds.apply_gain(frames, 3.0) == frames
    assert struct.unpack('<hh', sounds.apply_gain(frames, -1)) == (0, 0)


def test_make_tone_wav_is_three_seconds_at_quarter_level():
    import array
    import io
    import wave
    data = sounds.make_tone_wav()
    assert sounds.wav_seconds(data) == pytest.approx(3.0)
    with wave.open(io.BytesIO(data)) as w:
        samples = array.array('h', w.readframes(w.getnframes()))
    assert 8150 <= max(samples) <= 8192
    assert samples[0] == 0 and samples[1] == 0
