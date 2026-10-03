import os
import io
import wave
import time
import audioop
import logging
from core.config import settings

logger = logging.getLogger("voice.audio")


class AudioProcessor:
    """Provides pure audio/WAV manipulation utilities for 16-bit PCM streams."""

    @staticmethod
    def create_wav_buffer(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
        """Wrap raw PCM bytes into a valid WAV file in-memory."""
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit mono
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return wav_io.getvalue()

    @staticmethod
    def strip_wav_header(audio_bytes: bytes, target_rate: int = 16000) -> bytes:
        """If the bytes have a RIFF WAV header, strip it and resample to target_rate."""
        if not audio_bytes.startswith(b"RIFF"):
            return audio_bytes
        try:
            wav_io = io.BytesIO(audio_bytes)
            with wave.open(wav_io, "rb") as wf:
                framerate = wf.getframerate()
                sampwidth = wf.getsampwidth()
                nchannels = wf.getnchannels()
                frames = wf.readframes(wf.getnframes())

            if nchannels != 1:
                frames = audioop.tomono(frames, sampwidth, 0.5, 0.5)

            if framerate != target_rate:
                logger.info(f"[TTS] Resampling audio from {framerate}Hz to {target_rate}Hz")
                frames, _ = audioop.ratecv(frames, sampwidth, 1, framerate, target_rate, None)
            else:
                logger.info(f"[TTS] Parsed WAV header: Sample Rate = {framerate}Hz (matches target)")

            return frames
        except Exception as e:
            logger.error(f"[TTS] Failed to parse WAV header: {e}")
            return audio_bytes[44:] if len(audio_bytes) > 44 else audio_bytes


class CallRecorder:
    """Records both sides of a call as 16 kHz mono PCM tracks aligned by wall clock,
    then mixes them into a single WAV. The caller's mic frames stream continuously,
    so they form the timeline; agent audio is padded to its scheduled playback time."""

    BYTES_PER_SEC = 32000  # 16000 Hz * 2 bytes

    def __init__(self, call_id: str):
        self.call_id = call_id
        self.start_time = time.time()
        self.caller_track = bytearray()
        self.agent_track = bytearray()

    def _pad_to(self, track: bytearray, at_time: float) -> None:
        target = int((at_time - self.start_time) * self.BYTES_PER_SEC)
        target -= target % 2
        if target > len(track):
            track.extend(b"\x00" * (target - len(track)))

    def add_caller(self, pcm: bytes) -> None:
        self.caller_track.extend(pcm)

    def add_agent(self, pcm: bytes, at_time: float) -> None:
        self._pad_to(self.agent_track, at_time)
        self.agent_track.extend(pcm)

    def save(self, recordings_dir: str | None = None) -> str | None:
        try:
            if not self.caller_track and not self.agent_track:
                return None
            n = max(len(self.caller_track), len(self.agent_track))
            caller = bytes(self.caller_track) + b"\x00" * (n - len(self.caller_track))
            agent = bytes(self.agent_track) + b"\x00" * (n - len(self.agent_track))
            mixed = audioop.add(caller, agent, 2)

            target_dir = recordings_dir or str(settings.RECORDINGS_DIR)
            os.makedirs(target_dir, exist_ok=True)
            filename = f"{self.call_id}.wav"
            path = os.path.join(target_dir, filename)
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(mixed)
            logger.info(f"[RECORDING] Saved {filename} ({len(mixed)} bytes, {len(mixed)/self.BYTES_PER_SEC:.1f}s)")
            self.enforce_retention_policy(target_dir)
            return filename
        except Exception as e:
            logger.error(f"[RECORDING] Failed to save: {e}")
            return None

    @staticmethod
    def enforce_retention_policy(
        recordings_dir: str,
        max_days: int | None = None,
        max_storage_mb: float | None = None,
    ) -> int:
        """Enforces audio recording retention policy: deletes recordings older than max_days
        and prunes oldest files if total directory size exceeds max_storage_mb.
        Returns the number of pruned files."""
        max_days = max_days if max_days is not None else settings.AUDIO_RETENTION_MAX_DAYS
        max_storage_mb = max_storage_mb if max_storage_mb is not None else settings.AUDIO_RETENTION_MAX_STORAGE_MB
        deleted_count = 0
        try:
            if not os.path.exists(recordings_dir):
                return 0
            now = time.time()
            max_age_sec = max_days * 86400

            files = []
            total_bytes = 0
            for entry in os.scandir(recordings_dir):
                if entry.is_file() and entry.name.endswith(".wav"):
                    stat = entry.stat()
                    files.append((entry.path, stat.st_mtime, stat.st_size))
                    total_bytes += stat.st_size

            # 1. Prune files older than max_days
            remaining_files = []
            for path, mtime, size in files:
                if now - mtime > max_age_sec:
                    try:
                        os.remove(path)
                        deleted_count += 1
                        total_bytes -= size
                        logger.info(f"[AUDIO RETENTION] Pruned expired recording: {os.path.basename(path)}")
                    except Exception:
                        remaining_files.append((path, mtime, size))
                else:
                    remaining_files.append((path, mtime, size))

            # 2. Prune oldest files if total size exceeds max_storage_mb
            max_bytes = max_storage_mb * 1024 * 1024
            if total_bytes > max_bytes:
                remaining_files.sort(key=lambda x: x[1])
                for path, _, size in remaining_files:
                    if total_bytes <= max_bytes:
                        break
                    try:
                        os.remove(path)
                        deleted_count += 1
                        total_bytes -= size
                        logger.info(f"[AUDIO RETENTION] Quota exceeded. Pruned oldest: {os.path.basename(path)}")
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"[AUDIO RETENTION] Error enforcing retention: {e}")

        return deleted_count

