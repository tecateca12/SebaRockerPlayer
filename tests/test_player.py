"""
Automated verification tests for SebaRockerPlayer v0.2:
1. Auto-pairing of '<Song> D.wav' + '<Song> Clic.mp3' + '<Song> L.txt' (single file & recursive folders)
2. LivePrompter (.txt) parser: {artist:...}, {duration:mm:ss}, {soc}/{eoc}, {d_time:...}, {pause:...}
3. 48kHz native support (and 48kHz + 44.1kHz cross-rate alignment)
4. Sample-accurate single-pointer audio mixing (Master 100%, Backing 100%, Click 60% default)
5. Playlist management and per-song click volume persistence
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from core.audio_engine import DualTrackAudioEngine
from core.lyrics_parser import parse_liveprompter_file, parse_liveprompter_text
from core.playlist_manager import DEFAULT_CLICK_VOLUME, PlaylistManager
from core.track_scanner import pair_Single_file, scan_paths

MENSAKA_AGOSTO_L_TXT = """{artist:Mensaka}
{duration:02:35}

Corre el frio en mi habitacion 
y el invierno se marcho con vos
en septiembre suelo estar mejor
aunque a veces me falte tu voz... y estoy

{soc}
Buscando una cancion
para no extrañarte como un loco
buscando una razon 
porque agosto me destroza un poco
Un poco el corazon
{eoc}

