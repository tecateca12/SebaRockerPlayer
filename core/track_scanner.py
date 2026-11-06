"""
Intelligent scanner and auto-pairing engine for Backing + Click + Lyrics (.txt) tracks.

Naming pattern rules:
- Backing track typically ends with ' d.wav' / ' D.wav' (or .mp3, .flac, .ogg, .aiff, .m4a)
- Click track has the same base name ending with ' clic.mp3' / ' click.mp3' (or .wav, .flac, etc.)
- Lyrics file has the same base name ending with ' L.txt' / ' l.txt' (or '<BaseName>.txt')
- Also supports loading a single file (backing, click, or lyrics .txt) and automatically
  locating its counterparts in the same directory.
- Supports recursive folder scanning (e.g. dragging an entire artist/band folder with multiple albums).
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".aif", ".m4a"}
SUPPORTED_LYRICS_EXTENSIONS = {".txt", ".cho", ".crd"}
SUPPORTED_EXTENSIONS = SUPPORTED_AUDIO_EXTENSIONS | SUPPORTED_LYRICS_EXTENSIONS

# Regex patterns to identify backing, click, and lyrics suffixes (case-insensitive)
# Matches both "Song Name clic" and "Song Name click" -> base="Song Name", role="click"
# Matches "Song Name d" -> base="Song Name", role="backing_d"
# Matches "Song Name L" -> base="Song Name", role="lyrics_l"
_CLICK_SUFFIX_RE = re.compile(r"^(?P<base>.+?)[\s_-]+clic(?:k)?$", re.IGNORECASE)
_BACKING_SUFFIX_RE = re.compile(r"^(?P<base>.+?)[\s_-]+d$", re.IGNORECASE)
_LYRICS_SUFFIX_RE = re.compile(r"^(?P<base>.+?)[\s_-]+l$", re.IGNORECASE)


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
    """Represents a single logical song entry in the playlist (Backing + optional Click + optional Lyrics)."""

    title: str
    backing_path: Optional[str]
    click_path: Optional[str] = None
    lyrics_path: Optional[str] = None
    folder_name: str = ""
    click_volume: Optional[float] = None  # Per-song saved click volume (0.0 - 1.0), None = use current/default
    duration_seconds: float = 0.0
    sample_rate: int = 0
    id_key: str = field(init=False)

    def __post_init__(self) -> None:
        primary = self.backing_path or self.click_path or self.lyrics_path or self.title
        self.id_key = (
            str(Path(primary).resolve())
            if (self.backing_path or self.click_path or self.lyrics_path)
            else self.title
        )
        if not self.folder_name and primary and os.path.sep in primary:
            self.folder_name = Path(primary).parent.name

    @property
    def has_click(self) -> bool:
        return bool(self.click_path and os.path.isfile(self.click_path))

    @property
    def has_backing(self) -> bool:
        return bool(self.backing_path and os.path.isfile(self.backing_path))

    @property
    def has_lyrics(self) -> bool:
        return bool(self.lyrics_path and os.path.isfile(self.lyrics_path))

    @property
    def display_name(self) -> str:
        return self.title

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "backing_path": self.backing_path,
            "click_path": self.click_path,
            "lyrics_path": self.lyrics_path,
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
            lyrics_path=data.get("lyrics_path"),
            folder_name=data.get("folder_name", ""),
            click_volume=data.get("click_volume"),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            sample_rate=int(data.get("sample_rate", 0)),
        )


def classify_file(stem: str, suffix: str) -> Tuple[str, str]:
    """
    Given a filename stem (without extension) and lowercase extension, classify it into:
    (clean_base_name, role)
    where role is one of: 'backing_d', 'click', 'lyrics_l', 'lyrics_generic', or 'generic'.
    """
    clean_stem = unicodedata.normalize("NFC", stem).strip()
    ext = suffix.lower()

    if ext in SUPPORTED_LYRICS_EXTENSIONS:
        m_lyr = _LYRICS_SUFFIX_RE.match(clean_stem)
        if m_lyr:
            return m_lyr.group("base").strip(), "lyrics_l"
        return clean_stem, "lyrics_generic"

    m_click = _CLICK_SUFFIX_RE.match(clean_stem)
    if m_click:
        return m_click.group("base").strip(), "click"

    m_backing = _BACKING_SUFFIX_RE.match(clean_stem)
    if m_backing:
        return m_backing.group("base").strip(), "backing_d"

    return clean_stem, "generic"


def classify_stem(stem: str) -> Tuple[str, str]:
    """Backwards-compatible helper for audio stem classification."""
    return classify_file(stem, ".wav")


def pair_Single_file(file_path: str | Path) -> Optional[TrackItem]:
    """
    Given a single audio or lyrics file selected or dropped by the user, automatically find
    its companion click, backing, and lyrics (.txt) files in the same directory.
    """
    path = Path(file_path)
    if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return None

    parent = path.parent
    base_name, role = classify_file(path.stem, path.suffix)
    base_key = _norm_key(base_name)

    backing_candidate: Optional[Path] = None
    click_candidate: Optional[Path] = None
    lyrics_candidate: Optional[Path] = None

    if role == "backing_d":
        backing_candidate = path
    elif role == "click":
        click_candidate = path
    elif role in ("lyrics_l", "lyrics_generic"):
        lyrics_candidate = path
    else:
        backing_candidate = path

    # 1. Scan sibling files in the same directory to find the matching group
    try:
        siblings = sorted(parent.iterdir(), key=lambda p: _natural_sort_key(p.name))
    except OSError:
        siblings = []

    for sib in siblings:
        if sib == path or not sib.is_file() or sib.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        sib_base, sib_role = classify_file(sib.stem, sib.suffix)
        if _norm_key(sib_base) != base_key:
            continue

        if sib_role == "click" and click_candidate is None:
            click_candidate = sib
        elif sib_role == "backing_d" and backing_candidate is None:
            backing_candidate = sib
        elif sib_role == "lyrics_l" and lyrics_candidate is None:
            lyrics_candidate = sib
        elif sib_role == "lyrics_generic" and lyrics_candidate is None:
            lyrics_candidate = sib
        elif sib_role == "generic" and backing_candidate is None and role != "generic":
            backing_candidate = sib

    # 2. Direct probe fallback (in case cloud directory listing was blocked or partial)
    if click_candidate is None:
        for suffix_word in ("Clic", "clic", "Click", "click", "CLIC", "CLICK"):
            for ext in (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".MP3", ".WAV"):
                probe = parent / f"{base_name} {suffix_word}{ext}"
                if probe.is_file():
                    click_candidate = probe
                    break
            if click_candidate is not None:
                break

    if backing_candidate is None:
        for suffix_word in ("D", "d"):
            for ext in (".wav", ".mp3", ".flac", ".WAV", ".MP3"):
                probe = parent / f"{base_name} {suffix_word}{ext}"
                if probe.is_file():
                    backing_candidate = probe
                    break
            if backing_candidate is not None:
                break

    if lyrics_candidate is None:
        for suffix_word in (" L", " l", ""):
            for ext in (".txt", ".TXT", ".cho"):
                probe = parent / f"{base_name}{suffix_word}{ext}"
                if probe.is_file():
                    lyrics_candidate = probe
                    break
            if lyrics_candidate is not None:
                break

    # Do not create a playable item if there is neither backing nor click audio
    if backing_candidate is None and click_candidate is None:
        return None

    return TrackItem(
        title=base_name,
        backing_path=str(backing_candidate.resolve()) if backing_candidate else None,
        click_path=str(click_candidate.resolve()) if click_candidate else None,
        lyrics_path=str(lyrics_candidate.resolve()) if lyrics_candidate else None,
        folder_name=parent.name,
    )


def scan_directory_single_level(directory: str | Path) -> List[TrackItem]:
    """
    Scan a single directory (non-recursive) and pair all audio + lyrics files into TrackItems.
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

    groups: Dict[str, Dict[str, object]] = {}
    order: List[str] = []

    for f in files:
        base_name, role = classify_file(f.stem, f.suffix)
        key = _norm_key(base_name)
        if key not in groups:
            groups[key] = {
                "title": base_name,
                "backing_d": None,
                "click": None,
                "generic": None,
                "lyrics_l": None,
                "lyrics_generic": None,
            }
            order.append(key)

        bucket = groups[key]
        if role == "backing_d" and bucket["backing_d"] is None:
            bucket["backing_d"] = f
            bucket["title"] = base_name
        elif role == "click" and bucket["click"] is None:
            bucket["click"] = f
        elif role == "generic" and bucket["generic"] is None:
            bucket["generic"] = f
        elif role == "lyrics_l" and bucket["lyrics_l"] is None:
            bucket["lyrics_l"] = f
        elif role == "lyrics_generic" and bucket["lyrics_generic"] is None:
            bucket["lyrics_generic"] = f

    items: List[TrackItem] = []
    for key in order:
        bucket = groups[key]
        backing_file: Optional[Path] = bucket["backing_d"] or bucket["generic"]  # type: ignore[assignment]
        click_file: Optional[Path] = bucket["click"]  # type: ignore[assignment]
        lyrics_file: Optional[Path] = bucket["lyrics_l"] or bucket["lyrics_generic"]  # type: ignore[assignment]

        # Skip standalone .txt files in a folder if they have no matching audio track
        if backing_file is None and click_file is None:
            continue

        title = str(bucket["title"])
        items.append(
            TrackItem(
                title=title,
                backing_path=str(backing_file.resolve()) if backing_file else None,
                click_path=str(click_file.resolve()) if click_file else None,
                lyrics_path=str(lyrics_file.resolve()) if lyrics_file else None,
                folder_name=dir_path.name,
            )
        )

    return items


def scan_paths(paths: Iterable[str | Path], recursive: bool = True) -> List[TrackItem]:
    """
    Accepts any combination of files and directories (e.g. from Drag & Drop or File Dialog).
    - Directories are scanned (recursively by default, sorted naturally).
    - Individual files are auto-paired with their sibling click/backing/lyrics files, avoiding
      duplicates if the user selects multiple files of the same song at the same time.
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
                all_dirs: List[Path] = []
                for root, dirs, _files in os.walk(p):
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
