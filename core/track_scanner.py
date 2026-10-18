"""
Intelligent scanner and auto-pairing engine for Backing + Click tracks.

Naming pattern rules:
- Backing track typically ends with ' d.wav' (or .mp3, .flac, .ogg, .aiff, .m4a)
- Click track has the same base name ending with ' click.mp3' (or .wav, .flac, .ogg, .aiff, .m4a)
- Also supports loading a single file (either the backing or the click) and automatically
  locating its counterpart in the same directory.
- Supports recursive folder scanning (e.g. dragging an entire artist/band folder with multiple albums).
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".aif", ".m4a"}

# Regex patterns to identify backing and click suffixes (case-insensitive)
# Matches both "Song Name clic" and "Song Name click" -> base="Song Name", role="click"
# Matches "Song Name d" -> base="Song Name", role="backing"
_CLICK_SUFFIX_RE = re.compile(r"^(?P<base>.+?)[\s_-]+clic(?:k)?$", re.IGNORECASE)
_BACKING_SUFFIX_RE = re.compile(r"^(?P<base>.+?)[\s_-]+d$", re.IGNORECASE)


def _norm_key(text: str) -> str:
    """Normalize Unicode (NFC for macOS APFS/Google Drive) and collapse whitespace for matching."""
    nfc = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", nfc).strip().lower()


def _natural_sort_key(text: str) -> List[object]:
    """Return a key for natural sorting (so '2' comes before '10')."""
    nfc = unicodedata.normalize("NFC", text)
    return [int(tok) if tok.isdigit() else tok.lower() for tok in re.split(r"(\d+)", nfc)]


@dataclass
class TrackItem:
    """Represents a single logical song entry in the playlist (Backing + optional Click)."""

    title: str
    backing_path: Optional[str]
    click_path: Optional[str] = None
    folder_name: str = ""
    click_volume: Optional[float] = None  # Per-song saved click volume (0.0 - 1.0), None = use current/default
    duration_seconds: float = 0.0
    sample_rate: int = 0
    id_key: str = field(init=False)

    def __post_init__(self) -> None:
        primary = self.backing_path or self.click_path or self.title
        self.id_key = str(Path(primary).resolve()) if (self.backing_path or self.click_path) else self.title
        if not self.folder_name and primary and os.path.sep in primary:
            self.folder_name = Path(primary).parent.name

    @property
    def has_click(self) -> bool:
        return bool(self.click_path and os.path.isfile(self.click_path))

    @property
    def has_backing(self) -> bool:
        return bool(self.backing_path and os.path.isfile(self.backing_path))

    @property
    def display_name(self) -> str:
        return self.title

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "backing_path": self.backing_path,
            "click_path": self.click_path,
            "folder_name": self.folder_name,
            "click_volume": self.click_volume,
            "duration_seconds": self.duration_seconds,
            "sample_rate": self.sample_rate,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TrackItem":
        return cls(
            title=data.get("title", "Unknown"),
            backing_path=data.get("backing_path"),
            click_path=data.get("click_path"),
            folder_name=data.get("folder_name", ""),
            click_volume=data.get("click_volume"),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            sample_rate=int(data.get("sample_rate", 0)),
        )


def classify_stem(stem: str) -> Tuple[str, str]:
    """
    Given a filename stem (without extension), classify it into:
    (clean_base_name, role)
    where role is one of: 'backing_d', 'click', or 'generic'.
    """
    clean_stem = unicodedata.normalize("NFC", stem).strip()
    m_click = _CLICK_SUFFIX_RE.match(clean_stem)
    if m_click:
        return m_click.group("base").strip(), "click"

    m_backing = _BACKING_SUFFIX_RE.match(clean_stem)
    if m_backing:
        return m_backing.group("base").strip(), "backing_d"

    return clean_stem, "generic"


def pair_Single_file(file_path: str | Path) -> Optional[TrackItem]:
    """
    Given a single audio file selected or dropped by the user, automatically find
    its companion click or backing file in the same directory and return a TrackItem.
    """
    path = Path(file_path)
    if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return None

    parent = path.parent
    base_name, role = classify_stem(path.stem)
    base_key = _norm_key(base_name)

    backing_candidate: Optional[Path] = None
    click_candidate: Optional[Path] = None

    if role == "backing_d":
        backing_candidate = path
    elif role == "click":
        click_candidate = path
    else:
        backing_candidate = path

    # 1. Scan sibling files in the same directory to find the matching pair
    try:
        siblings = sorted(parent.iterdir(), key=lambda p: _natural_sort_key(p.name))
    except OSError:
        siblings = []

    for sib in siblings:
        if sib == path or not sib.is_file() or sib.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        sib_base, sib_role = classify_stem(sib.stem)
        if _norm_key(sib_base) != base_key:
            continue

        if sib_role == "click" and click_candidate is None:
            click_candidate = sib
        elif sib_role == "backing_d" and backing_candidate is None:
            backing_candidate = sib
        elif sib_role == "generic" and backing_candidate is None and role == "click":
            backing_candidate = sib

    # 2. Direct probe fallback (in case cloud directory listing was blocked or partial)
    if click_candidate is None and role != "click":
        for suffix_word in ("Clic", "clic", "Click", "click", "CLIC", "CLICK"):
            for ext in (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".MP3", ".WAV"):
                probe = parent / f"{base_name} {suffix_word}{ext}"
                if probe.is_file():
                    click_candidate = probe
                    break
            if click_candidate is not None:
                break

    if backing_candidate is None and role == "click":
        for suffix_word in ("D", "d"):
            for ext in (".wav", ".mp3", ".flac", ".WAV", ".MP3"):
                probe = parent / f"{base_name} {suffix_word}{ext}"
                if probe.is_file():
                    backing_candidate = probe
                    break
            if backing_candidate is not None:
                break

    return TrackItem(
        title=base_name,
        backing_path=str(backing_candidate.resolve()) if backing_candidate else None,
        click_path=str(click_candidate.resolve()) if click_candidate else None,
        folder_name=parent.name,
    )


def scan_directory_single_level(directory: str | Path) -> List[TrackItem]:
    """
    Scan a single directory (non-recursive) and pair all audio files into TrackItems.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return []

    try:
        files = [
            f
            for f in dir_path.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS and not f.name.startswith(".")
        ]
    except OSError:
        return []

    files.sort(key=lambda f: _natural_sort_key(f.name))

    # Group files by lowercase clean base name
    groups: Dict[str, Dict[str, object]] = {}
    order: List[str] = []

    for f in files:
        base_name, role = classify_stem(f.stem)
        key = _norm_key(base_name)
        if key not in groups:
            groups[key] = {
                "title": base_name,
                "backing_d": None,
                "click": None,
                "generic": None,
            }
            order.append(key)

        bucket = groups[key]
        if role == "backing_d" and bucket["backing_d"] is None:
            bucket["backing_d"] = f
            # Prefer the casing from the backing track
            bucket["title"] = base_name
        elif role == "click" and bucket["click"] is None:
            bucket["click"] = f
        elif role == "generic" and bucket["generic"] is None:
            bucket["generic"] = f

    items: List[TrackItem] = []
    for key in order:
        bucket = groups[key]
        backing_file: Optional[Path] = bucket["backing_d"] or bucket["generic"]  # type: ignore[assignment]
        click_file: Optional[Path] = bucket["click"]  # type: ignore[assignment]
        title = str(bucket["title"])

        items.append(
            TrackItem(
                title=title,
                backing_path=str(backing_file.resolve()) if backing_file else None,
                click_path=str(click_file.resolve()) if click_file else None,
                folder_name=dir_path.name,
            )
        )

    return items


