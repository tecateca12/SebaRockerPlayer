"""
LivePrompter (.txt) lyrics parser and scroll timing calculator.

Supports standard LivePrompter / ChordPro tags used in live performance files:
- {artist:...}, {title:...} / {t:...}, {subtitle:...} / {st:...}
- {duration:mm:ss} or {duration:seconds}
- {soc} / {start_of_chorus} ... {eoc} / {end_of_chorus}
- {sob} / {start_of_bridge} ... {eob} / {end_of_bridge}
- {comment:...} / {c:...}
- {d_time:mm:ss} or {d_time:seconds} (precision timestamp anchors)
- {pause:seconds} (scroll pause segments)
- Automatically strips chord brackets (e.g. [Am], [G7]) so only clean lyrics are shown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

_TAG_LINE_RE = re.compile(r"^\s*\{(?P<tag>[a-zA-Z0-9_]+)(?::(?P<val>.*))?\}\s*$")
# Matches inline chord brackets like [Am], [G/B], [F#m7] to strip them cleanly
_CHORD_BRACKET_RE = re.compile(r"\[[A-G][^\]]*\]")


def parse_time_value(raw: str) -> Optional[float]:
    """
    Parse a time string in 'mm:ss', 'hh:mm:ss', or 'seconds' format into float seconds.
    Examples:
        '02:35' -> 155.0
        '45' -> 45.0
    """
    text = raw.strip()
    if not text:
        return None
    if ":" in text:
        parts = text.split(":")
        try:
            if len(parts) == 2:
                mins = int(parts[0].strip())
                secs = float(parts[1].strip())
                return max(0.0, mins * 60.0 + secs)
            if len(parts) == 3:
                hrs = int(parts[0].strip())
                mins = int(parts[1].strip())
                secs = float(parts[2].strip())
                return max(0.0, hrs * 3600.0 + mins * 60.0 + secs)
        except ValueError:
            return None
    try:
        return max(0.0, float(text))
    except ValueError:
        return None


@dataclass
class LyricLine:
    """A single visual line of lyrics to render in the Teleprompter."""

    text: str
    is_chorus: bool = False
    is_bridge: bool = False
    is_comment: bool = False
    anchor_seconds: Optional[float] = None
    pause_seconds: float = 0.0


@dataclass
class ParsedLyrics:
    """Complete parsed representation of a LivePrompter .txt file."""

    title: Optional[str] = None
    artist: Optional[str] = None
    duration_seconds: Optional[float] = None
    lines: List[LyricLine] = field(default_factory=list)
    raw_text: str = ""

    @property
    def is_empty(self) -> bool:
        return len(self.lines) == 0

    def effective_duration(self, fallback_audio_duration: float) -> float:
        """
        Return the scroll duration in seconds:
        Uses {duration:mm:ss} from the .txt file if present and > 0,
        otherwise falls back to the audio track's duration.
        """
        if self.duration_seconds is not None and self.duration_seconds > 0.0:
            return self.duration_seconds
        return max(1.0, float(fallback_audio_duration))

    def _build_keyframes(self, total_duration: float) -> List[Tuple[float, float]]:
        """
        Build piecewise linear keyframes (time_seconds, normalized_pos_0_to_1)
        incorporating any {d_time:...} and {pause:...} tags.
        """
        n = len(self.lines)
        if n <= 1:
            return [(0.0, 0.0), (max(1.0, total_duration), 1.0)]

        keyframes: List[Tuple[float, float]] = [(0.0, 0.0)]
        has_custom_timing = any(
            (ln.anchor_seconds is not None or ln.pause_seconds > 0.0) for ln in self.lines
        )

        if not has_custom_timing:
            keyframes.append((max(1.0, total_duration), 1.0))
            return keyframes

        last_t = 0.0
        last_pos = 0.0
        for idx, ln in enumerate(self.lines):
            pos = idx / float(n - 1)
            if ln.anchor_seconds is not None and ln.anchor_seconds >= last_t:
                last_t = ln.anchor_seconds
                last_pos = pos
                keyframes.append((last_t, last_pos))
            if ln.pause_seconds > 0.0:
                if ln.anchor_seconds is None:
                    rem_time = max(0.0, total_duration - last_t)
                    rem_pos = max(0.0001, 1.0 - last_pos)
                    est_t = last_t + rem_time * ((pos - last_pos) / rem_pos)
                    last_t = est_t
                    last_pos = pos
                    keyframes.append((last_t, last_pos))
                last_t += ln.pause_seconds
                keyframes.append((last_t, last_pos))

        end_t = max(last_t + 0.1, total_duration)
        keyframes.append((end_t, 1.0))
        return keyframes

    def compute_scroll_ratio(
        self,
        elapsed_seconds: float,
        fallback_audio_duration: float = 0.0,
    ) -> float:
        """
        Given current playback time in seconds, return the normalized scroll ratio [0.0, 1.0]
        from beginning to end of the lyrics.
        """
        total_dur = self.effective_duration(fallback_audio_duration)
        if elapsed_seconds <= 0.0:
            return 0.0
        if elapsed_seconds >= total_dur:
            return 1.0

        keyframes = self._build_keyframes(total_dur)
        for i in range(len(keyframes) - 1):
            t0, p0 = keyframes[i]
            t1, p1 = keyframes[i + 1]
            if t0 <= elapsed_seconds <= t1:
                if t1 <= t0:
                    return p1
                alpha = (elapsed_seconds - t0) / (t1 - t0)
                return max(0.0, min(1.0, p0 + alpha * (p1 - p0)))

        return 1.0

    def active_line_index(
        self,
        elapsed_seconds: float,
        fallback_audio_duration: float = 0.0,
    ) -> int:
        """Return the index of the lyric line currently at the focus point."""
        if not self.lines:
            return -1
        ratio = self.compute_scroll_ratio(elapsed_seconds, fallback_audio_duration)
        idx = int(round(ratio * (len(self.lines) - 1)))
        return max(0, min(len(self.lines) - 1, idx))


def read_text_file_auto_encoding(file_path: str | Path) -> str:
    """Read a .txt file trying UTF-8 first and falling back to Latin-1 / CP1252."""
    path = Path(file_path)
    raw_bytes = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def parse_liveprompter_text(raw_text: str) -> ParsedLyrics:
    """Parse a LivePrompter / ChordPro text string into a ParsedLyrics object."""
    result = ParsedLyrics(raw_text=raw_text)

    in_chorus = False
    in_bridge = False
    pending_anchor: Optional[float] = None
    pending_pause: float = 0.0

    for raw_line in raw_text.splitlines():
        m_tag = _TAG_LINE_RE.match(raw_line)
        if m_tag:
            tag = m_tag.group("tag").strip().lower()
            val = (m_tag.group("val") or "").strip()

            if tag in ("title", "t"):
                result.title = val
            elif tag in ("artist", "subtitle", "st", "a"):
                result.artist = val
            elif tag == "duration":
                parsed_dur = parse_time_value(val)
                if parsed_dur is not None and parsed_dur > 0:
                    result.duration_seconds = parsed_dur
            elif tag in ("soc", "start_of_chorus"):
                in_chorus = True
            elif tag in ("eoc", "end_of_chorus"):
                in_chorus = False
            elif tag in ("sob", "start_of_bridge"):
                in_bridge = True
            elif tag in ("eob", "end_of_bridge"):
                in_bridge = False
            elif tag in ("comment", "c", "comment_italic", "ci", "comment_box", "cb"):
                if val:
                    result.lines.append(
                        LyricLine(
                            text=val,
                            is_chorus=in_chorus,
                            is_bridge=in_bridge,
                            is_comment=True,
                            anchor_seconds=pending_anchor,
                            pause_seconds=pending_pause,
                        )
                    )
                    pending_anchor = None
                    pending_pause = 0.0
            elif tag == "d_time":
                t_val = parse_time_value(val)
                if t_val is not None:
                    pending_anchor = t_val
            elif tag == "pause":
                p_val = parse_time_value(val)
                if p_val is not None:
                    pending_pause += p_val
            continue

        clean_line = _CHORD_BRACKET_RE.sub("", raw_line).rstrip()

        if not clean_line.strip():
            if not result.lines:
                continue
            if not result.lines[-1].text.strip():
                continue

        result.lines.append(
            LyricLine(
                text=clean_line,
                is_chorus=in_chorus,
                is_bridge=in_bridge,
                is_comment=False,
                anchor_seconds=pending_anchor,
                pause_seconds=pending_pause,
            )
        )
        pending_anchor = None
        pending_pause = 0.0

    while result.lines and not result.lines[-1].text.strip():
        result.lines.pop()

    return result


def parse_liveprompter_file(file_path: str | Path) -> ParsedLyrics:
    """Read and parse a LivePrompter .txt file from disk."""
    raw_text = read_text_file_auto_encoding(file_path)
    return parse_liveprompter_text(raw_text)
