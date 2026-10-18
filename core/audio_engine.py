"""
Sample-accurate Dual-Track Audio Engine (Backing + Click).

Guarantees zero drift between Backing and Click tracks by:
1. Decoding both audio files into float32 stereo numpy buffers in RAM.
2. Preserving the native sample rate (e.g. 48000 Hz or 44100 Hz) when both match,
   and automatically resampling the click track only if its sample rate differs from the backing track.
3. Aligning both buffers to the exact same frame count and reading them via a single
   shared frame pointer inside a single PortAudio hardware callback.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import miniaudio
import numpy as np
import sounddevice as sd
import soundfile as sf


@dataclass
class AudioDeviceInfo:
    index: Optional[int]
    name: str
    max_output_channels: int
    default_samplerate: float


@dataclass
class LoadedTrackStats:
    sample_rate: int
    total_frames: int
    duration_seconds: float
    backing_sr_original: Optional[int]
    click_sr_original: Optional[int]
    has_backing: bool
    has_click: bool


def decode_audio_file(
    file_path: str | Path,
    target_sample_rate: Optional[int] = None,
) -> Tuple[np.ndarray, int, int]:
    """
    Decode an audio file (.wav, .mp3, .flac, .ogg, .aiff, .m4a) into a 2D stereo
    float32 numpy array of shape (N, 2).

    Returns:
        (stereo_float32_array, output_sample_rate, original_file_sample_rate)
    """
    path_str = str(file_path)

    # First inspect original file metadata and try decoding with soundfile (libsndfile)
    original_sr: Optional[int] = None
    data: Optional[np.ndarray] = None

    try:
        info = sf.info(path_str)
        original_sr = int(info.samplerate)
        # If no resampling is needed (target_sample_rate is None or matches original_sr),
        # soundfile.read is fast and bit-accurate for WAV/FLAC/OGG/MP3
        if target_sample_rate is None or target_sample_rate == original_sr:
            raw, sr = sf.read(path_str, dtype="float32", always_2d=True)
            data = raw
            output_sr = int(sr)
    except Exception:
        data = None

    # Fallback or sample-rate conversion via miniaudio (handles MP3/WAV/FLAC + C-level resampling)
    if data is None:
        try:
            if original_sr is None:
                f_info = miniaudio.get_file_info(path_str)
                original_sr = int(f_info.sample_rate)
        except Exception:
            original_sr = target_sample_rate or 44100

        out_sr = int(target_sample_rate or original_sr or 44100)
        decoded = miniaudio.decode_file(
            path_str,
            output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=2,
            sample_rate=out_sr,
        )
        arr = np.frombuffer(decoded.samples, dtype=np.float32)
        arr = arr.reshape(-1, 2).copy()
        return arr, out_sr, int(original_sr)

    # Ensure 2 channels (stereo)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]

    return np.ascontiguousarray(data, dtype=np.float32), output_sr, int(original_sr)


class DualTrackAudioEngine:
    """
    Real-time sample-accurate mixer and player for Backing + Click tracks.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

        # Audio buffers (shape: (total_frames, 2), dtype: float32)
        self._backing_buf: Optional[np.ndarray] = None
        self._click_buf: Optional[np.ndarray] = None
        self._total_frames: int = 0
        self._sample_rate: int = 44100
        self._current_frame: int = 0

        # Mixing parameters
        self._master_volume: float = 1.0     # 100% default
        self._backing_volume: float = 1.0    # 100% default
        self._click_volume: float = 0.60     # 60% mandatory default

        self._master_muted: bool = False
        self._backing_muted: bool = False
        self._click_muted: bool = False

        self._backing_solo: bool = False
        self._click_solo: bool = False

        # Playback state
        self._is_playing: bool = False
        self._stream: Optional[sd.OutputStream] = None
        self._output_device: Optional[int] = None

        # Real-time peak meters (0.0 - 1.0)
        self.backing_peak: float = 0.0
        self.click_peak: float = 0.0
        self.master_peak: float = 0.0

        # Stats of currently loaded song
        self.stats: Optional[LoadedTrackStats] = None

        # Callback fired when track reaches the end naturally
        self.on_track_finished: Optional[Callable[[], None]] = None

    # ------------------------------------------------------------------
    # Audio Device Management
    # ------------------------------------------------------------------
    @staticmethod
    def list_output_devices() -> List[AudioDeviceInfo]:
        devices: List[AudioDeviceInfo] = []
        try:
            raw_list = sd.query_devices()
            for idx, dev in enumerate(raw_list):
                max_out = int(dev.get("max_output_channels", 0))
                if max_out >= 2:
                    devices.append(
                        AudioDeviceInfo(
                            index=idx,
                            name=str(dev.get("name", f"Device {idx}")),
                            max_output_channels=max_out,
                            default_samplerate=float(dev.get("default_samplerate", 44100.0)),
                        )
                    )
        except Exception:
            pass
        return devices

    def set_output_device(self, device_index: Optional[int]) -> None:
        was_playing = self.is_playing
        self._close_stream()
        self._output_device = device_index
        if self._total_frames > 0:
            self._open_stream()
            if was_playing:
                self.play()

    # ------------------------------------------------------------------
    # Track Loading & Sample-Accurate Alignment
    # ------------------------------------------------------------------
    def load_tracks(
        self,
        backing_path: Optional[str | Path],
        click_path: Optional[str | Path],
    ) -> LoadedTrackStats:
        """
        Decode Backing and Click tracks into memory, unify their sample rate (preserving
        48kHz / 44.1kHz natively), and pad the shorter buffer so both have identical length.
        """
        self.stop()
        self._close_stream()

        backing_arr: Optional[np.ndarray] = None
        click_arr: Optional[np.ndarray] = None
        backing_orig_sr: Optional[int] = None
        click_orig_sr: Optional[int] = None
        target_sr: Optional[int] = None

        if backing_path and Path(backing_path).is_file():
            backing_arr, target_sr, backing_orig_sr = decode_audio_file(backing_path, target_sample_rate=None)

        if click_path and Path(click_path).is_file():
            # If backing exists, decode click at the exact sample rate of the backing track.
            # If both are 48kHz, no resampling occurs. If click differs, it is matched to backing.
            click_arr, click_sr_out, click_orig_sr = decode_audio_file(
                click_path, target_sample_rate=target_sr
            )
            if target_sr is None:
                target_sr = click_sr_out

        if backing_arr is None and click_arr is None:
            raise ValueError("No se encontró un archivo válido de Backing ni de Click para cargar.")

        final_sr = int(target_sr or 44100)
        len_b = len(backing_arr) if backing_arr is not None else 0
        len_c = len(click_arr) if click_arr is not None else 0
        total_frames = max(len_b, len_c)

        # Pad shorter array or missing track with zeros so both buffers have shape (total_frames, 2)
        if backing_arr is None:
            backing_arr = np.zeros((total_frames, 2), dtype=np.float32)
        elif len(backing_arr) < total_frames:
            pad = np.zeros((total_frames - len(backing_arr), 2), dtype=np.float32)
            backing_arr = np.vstack((backing_arr, pad))

        if click_arr is None:
            click_arr = np.zeros((total_frames, 2), dtype=np.float32)
        elif len(click_arr) < total_frames:
            pad = np.zeros((total_frames - len(click_arr), 2), dtype=np.float32)
            click_arr = np.vstack((click_arr, pad))

        with self._lock:
            self._backing_buf = np.ascontiguousarray(backing_arr, dtype=np.float32)
            self._click_buf = np.ascontiguousarray(click_arr, dtype=np.float32)
            self._total_frames = total_frames
            self._sample_rate = final_sr
            self._current_frame = 0
            self.backing_peak = 0.0
            self.click_peak = 0.0
            self.master_peak = 0.0

            self.stats = LoadedTrackStats(
                sample_rate=final_sr,
                total_frames=total_frames,
                duration_seconds=total_frames / float(final_sr) if final_sr > 0 else 0.0,
                backing_sr_original=backing_orig_sr,
                click_sr_original=click_orig_sr,
                has_backing=len_b > 0,
                has_click=len_c > 0,
            )

        self._open_stream()
        return self.stats

    # ------------------------------------------------------------------
    # PortAudio Stream & Real-Time Callback
    # ------------------------------------------------------------------
    def _open_stream(self) -> None:
        if self._stream is not None:
            return
        try:
            self._stream = sd.OutputStream(
                samplerate=self._sample_rate,
                channels=2,
                dtype="float32",
                device=self._output_device,
                blocksize=1024,
                callback=self._audio_callback,
                finished_callback=self._on_stream_finished,
            )
        except Exception:
            # Fallback to default device if selected device fails
            self._output_device = None
            self._stream = sd.OutputStream(
                samplerate=self._sample_rate,
                channels=2,
                dtype="float32",
                blocksize=1024,
                callback=self._audio_callback,
                finished_callback=self._on_stream_finished,
            )

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _effective_gains(self) -> Tuple[float, float]:
        """Compute effective linear multipliers for (backing_gain, click_gain)."""
        if self._master_muted:
            return 0.0, 0.0

        any_solo = self._backing_solo or self._click_solo
        if any_solo:
            b_active = self._backing_solo and not self._backing_muted
            c_active = self._click_solo and not self._click_muted
        else:
            b_active = not self._backing_muted
            c_active = not self._click_muted

        b_gain = (self._backing_volume * self._master_volume) if b_active else 0.0
        c_gain = (self._click_volume * self._master_volume) if c_active else 0.0
        return b_gain, c_gain

    def _audio_callback(
        self,
        outdata: np.ndarray,
        frames: int,
        _time_info: object,
        _status: sd.CallbackFlags,
    ) -> None:
        with self._lock:
            if (
                not self._is_playing
                or self._backing_buf is None
                or self._click_buf is None
                or self._total_frames == 0
            ):
                outdata.fill(0.0)
                self.backing_peak = 0.0
                self.click_peak = 0.0
                self.master_peak = 0.0
                return

            pos = self._current_frame
            remaining = self._total_frames - pos
            if remaining <= 0:
                outdata.fill(0.0)
                self._is_playing = False
                self.backing_peak = 0.0
                self.click_peak = 0.0
                self.master_peak = 0.0
                raise sd.CallbackStop()

            valid = min(frames, remaining)
            end = pos + valid

            b_chunk = self._backing_buf[pos:end]
            c_chunk = self._click_buf[pos:end]
            b_gain, c_gain = self._effective_gains()

            # Sample-accurate mix into outdata
            mixed = b_chunk * b_gain + c_chunk * c_gain
            np.clip(mixed, -1.0, 1.0, out=outdata[:valid])

            if valid < frames:
                outdata[valid:].fill(0.0)

            # Update peak meters for UI feedback
            self.backing_peak = float(np.max(np.abs(b_chunk)) * b_gain) if valid > 0 else 0.0
            self.click_peak = float(np.max(np.abs(c_chunk)) * c_gain) if valid > 0 else 0.0
            self.master_peak = float(np.max(np.abs(outdata[:valid]))) if valid > 0 else 0.0

            self._current_frame = end
            if self._current_frame >= self._total_frames:
                self._is_playing = False
                raise sd.CallbackStop()

    def _on_stream_finished(self) -> None:
        with self._lock:
            reached_end = self._total_frames > 0 and self._current_frame >= self._total_frames
        if reached_end and self.on_track_finished is not None:
            self.on_track_finished()

    # ------------------------------------------------------------------
    # Transport Controls (Play, Pause, Stop, Seek)
    # ------------------------------------------------------------------
    def play(self) -> None:
        with self._lock:
            if self._total_frames == 0:
                return
            if self._current_frame >= self._total_frames:
                self._current_frame = 0
            self._is_playing = True

        if self._stream is None:
            self._open_stream()
        if self._stream is not None and not self._stream.active:
            try:
                self._stream.stop()
            except Exception:
                pass
            self._stream.start()

    def pause(self) -> None:
        with self._lock:
            self._is_playing = False
            self.backing_peak = 0.0
            self.click_peak = 0.0
            self.master_peak = 0.0

    def toggle_play_pause(self) -> bool:
        if self.is_playing:
            self.pause()
            return False
        self.play()
        return True

    def stop(self) -> None:
        with self._lock:
            self._is_playing = False
            self._current_frame = 0
            self.backing_peak = 0.0
            self.click_peak = 0.0
            self.master_peak = 0.0
        if self._stream is not None and self._stream.active:
            try:
                self._stream.stop()
            except Exception:
                pass

    def seek_seconds(self, seconds: float) -> None:
        """Jump both tracks simultaneously to the exact same target frame."""
        with self._lock:
            if self._total_frames == 0 or self._sample_rate <= 0:
                return
            target_frame = int(round(seconds * self._sample_rate))
            self._current_frame = max(0, min(self._total_frames - 1, target_frame))

    def seek_ratio(self, ratio: float) -> None:
        """Jump both tracks simultaneously using a normalized position [0.0, 1.0]."""
        with self._lock:
            if self._total_frames == 0:
                return
            clamped = max(0.0, min(1.0, float(ratio)))
            self._current_frame = int(round(clamped * (self._total_frames - 1)))

    # ------------------------------------------------------------------
    # Volume, Mute & Solo Controls
    # ------------------------------------------------------------------
    @property
    def master_volume(self) -> float:
        return self._master_volume

    @master_volume.setter
    def master_volume(self, value: float) -> None:
        with self._lock:
            self._master_volume = max(0.0, min(1.0, float(value)))

    @property
    def backing_volume(self) -> float:
        return self._backing_volume

    @backing_volume.setter
    def backing_volume(self, value: float) -> None:
        with self._lock:
            self._backing_volume = max(0.0, min(1.0, float(value)))

    @property
    def click_volume(self) -> float:
        return self._click_volume

    @click_volume.setter
    def click_volume(self, value: float) -> None:
        with self._lock:
            self._click_volume = max(0.0, min(1.0, float(value)))

    @property
    def master_muted(self) -> bool:
        return self._master_muted

    @master_muted.setter
    def master_muted(self, value: bool) -> None:
        with self._lock:
            self._master_muted = bool(value)

    @property
    def backing_muted(self) -> bool:
        return self._backing_muted

    @backing_muted.setter
    def backing_muted(self, value: bool) -> None:
        with self._lock:
            self._backing_muted = bool(value)

    @property
    def click_muted(self) -> bool:
        return self._click_muted

    @click_muted.setter
    def click_muted(self, value: bool) -> None:
        with self._lock:
            self._click_muted = bool(value)

    @property
    def backing_solo(self) -> bool:
        return self._backing_solo

    @backing_solo.setter
    def backing_solo(self, value: bool) -> None:
        with self._lock:
            self._backing_solo = bool(value)

    @property
    def click_solo(self) -> bool:
        return self._click_solo

    @click_solo.setter
    def click_solo(self, value: bool) -> None:
        with self._lock:
            self._click_solo = bool(value)

    # ------------------------------------------------------------------
    # Status Properties
    # ------------------------------------------------------------------
    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._is_playing

    @property
    def current_seconds(self) -> float:
        with self._lock:
            if self._sample_rate <= 0:
                return 0.0
            return self._current_frame / float(self._sample_rate)

    @property
    def duration_seconds(self) -> float:
        with self._lock:
            if self._sample_rate <= 0:
                return 0.0
            return self._total_frames / float(self._sample_rate)

    @property
    def current_frame(self) -> int:
        with self._lock:
            return self._current_frame

    @property
    def total_frames(self) -> int:
        with self._lock:
            return self._total_frames

    @property
    def sample_rate(self) -> int:
        with self._lock:
            return self._sample_rate

    def shutdown(self) -> None:
        self.stop()
        self._close_stream()
