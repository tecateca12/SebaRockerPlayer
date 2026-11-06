"""
LivePrompter-style Teleprompter Widget for SebaRockerPlayer.

Features:
- Sub-pixel smooth vertical scrolling synchronized to audio playback time and {duration:mm:ss}
- Chorus block highlighting ({soc} ... {eoc}) with LivePrompter-style accent bar
- Focus Zone indicator (reading guide line at 35% height)
- Font size controls (A- / A+) for easy reading on Tablet or Desktop
- Stage Fullscreen Mode toggle ('⛶ Modo Escenario')
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.lyrics_parser import LyricLine, ParsedLyrics


def _fmt_mmss(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    return f"{s // 60:02d}:{s % 60:02d}"


class LyricsCanvas(QWidget):
    """Hardware-smooth sub-pixel teleprompter renderer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lyrics: Optional[ParsedLyrics] = None
        self._scroll_ratio: float = 0.0
        self._active_line_idx: int = -1
        self._font_size: int = 22
        self._manual_offset_px: float = 0.0
        self.setMinimumHeight(220)

    @property
    def font_size(self) -> int:
        return self._font_size

    def set_font_size(self, size: int) -> None:
        self._font_size = max(12, min(52, int(size)))
        self.update()

    def set_lyrics(self, lyrics: Optional[ParsedLyrics]) -> None:
        self._lyrics = lyrics
        self._scroll_ratio = 0.0
        self._active_line_idx = 0 if (lyrics and lyrics.lines) else -1
        self._manual_offset_px = 0.0
        self.update()

    def set_playback_time(self, elapsed_seconds: float, audio_duration: float, is_playing: bool) -> None:
        if self._lyrics is None or self._lyrics.is_empty:
            return
        if is_playing:
            self._manual_offset_px = 0.0
        self._scroll_ratio = self._lyrics.compute_scroll_ratio(elapsed_seconds, audio_duration)
        self._active_line_idx = self._lyrics.active_line_index(elapsed_seconds, audio_duration)
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        self._manual_offset_px -= delta * 0.5
        self.update()
        event.accept()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        w = float(self.width())
        h = float(self.height())

        # Dark stage background
        painter.fillRect(QRectF(0, 0, w, h), QColor("#090d12"))

        if self._lyrics is None or self._lyrics.is_empty:
            font = QFont("Helvetica Neue", 15)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#6e7681"))
            painter.drawText(
                QRectF(20, 0, w - 40, h),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                "📝 Sin letra cargada para este tema\n"
                "(Si existe un archivo '<Tema> L.txt' en la carpeta, se cargará y scrolleará automáticamente)",
            )
            painter.end()
            return

        # Focus line at 35% from top of viewport (LivePrompter reading zone)
        focus_y = h * 0.35

        # Draw subtle focus zone band and left/right triangles
        focus_band_rect = QRectF(0, focus_y - (self._font_size * 0.95), w, self._font_size * 1.9)
        painter.fillRect(focus_band_rect, QColor(31, 111, 235, 22))

        pen_focus = QPen(QColor(88, 166, 255, 90), 1.0, Qt.PenStyle.DashLine)
        painter.setPen(pen_focus)
        painter.drawLine(int(12), int(focus_y + self._font_size * 0.95), int(w - 12), int(focus_y + self._font_size * 0.95))

        # Triangle marker on left edge
        marker_path = QPainterPath()
        marker_path.moveTo(6.0, focus_y - 7.0)
        marker_path.lineTo(16.0, focus_y)
        marker_path.lineTo(6.0, focus_y + 7.0)
        marker_path.closeSubpath()
        painter.fillPath(marker_path, QColor("#58a6ff"))

        # Layout lines and compute heights with word wrapping
        base_font = QFont("Helvetica Neue", self._font_size)
        bold_font = QFont("Helvetica Neue", self._font_size, QFont.Weight.Bold)
        comment_font = QFont("Helvetica Neue", max(11, int(self._font_size * 0.80)), QFont.Weight.Bold)

        left_pad = 36.0
        right_pad = 24.0
        avail_w = max(120.0, w - left_pad - right_pad)

        lines: List[LyricLine] = self._lyrics.lines
        line_heights: List[float] = []
        line_y_centers: List[float] = []

        cursor_y = 0.0
        for ln in lines:
            if not ln.text.strip():
                lh = self._font_size * 0.9
            else:
                f = comment_font if ln.is_comment else (bold_font if ln.is_chorus else base_font)
                fm = QFontMetricsF(f)
                rect = fm.boundingRect(
                    QRectF(0, 0, avail_w, 2000),
                    Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                    ln.text,
                )
                lh = max(self._font_size * 1.45, rect.height() + self._font_size * 0.42)
            line_y_centers.append(cursor_y + lh * 0.5)
            line_heights.append(lh)
            cursor_y += lh

        total_content_h = max(1.0, cursor_y - (line_heights[-1] if line_heights else 0.0))
        scroll_px = self._scroll_ratio * total_content_h + self._manual_offset_px
        scroll_px = max(0.0, min(total_content_h, scroll_px))

        # Draw each line relative to focus_y
        running_y = focus_y - scroll_px - (line_heights[0] * 0.5 if line_heights else 0.0)

        for idx, ln in enumerate(lines):
            lh = line_heights[idx]
            y_top = running_y
            running_y += lh

            # Cull offscreen lines
            if y_top + lh < -20 or y_top > h + 20:
                continue

            if not ln.text.strip():
                continue

            is_active = idx == self._active_line_idx
            text_rect = QRectF(left_pad, y_top, avail_w, lh)

            # Chorus highlight bar & background tint ({soc} ... {eoc})
            if ln.is_chorus:
                chorus_bg = QRectF(left_pad - 12.0, y_top + 1.0, avail_w + 16.0, lh - 2.0)
                painter.fillRect(chorus_bg, QColor(247, 129, 102, 26 if not is_active else 48))
                bar_rect = QRectF(left_pad - 12.0, y_top + 1.0, 4.0, lh - 2.0)
                painter.fillRect(bar_rect, QColor("#f78166"))

            if ln.is_comment:
                painter.setFont(comment_font)
                painter.setPen(QColor("#d29922"))
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
                    f"▸ {ln.text}",
                )
            else:
                painter.setFont(bold_font if (ln.is_chorus or is_active) else base_font)
                if is_active:
                    painter.setPen(QColor("#ffffff") if not ln.is_chorus else QColor("#ffa657"))
                elif ln.is_chorus:
                    painter.setPen(QColor("#f78166"))
                else:
                    # Slight distance fade for lines far from focus
                    dist_ratio = abs((y_top + lh * 0.5) - focus_y) / max(1.0, h * 0.65)
                    alpha = int(max(115, min(235, 235 - dist_ratio * 95)))
                    painter.setPen(QColor(210, 218, 226, alpha))

                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
                    ln.text,
                )

        painter.end()


