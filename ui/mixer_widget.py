"""
Mixer widget providing independent controls for Backing, Click (default 60%),
and Master volume, including Mute/Solo buttons and real-time peak level meters.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class ChannelStripWidget(QFrame):
    """A single horizontal channel strip with slider, level meter, % readout, Mute, Solo, and Reset."""

    volumeChanged = Signal(float)   # 0.0 to 1.0
    muteToggled = Signal(bool)
    soloToggled = Signal(bool)

    def __init__(
        self,
        title: str,
        accent_color: str,
        default_percent: int = 100,
        has_solo: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._default_percent = default_percent
        self._accent_color = accent_color
        self.setObjectName("ChannelStrip")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        # Top row: Channel Title + Percentage Value + Mute / Solo / Reset buttons
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"font-weight: 700; font-size: 12px; color: {accent_color}; letter-spacing: 0.6px;"
        )
        top_row.addWidget(self.title_label)

        top_row.addStretch()

        self.value_label = QLabel(f"{default_percent}%")
        self.value_label.setFixedWidth(44)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.value_label.setStyleSheet(
            "font-family: 'Menlo', 'Consolas', monospace; font-weight: bold; font-size: 12px; color: #e6edf3;"
        )
        top_row.addWidget(self.value_label)

        self.reset_btn = QPushButton(f"{default_percent}%")
        self.reset_btn.setToolTip(f"Restaurar volumen por defecto ({default_percent}%)")
        self.reset_btn.setFixedSize(40, 22)
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #21262d;
                color: #8b949e;
                border: 1px solid #30363d;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #30363d;
                color: #f0f6fc;
            }
            """
        )
        self.reset_btn.clicked.connect(self.reset_to_default)
        top_row.addWidget(self.reset_btn)

        self.mute_btn = QPushButton("M")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setToolTip("Mute (Silenciar canal)")
        self.mute_btn.setFixedSize(26, 22)
        self.mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mute_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #21262d;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:checked {
                background-color: #da3633;
                color: #ffffff;
                border: 1px solid #f85149;
            }
            """
        )
        self.mute_btn.toggled.connect(self.muteToggled.emit)
        top_row.addWidget(self.mute_btn)

        self.solo_btn: QPushButton | None = None
        if has_solo:
            self.solo_btn = QPushButton("S")
            self.solo_btn.setCheckable(True)
            self.solo_btn.setToolTip("Solo (Escuchar únicamente este canal)")
            self.solo_btn.setFixedSize(26, 22)
            self.solo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.solo_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #21262d;
                    color: #c9d1d9;
                    border: 1px solid #30363d;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:checked {
                    background-color: #d29922;
                    color: #0d1117;
                    border: 1px solid #e3b341;
                }
                """
            )
            self.solo_btn.toggled.connect(self.soloToggled.emit)
            top_row.addWidget(self.solo_btn)

        layout.addLayout(top_row)

        # Slider row
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(default_percent)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.setStyleSheet(
            f"""
            QSlider::groove:horizontal {{
                border: 1px solid #30363d;
                height: 6px;
                background: #161b22;
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent_color};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: #f0f6fc;
                border: 2px solid {accent_color};
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            """
        )
        self.slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.slider)

        # Live VU peak meter bar
        self.vu_bar = QProgressBar()
        self.vu_bar.setRange(0, 100)
        self.vu_bar.setValue(0)
        self.vu_bar.setTextVisible(False)
        self.vu_bar.setFixedHeight(4)
        self.vu_bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: #0d1117;
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {accent_color};
                border-radius: 2px;
            }}
            """
        )
        layout.addWidget(self.vu_bar)

    def _on_slider_changed(self, value: int) -> None:
        self.value_label.setText(f"{value}%")
        self.volumeChanged.emit(value / 100.0)

    def reset_to_default(self) -> None:
        self.slider.setValue(self._default_percent)

    def set_volume_silent(self, volume_ratio: float) -> None:
        """Set slider position from code without firing user-initiated save callbacks."""
        pct = int(round(max(0.0, min(1.0, volume_ratio)) * 100))
        self.slider.blockSignals(True)
        self.slider.setValue(pct)
        self.slider.blockSignals(False)
        self.value_label.setText(f"{pct}%")

    def set_peak(self, peak: float) -> None:
        pct = int(round(max(0.0, min(1.0, peak)) * 100))
        self.vu_bar.setValue(pct)


class MixerWidget(QFrame):
    """
    Contains the 3 mixer channels:
    - MASTER (100% default, affects both Backing and Click)
    - BACKING (100% default, independent fader + Mute/Solo)
    - CLICK (60% mandatory default, independent fader + Mute/Solo)
    """

    masterVolumeChanged = Signal(float)
    backingVolumeChanged = Signal(float)
    clickVolumeChanged = Signal(float)

    masterMuteToggled = Signal(bool)
    backingMuteToggled = Signal(bool)
    clickMuteToggled = Signal(bool)

    backingSoloToggled = Signal(bool)
    clickSoloToggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MixerPanel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 1. Master Volume Strip (Affects both tracks)
        self.master_strip = ChannelStripWidget(
            title="MASTER (AMBAS PISTAS)",
            accent_color="#3fb950",
            default_percent=100,
            has_solo=False,
        )
        # 2. Backing Track Strip
        self.backing_strip = ChannelStripWidget(
            title="BACKING TRACK",
            accent_color="#58a6ff",
            default_percent=100,
            has_solo=True,
        )
        # 3. Click Track Strip (60% mandatory default)
        self.click_strip = ChannelStripWidget(
            title="CLICK TRACK",
            accent_color="#f78166",
            default_percent=60,
            has_solo=True,
        )

        for strip in (self.master_strip, self.backing_strip, self.click_strip):
            strip.setStyleSheet(
                """
                QFrame#ChannelStrip {
                    background-color: #161b22;
                    border: 1px solid #30363d;
                    border-radius: 8px;
                }
                """
            )
            layout.addWidget(strip, 1)

        # Forward signals
        self.master_strip.volumeChanged.connect(self.masterVolumeChanged.emit)
        self.backing_strip.volumeChanged.connect(self.backingVolumeChanged.emit)
        self.click_strip.volumeChanged.connect(self.clickVolumeChanged.emit)

        self.master_strip.muteToggled.connect(self.masterMuteToggled.emit)
        self.backing_strip.muteToggled.connect(self.backingMuteToggled.emit)
        self.click_strip.muteToggled.connect(self.clickMuteToggled.emit)

        self.backing_strip.soloToggled.connect(self.backingSoloToggled.emit)
        self.click_strip.soloToggled.connect(self.clickSoloToggled.emit)

    def update_peaks(self, master_peak: float, backing_peak: float, click_peak: float) -> None:
        self.master_strip.set_peak(master_peak)
        self.backing_strip.set_peak(backing_peak)
        self.click_strip.set_peak(click_peak)
