"""
Playlist management, playback ordering, and per-track volume persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from core.track_scanner import TrackItem, scan_paths

DEFAULT_CLICK_VOLUME = 0.60  # 60% mandatory default
VOLUME_MEMORY_FILE = Path.home() / ".seba_rocker_player_memory.json"


class PlaylistManager:
    """Manages the list of paired tracks, active selection, and per-song settings."""

    def __init__(self, memory_path: Path = VOLUME_MEMORY_FILE) -> None:
        self.items: List[TrackItem] = []
        self.current_index: int = -1
        self.continuous_playback: bool = True  # True = Winamp continuous, False = Stop after song
        self.memory_path = memory_path
        self._volume_memory: Dict[str, float] = {}
        self._load_volume_memory()

    # ------------------------------------------------------------------
    # Volume memory persistence (remembers custom click volume per song)
    # ------------------------------------------------------------------
    def _load_volume_memory(self) -> None:
        if not self.memory_path.is_file():
            return
        try:
            data = json.loads(self.memory_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._volume_memory = {
                    str(k): float(v) for k, v in data.items() if isinstance(v, (int, float))
                }
        except Exception:
            self._volume_memory = {}

    def _save_volume_memory(self) -> None:
        try:
            self.memory_path.write_text(
                json.dumps(self._volume_memory, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def get_track_click_volume(self, item: TrackItem) -> float:
        """Return the saved click volume for a track, or None if not customized."""
        if item.click_volume is not None:
            return item.click_volume
        if item.id_key in self._volume_memory:
            item.click_volume = self._volume_memory[item.id_key]
            return item.click_volume
        return DEFAULT_CLICK_VOLUME

    def has_custom_click_volume(self, item: TrackItem) -> bool:
        return item.click_volume is not None or item.id_key in self._volume_memory

    def set_track_click_volume(self, item: TrackItem, volume: float) -> None:
        """Persist custom click volume (0.0 to 1.0) for a specific song."""
        clamped = max(0.0, min(1.0, float(volume)))
        item.click_volume = clamped
        self._volume_memory[item.id_key] = clamped
        self._save_volume_memory()

    # ------------------------------------------------------------------
    # Playlist manipulation
    # ------------------------------------------------------------------
    def add_paths(self, paths: Iterable[str | Path], recursive: bool = True) -> List[TrackItem]:
        """Scan files/folders, auto-pair Backing + Click, and append to playlist."""
        new_items = scan_paths(paths, recursive=recursive)
        added: List[TrackItem] = []
        existing_keys = {it.id_key for it in self.items}

        for item in new_items:
            if item.id_key in self._volume_memory and item.click_volume is None:
                item.click_volume = self._volume_memory[item.id_key]
            if item.id_key not in existing_keys:
                self.items.append(item)
                existing_keys.add(item.id_key)
                added.append(item)

        if self.current_index == -1 and self.items:
            self.current_index = 0

        return added

    def clear(self) -> None:
        self.items.clear()
        self.current_index = -1

    def remove_at(self, index: int) -> None:
        if 0 <= index < len(self.items):
            del self.items[index]
            if not self.items:
                self.current_index = -1
            elif index < self.current_index:
                self.current_index -= 1
            elif index == self.current_index and self.current_index >= len(self.items):
                self.current_index = len(self.items) - 1

    def move_item(self, from_idx: int, to_idx: int) -> bool:
        if not (0 <= from_idx < len(self.items) and 0 <= to_idx < len(self.items)):
            return False
        if from_idx == to_idx:
            return False
        current_item = self.current_item
        item = self.items.pop(from_idx)
        self.items.insert(to_idx, item)
        if current_item is not None:
            self.current_index = self.items.index(current_item)
        return True

    @property
    def current_item(self) -> Optional[TrackItem]:
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index]
        return None

    def select_index(self, index: int) -> Optional[TrackItem]:
        if 0 <= index < len(self.items):
            self.current_index = index
            return self.items[index]
        return None

    def next_track(self) -> Optional[TrackItem]:
        if not self.items:
            return None
        if self.current_index + 1 < len(self.items):
            self.current_index += 1
            return self.items[self.current_index]
        return None

    def previous_track(self) -> Optional[TrackItem]:
        if not self.items:
            return None
        if self.current_index - 1 >= 0:
            self.current_index -= 1
            return self.items[self.current_index]
        return None

    # ------------------------------------------------------------------
    # Save / Load Playlist files (.dpls / .json)
    # ------------------------------------------------------------------
    def save_playlist(self, file_path: str | Path) -> None:
        path = Path(file_path)
        payload = {
            "version": 1,
            "continuous_playback": self.continuous_playback,
            "tracks": [item.to_dict() for item in self.items],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_playlist(self, file_path: str | Path, append: bool = False) -> List[TrackItem]:
        path = Path(file_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not append:
            self.clear()

        if isinstance(data, dict) and "continuous_playback" in data:
            self.continuous_playback = bool(data["continuous_playback"])

        raw_tracks = data.get("tracks", []) if isinstance(data, dict) else []
        loaded: List[TrackItem] = []
        existing_keys = {it.id_key for it in self.items}

        for raw in raw_tracks:
            if not isinstance(raw, dict):
                continue
            item = TrackItem.from_dict(raw)
            if item.click_volume is not None:
                self._volume_memory[item.id_key] = item.click_volume
            elif item.id_key in self._volume_memory:
                item.click_volume = self._volume_memory[item.id_key]

            if item.id_key not in existing_keys:
                self.items.append(item)
                existing_keys.add(item.id_key)
                loaded.append(item)

        if self.current_index == -1 and self.items:
            self.current_index = 0
        self._save_volume_memory()
        return loaded