def scan_paths(paths: Iterable[str | Path], recursive: bool = True) -> List[TrackItem]:
    """
    Accepts any combination of files and directories (e.g. from Drag & Drop or File Dialog).
    - Directories are scanned (recursively by default, sorted naturally).
    - Individual files are auto-paired with their sibling click/backing track, avoiding duplicates
      if the user selects both 'Song d.wav' and 'Song click.mp3' at the same time.
    """
    collected: List[TrackItem] = []
    seen_pairs: set[Tuple[Optional[str], Optional[str]]] = set()

    def _add_item(item: Optional[TrackItem]) -> None:
        if item is None:
            return
        sig = (item.backing_path, item.click_path)
        if sig not in seen_pairs:
            seen_pairs.add(sig)
            collected.append(item)

    for raw_p in paths:
        p = Path(raw_p)
        if not p.exists():
            continue
        if p.is_file():
            _add_item(pair_Single_file(p))
        elif p.is_dir():
            if recursive:
                # Collect all directories in natural sorted order
                all_dirs: List[Path] = []
                for root, dirs, _files in os.walk(p):
                    # Filter hidden directories
                    dirs[:] = sorted(
                        [d for d in dirs if not d.startswith(".")],
                        key=_natural_sort_key,
                    )
                    all_dirs.append(Path(root))
                for d in all_dirs:
                    for item in scan_directory_single_level(d):
                        _add_item(item)
            else:
                for item in scan_directory_single_level(p):
                    _add_item(item)

    return collected
