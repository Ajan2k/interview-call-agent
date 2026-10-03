"""Unit tests for the pure audio/WAV helper functions in voice.py:
create_wav_buffer, strip_wav_header.
"""
import io
import wave

import pytest

from routes import voice

pytestmark = pytest.mark.unit


class TestCreateWavBuffer:
    def test_produces_readable_wav_with_expected_params(self):
        pcm = b"\x01\x00" * 160  # 160 frames of 16-bit mono
        blob = voice.create_wav_buffer(pcm, sample_rate=16000)

        assert blob.startswith(b"RIFF")
        with wave.open(io.BytesIO(blob), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.readframes(wf.getnframes()) == pcm

    def test_honours_custom_sample_rate(self):
        blob = voice.create_wav_buffer(b"\x00\x00" * 10, sample_rate=8000)
        with wave.open(io.BytesIO(blob), "rb") as wf:
            assert wf.getframerate() == 8000

    def test_empty_pcm_yields_valid_but_empty_wav(self):
        blob = voice.create_wav_buffer(b"")
        with wave.open(io.BytesIO(blob), "rb") as wf:
            assert wf.getnframes() == 0


class TestStripWavHeader:
    def test_non_riff_bytes_returned_unchanged(self):
        raw = b"\x10\x00\x20\x00not-a-wav"
        assert voice.strip_wav_header(raw) == raw

    def test_matching_rate_mono_returns_raw_pcm(self, wav_bytes):
        pcm_frames = 160
        blob = wav_bytes(sample_rate=16000, nchannels=1, n_frames=pcm_frames)
        out = voice.strip_wav_header(blob, target_rate=16000)

        # Header stripped: length equals frames * 2 bytes (16-bit mono), no RIFF prefix.
        assert not out.startswith(b"RIFF")
        assert len(out) == pcm_frames * 2

    def test_stereo_is_downmixed_to_mono(self, wav_bytes):
        n = 100
        stereo = wav_bytes(sample_rate=16000, nchannels=2, n_frames=n)
        out = voice.strip_wav_header(stereo, target_rate=16000)
        # Mono output should be half the sample count of the stereo interleaved data.
        assert len(out) == n * 2  # n frames * 2 bytes, single channel

    def test_resamples_when_rate_differs(self, wav_bytes):
        # 8kHz source upsampled to 16kHz should roughly double in length.
        src = wav_bytes(sample_rate=8000, nchannels=1, n_frames=800)
        out = voice.strip_wav_header(src, target_rate=16000)
        assert not out.startswith(b"RIFF")
        # ratecv upsampling ~2x; allow slack for filter warm-up.
        assert 2800 < len(out) < 3400

    def test_corrupt_riff_falls_back_to_header_slice(self):
        # Starts with RIFF but is not a parseable wave -> except branch slices 44 bytes.
        corrupt = b"RIFF" + b"\x00" * 40 + b"PAYLOAD-DATA"
        out = voice.strip_wav_header(corrupt)
        assert out == b"PAYLOAD-DATA"