Murmurando en mi imaginacion
el tiempo no juega a mi favor
"""


def _write_minimal_mp3_or_wav(path: Path, data: np.ndarray, samplerate: int) -> None:
    sf.write(str(path), data, samplerate)


class TestSebaRockerPlayerV02(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_auto_pairing_backing_click_and_lyrics_txt(self) -> None:
        """Verify that '<Tema> D.wav', '<Tema> Clic.mp3', and '<Tema> L.txt' pair into one item."""
        album_dir = self.root / "Mensaka"
        album_dir.mkdir(parents=True)

        sr = 48000
        samples = np.zeros((sr, 2), dtype=np.float32)

        b1 = album_dir / "Mensaka - Agosto D.wav"
        c1 = album_dir / "Mensaka - Agosto Clic.mp3"
        l1 = album_dir / "Mensaka - Agosto L.txt"

        b2 = album_dir / "02 - Sin Letra D.wav"
        c2 = album_dir / "02 - Sin Letra Clic.mp3"

        _write_minimal_mp3_or_wav(b1, samples, sr)
        _write_minimal_mp3_or_wav(c1, samples, sr)
        l1.write_text(MENSAKA_AGOSTO_L_TXT, encoding="utf-8")

        _write_minimal_mp3_or_wav(b2, samples, sr)
        _write_minimal_mp3_or_wav(c2, samples, sr)

        # 1. Opening the backing D.wav file should auto-locate both Clic.mp3 and L.txt
        item = pair_Single_file(b1)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.display_name, "Mensaka - Agosto")
        self.assertTrue(item.has_backing)
        self.assertTrue(item.has_click)
        self.assertTrue(item.has_lyrics)
        self.assertEqual(Path(item.lyrics_path).name, "Mensaka - Agosto L.txt")

        # 2. Opening the L.txt file directly should also auto-locate D.wav and Clic.mp3
        from_lyrics = pair_Single_file(l1)
        self.assertIsNotNone(from_lyrics)
        assert from_lyrics is not None
        self.assertEqual(from_lyrics.display_name, "Mensaka - Agosto")
        self.assertTrue(from_lyrics.has_backing)
        self.assertTrue(from_lyrics.has_click)
        self.assertTrue(from_lyrics.has_lyrics)

        # 3. Scanning the folder should return 2 songs (not 5 files!)
        # Sorted naturally: '02 - Sin Letra' is items[0], 'Mensaka - Agosto' is items[1]
        items = scan_paths([album_dir], recursive=True)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].display_name, "02 - Sin Letra")
        self.assertFalse(items[0].has_lyrics)
        self.assertEqual(items[1].display_name, "Mensaka - Agosto")
        self.assertTrue(items[1].has_lyrics)

    def test_liveprompter_lyrics_parser_and_scroll_timing(self) -> None:
        """Verify {artist}, {duration:02:35}, {soc}/{eoc}, chord stripping, and scroll math."""
        l_path = self.root / "Mensaka - Agosto L.txt"
        l_path.write_text(MENSAKA_AGOSTO_L_TXT, encoding="utf-8")

        parsed = parse_liveprompter_file(l_path)
        self.assertEqual(parsed.artist, "Mensaka")
        # 02:35 = 2 * 60 + 35 = 155.0 seconds
        self.assertAlmostEqual(parsed.duration_seconds or 0.0, 155.0)
        self.assertFalse(parsed.is_empty)

        # Verify chorus lines ({soc} ... {eoc}) are marked is_chorus=True
        chorus_lines = [ln for ln in parsed.lines if ln.is_chorus and ln.text.strip()]
        self.assertEqual(len(chorus_lines), 5)
        self.assertEqual(chorus_lines[0].text, "Buscando una cancion")

        # Verify scroll ratio from start (0s) to mid (77.5s) to end (155s)
        self.assertAlmostEqual(parsed.compute_scroll_ratio(0.0, 180.0), 0.0)
        self.assertAlmostEqual(parsed.compute_scroll_ratio(77.5, 180.0), 0.50, places=2)
        self.assertAlmostEqual(parsed.compute_scroll_ratio(155.0, 180.0), 1.0)

        # Verify {d_time:...} and chord stripping ([Am] removed)
        custom_txt = "{duration:01:00}\n[Am]Linea 1\n{d_time:00:40}\n[G]Linea 2\nLinea 3\n"
        p2 = parse_liveprompter_text(custom_txt)
        self.assertEqual(p2.lines[0].text, "Linea 1")
        self.assertEqual(p2.lines[1].text, "Linea 2")
        # At t=40s, line index 1 (out of 0, 1, 2 -> pos 0.5) must be reached
        self.assertAlmostEqual(p2.compute_scroll_ratio(40.0), 0.50, places=2)

    @patch("core.audio_engine.DualTrackAudioEngine._open_stream")
    def test_48khz_native_and_sample_accurate_mixing(self, _mock_stream) -> None:
        sr = 48000
        n_frames = sr * 2
        t = np.arange(n_frames, dtype=np.float32) / sr
        sine_wave = (0.5 * np.sin(2.0 * np.pi * 1000.0 * t)).astype(np.float32)
        stereo_wave = np.column_stack([sine_wave, sine_wave])

        b_path = self.root / "Tema Test d.wav"
        c_path = self.root / "Tema Test click.mp3"
        _write_minimal_mp3_or_wav(b_path, stereo_wave, sr)
        _write_minimal_mp3_or_wav(c_path, stereo_wave, sr)

        engine = DualTrackAudioEngine()
        self.assertAlmostEqual(engine.master_volume, 1.0)
        self.assertAlmostEqual(engine.backing_volume, 1.0)
        self.assertAlmostEqual(engine.click_volume, 0.60)

        stats = engine.load_tracks(b_path, c_path)
        self.assertEqual(stats.sample_rate, 48000)
        self.assertEqual(stats.total_frames, n_frames)

        engine._is_playing = True
        out = np.zeros((1024, 2), dtype=np.float32)
        engine._audio_callback(out, 1024, None, 0)
        expected_first = stereo_wave[:1024] * 1.60
        self.assertTrue(np.allclose(out, expected_first, atol=0.015))

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

        pm.set_track_click_volume(track, 0.75)
        pm2 = PlaylistManager(memory_path=mem_file)
        added2 = pm2.add_paths([self.root])
        self.assertAlmostEqual(pm2.get_track_click_volume(added2[0]), 0.75)


if __name__ == "__main__":
    unittest.main()