class LyricsWidget(QFrame):
    """
    Teleprompter container with header metadata, A-/A+ font zoom,
    and Stage Fullscreen Mode toggle.
    """

    stageModeToggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LyricsContainer")
        self._stage_mode: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header Bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.header_lbl = QLabel("📝 TELEPROMPTER (LIVEPROMPTER)")
        self.header_lbl.setStyleSheet(
            "font-weight: 700; font-size: 12px; color: #f78166; letter-spacing: 0.6px;"
        )
        top_bar.addWidget(self.header_lbl)

        self.meta_badge = QLabel("Sin archivo L.txt")
        self.meta_badge.setStyleSheet(
            "font-size: 11px; color: #8b949e; background: #0d1117; "
            "border: 1px solid #30363d; border-radius: 4px; padding: 2px 8px;"
        )
        top_bar.addWidget(self.meta_badge)

        top_bar.addStretch()

        # Font size buttons (A- / A+)
        self.btn_font_minus = self._make_tool_btn("A-", "Achicar tamaño de letra")
        self.btn_font_plus = self._make_tool_btn("A+", "Agrandar tamaño de letra (ideal Tablet)")
        self.btn_font_minus.clicked.connect(lambda: self._change_font(-2))
        self.btn_font_plus.clicked.connect(lambda: self._change_font(+2))
        top_bar.addWidget(self.btn_font_minus)
        top_bar.addWidget(self.btn_font_plus)

        # Stage Fullscreen Mode toggle button
        self.btn_stage = QPushButton("⛶ Modo Escenario")
        self.btn_stage.setCheckable(True)
        self.btn_stage.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stage.setToolTip("Expandir la letra a pantalla completa para tocar en vivo (F11)")
        self._update_stage_btn_style(False)
        self.btn_stage.toggled.connect(self._on_stage_toggled)
        top_bar.addWidget(self.btn_stage)

        layout.addLayout(top_bar)

        # Teleprompter Canvas
        self.canvas = LyricsCanvas()
        self.canvas.setStyleSheet("border: 1px solid #30363d; border-radius: 6px;")
        layout.addWidget(self.canvas, 1)

    @staticmethod
    def _make_tool_btn(text: str, tooltip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setFixedSize(34, 26)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            """
            QPushButton {
                background-color: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 5px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #30363d;
                border-color: #58a6ff;
            }
            """
        )
        return btn

    def _update_stage_btn_style(self, active: bool) -> None:
        if active:
            self.btn_stage.setText("✖ Salir Modo Escenario")
            self.btn_stage.setStyleSheet(
                """
                QPushButton {
                    background-color: #da3633;
                    color: #ffffff;
                    border: 1px solid #f85149;
                    border-radius: 5px;
                    padding: 4px 10px;
                    font-size: 12px;
                    font-weight: 700;
                }
                """
            )
        else:
            self.btn_stage.setText("⛶ Modo Escenario")
            self.btn_stage.setStyleSheet(
                """
                QPushButton {
                    background-color: #21262d;
                    color: #f0f6fc;
                    border: 1px solid #30363d;
                    border-radius: 5px;
                    padding: 4px 10px;
                    font-size: 12px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #30363d;
                    border-color: #f78166;
                }
                """
            )

    def _change_font(self, delta: int) -> None:
        self.canvas.set_font_size(self.canvas.font_size + delta)

    def _on_stage_toggled(self, checked: bool) -> None:
        self._stage_mode = checked
        self._update_stage_btn_style(checked)
        self.stageModeToggled.emit(checked)

    def load_parsed_lyrics(
        self,
        lyrics: Optional[ParsedLyrics],
        fallback_audio_duration: float = 0.0,
    ) -> None:
        self.canvas.set_lyrics(lyrics)
        if lyrics is None or lyrics.is_empty:
            self.meta_badge.setText("⚠️ Sin archivo L.txt")
            return

        parts: List[str] = []
        if lyrics.artist:
            parts.append(f"🎤 {lyrics.artist}")
        if lyrics.duration_seconds is not None and lyrics.duration_seconds > 0:
            parts.append(f"⏱ Scroll: {_fmt_mmss(lyrics.duration_seconds)} (tag duration)")
        elif fallback_audio_duration > 0:
            parts.append(f"⏱ Scroll: {_fmt_mmss(fallback_audio_duration)} (duración audio)")

        self.meta_badge.setText("  ·  ".join(parts) if parts else "📝 Letra activa")

    def update_scroll(self, elapsed_seconds: float, audio_duration: float, is_playing: bool) -> None:
        self.canvas.set_playback_time(elapsed_seconds, audio_duration, is_playing)
