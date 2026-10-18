"""
Automated verification tests for DualTrack Sync Player:
1. Auto-pairing of '<Song> d.wav' + '<Song> click.mp3' (single file & recursive folders)
2. 48kHz native support (and 48kHz + 44.1kHz cross-rate alignment)
3. Sample-accurate single-pointer audio mixing (Master 100%, Backing 100%, Click 60% default)
4. Playlist management and per-song click volume persistence
"""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from core.audio_engine import DualTrackAudioEngine
from core.playlist_manager import DEFAULT_CLICK_VOLUME, PlaylistManager
from core.track_scanner import pair_Single_file, scan_paths


def _write_minimal_mp3_or_wav(path: Path, data: np.ndarray, samplerate: int) -> None:
    """Write test audio file using soundfile (supports WAV, FLAC, OGG, and MP3 on modern libsndfile)."""
    sf.write(str(path), data, samplerate)


class TestDualTrackPlayer(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_auto_pairing_single_file_and_recursive_folders(self) -> None:
        """Verify that '<Tema> d.wav' and '<Tema> click.mp3' pair into a single clean item."""
        album_dir = self.root / "Attaque 77" / "1989 - Dulce Navidad dls"
        album_dir.mkdir(parents=True)

        sr = 48000
        samples = np.zeros((sr, 2), dtype=np.float32)

        b1 = album_dir / "01 - Hay una Bomba en el Colegio D.wav"
        c1 = album_dir / "01 - Hay una Bomba en el Colegio Clic.mp3"
        b2 = album_dir / "02 - Gil d.wav"
        c2 = album_dir / "02 - Gil click.mp3"
        b3 = album_dir / "03 - Solo Backing D.wav"

        _write_minimal_mp3_or_wav(b1, samples, sr)
        _write_minimal_mp3_or_wav(c1, samples, sr)
        _write_minimal_mp3_or_wav(b2, samples, sr)
        _write_minimal_mp3_or_wav(c2, samples, sr)
        _write_minimal_mp3_or_wav(b3, samples, sr)

        # 1. Opening a single backing file should auto-locate the Clic.mp3 / click.mp3
        single_item = pair_Single_file(b1)
        self.assertIsNotNone(single_item)
        assert single_item is not None
        self.assertEqual(single_item.display_name, "01 - Hay una Bomba en el Colegio")
        self.assertTrue(single_item.has_backing)
        self.assertTrue(single_item.has_click)
        self.assertEqual(Path(single_item.click_path).name, "01 - Hay una Bomba en el Colegio Clic.mp3")

        # 2. Opening the click file directly should also auto-locate the backing D.wav
        from_click = pair_Single_file(c1)
        self.assertIsNotNone(from_click)
        assert from_click is not None
        self.assertEqual(from_click.display_name, "01 - Hay una Bomba en el Colegio")
        self.assertEqual(Path(from_click.backing_path).name, "01 - Hay una Bomba en el Colegio D.wav")

        # 3. Scanning the top-level band folder recursively should find 3 songs (not 5!)
        items = scan_paths([self.root / "Attaque 77"], recursive=True)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].display_name, "01 - Hay una Bomba en el Colegio")
        self.assertTrue(items[0].has_click)
        self.assertEqual(items[1].display_name, "02 - Gil")
        self.assertTrue(items[1].has_click)
        self.assertEqual(items[2].display_name, "03 - Solo Backing")
        self.assertFalse(items[2].has_click)

    @patch("core.audio_engine.DualTrackAudioEngine._open_stream")
    def test_48khz_native_and_sample_accurate_mixing(self, _mock_stream) -> None:
        """
        Verify 48kHz native loading, 60% default click volume, Master volume scaling,
        and sample-accurate frame alignment during playback and seeking.
        """
        sr = 48000
        # 2 seconds at 48kHz = 96,000 frames of a 1000 Hz sine wave
        n_frames = sr * 2
        t = np.arange(n_frames, dtype=np.float32) / sr
        sine_wave = (0.5 * np.sin(2.0 * np.pi * 1000.0 * t)).astype(np.float32)
        stereo_wave = np.column_stack([sine_wave, sine_wave])

        b_path = self.root / "Tema Test d.wav"
        c_path = self.root / "Tema Test click.mp3"
        _write_minimal_mp3_or_wav(b_path, stereo_wave, sr)
        _write_minimal_mp3_or_wav(c_path, stereo_wave, sr)

        engine = DualTrackAudioEngine()
        # Verify mandatory defaults: Master=100%, Backing=100%, Click=60%
        self.assertAlmostEqual(engine.master_volume, 1.0)
        self.assertAlmostEqual(engine.backing_volume, 1.0)
        self.assertAlmostEqual(engine.click_volume, 0.60)

        stats = engine.load_tracks(b_path, c_path)
        self.assertEqual(stats.sample_rate, 48000)
        self.assertEqual(stats.backing_sr_original, 48000)
        self.assertEqual(stats.click_sr_original, 48000)
        self.assertEqual(stats.total_frames, n_frames)
        self.assertTrue(stats.has_backing)
        self.assertTrue(stats.has_click)

        # Simulate hardware audio callback and verify sample-accurate sum
        engine._is_playing = True
        out = np.zeros((1024, 2), dtype=np.float32)
        engine._audio_callback(out, 1024, None, 0)

        # Expected mix: (stereo_wave * 1.0 + stereo_wave * 0.60) * 1.0 = stereo_wave * 1.60
        expected_first = stereo_wave[:1024] * 1.60
        self.assertTrue(np.allclose(out, expected_first, atol=0.015))
        self.assertEqual(engine.current_frame, 1024)

        # Now change Master volume to 50% -> affects both tracks: 1.60 * 0.5 = 0.80
        engine.master_volume = 0.50
        engine._audio_callback(out, 1024, None, 0)
        expected_second = stereo_wave[1024:2048] * 0.80
        self.assertTrue(np.allclose(out, expected_second, atol=0.015))
        self.assertEqual(engine.current_frame, 2048)

        # Test Seek: both backing and click jump via the single frame pointer
        engine.seek_seconds(1.0)
        self.assertEqual(engine.current_frame, 48000)

    @patch("core.audio_engine.DualTrackAudioEngine._open_stream")
    def test_cross_sample_rate_48khz_backing_with_44100hz_click(self, _mock_stream) -> None:
        """Verify that if Backing is 48kHz and Click is 44.1kHz, Click is matched to 48kHz."""
        sr_b = 48000
        sr_c = 44100
        b_path = self.root / "CrossRate d.wav"
        c_path = self.root / "CrossRate click.mp3"

        t_b = np.arange(sr_b, dtype=np.float32) / sr_b
        t_c = np.arange(sr_c, dtype=np.float32) / sr_c
        wave_b = np.column_stack([0.4 * np.sin(2 * np.pi * 440 * t_b)] * 2).astype(np.float32)
        wave_c = np.column_stack([0.4 * np.sin(2 * np.pi * 880 * t_c)] * 2).astype(np.float32)

        _write_minimal_mp3_or_wav(b_path, wave_b, sr_b)
        _write_minimal_mp3_or_wav(c_path, wave_c, sr_c)

        engine = DualTrackAudioEngine()
        stats = engine.load_tracks(b_path, c_path)
        self.assertEqual(stats.sample_rate, 48000)
        self.assertEqual(stats.backing_sr_original, 48000)
        self.assertEqual(stats.click_sr_original, 44100)
        self.assertEqual(engine._backing_buf.shape, engine._click_buf.shape)

    def test_playlist_and_volume_memory(self) -> None:
        mem_file = self.root / "vol_mem.json"
        pm = PlaylistManager(memory_path=mem_file)

        b_path = self.root / "Cancion A d.wav"
        c_path = self.root / "Cancion A click.mp3"
        _write_minimal_mp3_or_wav(b_path, np.zeros((4800, 2), dtype=np.float32), 48000)
        _write_minimal_mp3_or_wav(c_path, np.zeros((4800, 2), dtype=np.float32), 48000)

        added = pm.add_paths([self.root])
        self.assertEqual(len(added), 1)
        track = added[0]
        self.assertAlmostEqual(pm.get_track_click_volume(track), DEFAULT_CLICK_VOLUME)

        # Customize click volume for this song to 75% and verify persistence
        pm.set_track_click_volume(track, 0.75)
        pm2 = PlaylistManager(memory_path=mem_file)
        added2 = pm2.add_paths([self.root])
        self.assertAlmostEqual(pm2.get_track_click_volume(added2[0]), 0.75)


if __name__ == "__main__":
    unittest.main()
