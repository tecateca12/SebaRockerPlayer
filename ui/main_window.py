"""
Main Window for the Dual-Track Synchronized Audio Player (Backing + Click).
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.audio_engine import DualTrackAudioEngine
from core.playlist_manager import DEFAULT_CLICK_VOLUME, PlaylistManager
from core.track_scanner import SUPPORTED_EXTENSIONS, TrackItem
from ui.mixer_widget import MixerWidget
from ui.playlist_widget import PlaylistWidget


def format_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    total_sec = int(seconds)
    mins = total_sec // 60
    secs = total_sec % 60
    return f"{mins:02d}:{secs:02d}"


class MainWindow(QMainWindow):
    """Winamp-inspired Dual-Track Synchronized Player Main Window."""

    trackFinishedOnAudioThread = Signal()

    def __init__(self, initial_paths: List[str] | None = None) -> None:
        super().__init__()
        self.setWindowTitle("SebaRockerPlayer — Backing + Click (Sample-Accurate)")
        self.setMinimumSize(860, 660)
        self.resize(940, 720)
        self.setAcceptDrops(True)

        self.engine = DualTrackAudioEngine()
        self.playlist = PlaylistManager()

        # Connect thread-safe end-of-track signal
        self.trackFinishedOnAudioThread.connect(self._handle_track_finished)
        self.engine.on_track_finished = self.trackFinishedOnAudioThread.emit

        self._user_seeking: bool = False

        self._build_ui()
        self._connect_signals()
        self._populate_audio_devices()

        # 30 FPS UI timer for time display, seek bar, and live VU meters
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(33)
        self._ui_timer.timeout.connect(self._update_telemetry)
        self._ui_timer.start()

        if initial_paths:
            self.add_paths_to_playlist(initial_paths, auto_load_first=True)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#CentralRoot {
                background-color: #0d1117;
                color: #e6edf3;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }
            QFrame#DeckDisplay {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 10px;
            }
            QFrame#PlaylistContainer {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 10px;
            }
            """
        )

        central = QWidget()
        central.setObjectName("CentralRoot")
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)

        # 1. Top Winamp Deck Display + Transport
        deck_frame = QFrame()
        deck_frame.setObjectName("DeckDisplay")
        deck_layout = QVBoxLayout(deck_frame)
        deck_layout.setContentsMargins(14, 12, 14, 12)
        deck_layout.setSpacing(10)

        # Top row of deck: Track Title & Digital Clock
        info_row = QHBoxLayout()
        info_row.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)

        self.song_title_lbl = QLabel("Arrastrá un tema o carpeta para empezar")
        self.song_title_lbl.setStyleSheet(
            "font-size: 18px; font-weight: 800; color: #f0f6fc;"
        )
        title_col.addWidget(self.song_title_lbl)

        self.song_meta_lbl = QLabel("Soporta emparejamiento automático: '<Tema> d.wav' + '<Tema> click.mp3'")
        self.song_meta_lbl.setStyleSheet("font-size: 12px; color: #8b949e;")
        title_col.addWidget(self.song_meta_lbl)

        info_row.addLayout(title_col, 1)

        # Badges & Digital Time Counter
        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        right_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.time_lbl = QLabel("00:00 / 00:00")
        self.time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.time_lbl.setStyleSheet(
            """
            font-family: 'Menlo', 'Consolas', monospace;
            font-size: 24px;
            font-weight: 800;
            color: #3fb950;
            background-color: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 4px 10px;
            """
        )
        right_col.addWidget(self.time_lbl)

        badges_row = QHBoxLayout()
        badges_row.setSpacing(6)

        self.sync_badge = QLabel("🔒 SYNC PERFECTO")
        self.sync_badge.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #3fb950; background: #0d1117; "
            "border: 1px solid #238636; border-radius: 4px; padding: 2px 6px;"
        )
        badges_row.addWidget(self.sync_badge)

        self.sr_badge = QLabel("-- kHz")
        self.sr_badge.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #58a6ff; background: #0d1117; "
            "border: 1px solid #1f6feb; border-radius: 4px; padding: 2px 6px;"
        )
        badges_row.addWidget(self.sr_badge)

        right_col.addLayout(badges_row)
        info_row.addLayout(right_col)

        deck_layout.addLayout(info_row)

        # Seek Slider
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 10000)
        self.seek_slider.setValue(0)
        self.seek_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.seek_slider.setStyleSheet(
            """
            QSlider::groove:horizontal {
                border: 1px solid #30363d;
                height: 8px;
                background: #0d1117;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f6feb, stop:1 #58a6ff);
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 2px solid #58a6ff;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            """
        )
        deck_layout.addWidget(self.seek_slider)

        # Transport & Mode Bar
        transport_row = QHBoxLayout()
        transport_row.setSpacing(8)

        self.btn_prev = self._make_transport_btn("⏮ Anterior", "#21262d", "#c9d1d9", min_width=105)
        self.btn_play = self._make_transport_btn("▶ Play", "#238636", "#ffffff", min_width=110)
        self.btn_stop = self._make_transport_btn("⏹ Stop", "#21262d", "#c9d1d9", min_width=90)
        self.btn_next = self._make_transport_btn("⏭ Siguiente", "#21262d", "#c9d1d9", min_width=108)

        transport_row.addWidget(self.btn_prev)
        transport_row.addWidget(self.btn_play)
        transport_row.addWidget(self.btn_stop)
        transport_row.addWidget(self.btn_next)

        transport_row.addSpacing(12)

        # Toggle between Continuous (Winamp) and Stop-at-end (Live/Rehearsal)
        self.btn_mode = QPushButton("🔄 Modo: Continuo (Winamp)")
        self.btn_mode.setCheckable(True)
        self.btn_mode.setChecked(True)
        self.btn_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode.setToolTip(
            "Alternar entre reproducción continua (pasa al siguiente tema solo) "
            "o modo Vivo/Ensayo (frena al terminar el tema)"
        )
        self._update_mode_btn_style(True)
        transport_row.addWidget(self.btn_mode)

        transport_row.addStretch()

        # Audio Output Device Selector
        dev_lbl = QLabel("Salida:")
        dev_lbl.setStyleSheet("font-size: 12px; color: #8b949e; font-weight: 600;")
        transport_row.addWidget(dev_lbl)

        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(210)
        self.device_combo.setStyleSheet(
            """
            QComboBox {
                background-color: #0d1117;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 12px;
            }
            """
        )
        transport_row.addWidget(self.device_combo)

        deck_layout.addLayout(transport_row)
        root_layout.addWidget(deck_frame)

        # 2. Mixer Panel (Master 100%, Backing 100%, Click 60%)
        self.mixer = MixerWidget()
        root_layout.addWidget(self.mixer)

        # 3. Playlist Panel (Drag & Drop + Auto-pairing)
        self.playlist_widget = PlaylistWidget()
        root_layout.addWidget(self.playlist_widget, 1)

        # Keyboard shortcut: Spacebar for Play/Pause
        self.space_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self.space_shortcut.activated.connect(self.on_play_pause_clicked)

    @staticmethod
    def _make_transport_btn(
        text: str, bg: str, fg: str, min_width: int = 90
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setMinimumWidth(min_width)
        btn.setFixedHeight(34)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid #30363d;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 700;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                border: 1px solid #58a6ff;
            }}
            """
        )
        return btn

    def _update_mode_btn_style(self, continuous: bool) -> None:
        if continuous:
            self.btn_mode.setText("🔄 Modo: Continuo (Winamp)")
            self.btn_mode.setStyleSheet(
                """
                QPushButton {
                    background-color: #1f6feb;
                    color: #ffffff;
                    border: 1px solid #388bfd;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 700;
                    padding: 6px 12px;
                }
                """
            )
        else:
            self.btn_mode.setText("🛑 Modo: Detener al finalizar (Vivo)")
            self.btn_mode.setStyleSheet(
                """
                QPushButton {
                    background-color: #9e6a03;
                    color: #ffffff;
                    border: 1px solid #d29922;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 700;
                    padding: 6px 12px;
                }
                """
            )

    def _connect_signals(self) -> None:
        # Transport
        self.btn_play.clicked.connect(self.on_play_pause_clicked)
        self.btn_stop.clicked.connect(self.on_stop_clicked)
        self.btn_prev.clicked.connect(self.on_prev_clicked)
        self.btn_next.clicked.connect(self.on_next_clicked)
        self.btn_mode.toggled.connect(self.on_mode_toggled)

        # Seek slider
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.seek_slider.sliderMoved.connect(self._on_seek_moved)

        # Audio Device
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)

        # Mixer signals
        self.mixer.masterVolumeChanged.connect(self._on_master_volume_changed)
        self.mixer.backingVolumeChanged.connect(self._on_backing_volume_changed)
        self.mixer.clickVolumeChanged.connect(self._on_click_volume_changed)

        self.mixer.masterMuteToggled.connect(self._on_master_mute_toggled)
        self.mixer.backingMuteToggled.connect(self._on_backing_mute_toggled)
        self.mixer.clickMuteToggled.connect(self._on_click_mute_toggled)

        self.mixer.backingSoloToggled.connect(self._on_backing_solo_toggled)
        self.mixer.clickSoloToggled.connect(self._on_click_solo_toggled)

        # Playlist signals
        self.playlist_widget.filesDropped.connect(
            lambda paths: self.add_paths_to_playlist(paths, auto_load_first=True)
        )
        self.playlist_widget.trackActivated.connect(self.play_track_at_index)
        self.playlist_widget.addFilesRequested.connect(self.open_files_dialog)
        self.playlist_widget.addFolderRequested.connect(self.open_folder_dialog)
        self.playlist_widget.moveUpRequested.connect(self.move_track_up)
        self.playlist_widget.moveDownRequested.connect(self.move_track_down)
        self.playlist_widget.removeTrackRequested.connect(self.remove_track_at)
        self.playlist_widget.clearPlaylistRequested.connect(self.clear_playlist)
        self.playlist_widget.savePlaylistRequested.connect(self.save_playlist_dialog)
        self.playlist_widget.loadPlaylistRequested.connect(self.load_playlist_dialog)

    def _populate_audio_devices(self) -> None:
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem("Por defecto del sistema", None)
        for dev in self.engine.list_output_devices():
            self.device_combo.addItem(f"{dev.name} ({int(dev.default_samplerate)} Hz)", dev.index)
        self.device_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Drag & Drop on MainWindow
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
            if paths:
                self.add_paths_to_playlist(paths, auto_load_first=True)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    # ------------------------------------------------------------------
    # Playlist & Track Loading Operations
    # ------------------------------------------------------------------
    def add_paths_to_playlist(self, paths: List[str], auto_load_first: bool = True) -> None:
        was_empty = len(self.playlist.items) == 0
        # Check if user dropped a .dpls playlist file directly
        playlist_files = [p for p in paths if Path(p).is_file() and Path(p).suffix.lower() == ".dpls"]
        media_paths = [p for p in paths if p not in playlist_files]

        for pl_file in playlist_files:
            try:
                self.playlist.load_playlist(pl_file, append=not was_empty)
                self.btn_mode.setChecked(self.playlist.continuous_playback)
            except Exception as exc:
                QMessageBox.warning(self, "Error al cargar playlist", str(exc))

        if media_paths:
            self.playlist.add_paths(media_paths, recursive=True)

        self._refresh_playlist_ui()

        if was_empty and auto_load_first and self.playlist.current_item is not None:
            self._load_track_item(self.playlist.current_item, auto_play=False)

    def _load_track_item(self, item: TrackItem, auto_play: bool = False) -> bool:
        try:
            # Apply per-song saved click volume (or 60% default)
            click_vol = self.playlist.get_track_click_volume(item)
            self.engine.click_volume = click_vol
            self.mixer.click_strip.set_volume_silent(click_vol)

            stats = self.engine.load_tracks(item.backing_path, item.click_path)
            item.duration_seconds = stats.duration_seconds
            item.sample_rate = stats.sample_rate

            # Update Deck header
            self.song_title_lbl.setText(item.display_name)
            sr_khz = f"{stats.sample_rate / 1000.0:.1f} kHz"
            self.sr_badge.setText(f"{sr_khz} NATIVO")

            meta_parts = []
            if item.folder_name:
                meta_parts.append(f"📁 {item.folder_name}")
            if stats.has_backing and stats.has_click:
                meta_parts.append("🎯 Backing + Click sincronizados")
                if (
                    stats.backing_sr_original
                    and stats.click_sr_original
                    and stats.backing_sr_original != stats.click_sr_original
                ):
                    meta_parts.append(
                        f"(Click adaptado de {stats.click_sr_original}Hz a {stats.sample_rate}Hz)"
                    )
                self.sync_badge.setText("🔒 SYNC PERFECTO")
            elif stats.has_backing:
                meta_parts.append("⚠️ Solo Backing (No se encontró archivo click)")
                self.sync_badge.setText("⚠️ SIN CLICK")
            else:
                meta_parts.append("🥁 Solo Click")

            self.song_meta_lbl.setText("  ·  ".join(meta_parts))
            self.seek_slider.setValue(0)
            self.time_lbl.setText(f"00:00 / {format_time(stats.duration_seconds)}")

            if auto_play:
                self.engine.play()

            self._update_play_button_state()
            self._refresh_playlist_ui()
            return True
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error al cargar audio",
                f"No se pudo cargar '{item.display_name}':\n{exc}",
            )
            return False

    def play_track_at_index(self, index: int) -> None:
        item = self.playlist.select_index(index)
        if item is not None:
            self._load_track_item(item, auto_play=True)

    # ------------------------------------------------------------------
    # Transport Handlers
    # ------------------------------------------------------------------
    def on_play_pause_clicked(self) -> None:
        if self.engine.total_frames == 0:
            if self.playlist.current_item is not None:
                self._load_track_item(self.playlist.current_item, auto_play=True)
            return

        self.engine.toggle_play_pause()
        self._update_play_button_state()
        self._refresh_playlist_ui()

    def on_stop_clicked(self) -> None:
        self.engine.stop()
        self.seek_slider.setValue(0)
        self._update_play_button_state()
        self._refresh_playlist_ui()

    def on_prev_clicked(self) -> None:
        # If more than 3 seconds into the song, restart current song; otherwise go to previous
        if self.engine.current_seconds > 3.0:
            self.engine.seek_seconds(0.0)
            return
        was_playing = self.engine.is_playing
        prev_item = self.playlist.previous_track()
        if prev_item is not None:
            self._load_track_item(prev_item, auto_play=was_playing)

    def on_next_clicked(self) -> None:
        was_playing = self.engine.is_playing
        next_item = self.playlist.next_track()
        if next_item is not None:
            self._load_track_item(next_item, auto_play=was_playing)

    def on_mode_toggled(self, checked: bool) -> None:
        self.playlist.continuous_playback = checked
        self._update_mode_btn_style(checked)

    def _handle_track_finished(self) -> None:
        """Called on main UI thread when active song finishes playing."""
        self._update_play_button_state()
        next_item = self.playlist.next_track()
        if next_item is not None:
            # If continuous mode (Winamp) is active, auto-play next song;
            # If live/rehearsal stop mode is active, cue next song ready to play.
            self._load_track_item(next_item, auto_play=self.playlist.continuous_playback)
        else:
            self.engine.stop()
            self._update_play_button_state()
            self._refresh_playlist_ui()

    def _update_play_button_state(self) -> None:
        if self.engine.is_playing:
            self.btn_play.setText("⏸ Pausa")
            self.btn_play.setStyleSheet(
                """
                QPushButton {
                    background-color: #1f6feb;
                    color: #ffffff;
                    border: 1px solid #388bfd;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: 700;
                    padding: 4px 12px;
                }
                """
            )
        else:
            self.btn_play.setText("▶ Play")
            self.btn_play.setStyleSheet(
                """
                QPushButton {
                    background-color: #238636;
                    color: #ffffff;
                    border: 1px solid #2ea043;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: 700;
                    padding: 4px 12px;
                }
                """
            )

    # ------------------------------------------------------------------
    # Seek Bar & Telemetry Loop
    # ------------------------------------------------------------------
    def _on_seek_pressed(self) -> None:
        self._user_seeking = True

    def _on_seek_moved(self, value: int) -> None:
        dur = self.engine.duration_seconds
        if dur > 0:
            preview_sec = (value / 10000.0) * dur
            self.time_lbl.setText(f"{format_time(preview_sec)} / {format_time(dur)}")

    def _on_seek_released(self) -> None:
        ratio = self.seek_slider.value() / 10000.0
        self.engine.seek_ratio(ratio)
        self._user_seeking = False

    def _update_telemetry(self) -> None:
        cur = self.engine.current_seconds
        dur = self.engine.duration_seconds

        if not self._user_seeking:
            self.time_lbl.setText(f"{format_time(cur)} / {format_time(dur)}")
            if dur > 0:
                pos_val = int(round((cur / dur) * 10000))
                self.seek_slider.blockSignals(True)
                self.seek_slider.setValue(pos_val)
                self.seek_slider.blockSignals(False)

        self.mixer.update_peaks(
            self.engine.master_peak,
            self.engine.backing_peak,
            self.engine.click_peak,
        )

    # ------------------------------------------------------------------
    # Mixer Handlers
    # ------------------------------------------------------------------
    def _on_master_volume_changed(self, val: float) -> None:
        self.engine.master_volume = val

    def _on_backing_volume_changed(self, val: float) -> None:
        self.engine.backing_volume = val

    def _on_click_volume_changed(self, val: float) -> None:
        self.engine.click_volume = val
        # Save custom click volume for the active song
        if self.playlist.current_item is not None:
            self.playlist.set_track_click_volume(self.playlist.current_item, val)
            self._refresh_playlist_ui(preserve_selection=True)

    def _on_master_mute_toggled(self, muted: bool) -> None:
        self.engine.master_muted = muted

    def _on_backing_mute_toggled(self, muted: bool) -> None:
        self.engine.backing_muted = muted

    def _on_click_mute_toggled(self, muted: bool) -> None:
        self.engine.click_muted = muted

    def _on_backing_solo_toggled(self, solo: bool) -> None:
        self.engine.backing_solo = solo

    def _on_click_solo_toggled(self, solo: bool) -> None:
        self.engine.click_solo = solo

    def _on_device_changed(self, _idx: int) -> None:
        dev_id = self.device_combo.currentData()
        self.engine.set_output_device(dev_id)

    # ------------------------------------------------------------------
    # Playlist Toolbar Actions & File Dialogs
    # ------------------------------------------------------------------
    def _refresh_playlist_ui(self, preserve_selection: bool = False) -> None:
        sel = self.playlist_widget.selected_playlist_index() if preserve_selection else None
        self.playlist_widget.refresh(
            self.playlist.items,
            self.playlist.current_index,
            self.engine.is_playing,
            selected_index=sel,
        )

    def open_files_dialog(self) -> None:
        exts = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleccionar tema(s) (el click se emparejará automáticamente)",
            str(Path.home()),
            f"Archivos de Audio ({exts});;Todos los archivos (*)",
        )
        if files:
            self.add_paths_to_playlist(files, auto_load_first=True)

    def open_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta de temas o banda (escaneo automático con subcarpetas)",
            str(Path.home()),
        )
        if folder:
            self.add_paths_to_playlist([folder], auto_load_first=True)

    def move_track_up(self, index: int) -> None:
        if self.playlist.move_item(index, index - 1):
            self._refresh_playlist_ui()
            self.playlist_widget.table.selectRow(index - 1)

    def move_track_down(self, index: int) -> None:
        if self.playlist.move_item(index, index + 1):
            self._refresh_playlist_ui()
            self.playlist_widget.table.selectRow(index + 1)

    def remove_track_at(self, index: int) -> None:
        removing_active = index == self.playlist.current_index
        self.playlist.remove_at(index)
        if removing_active:
            self.engine.stop()
            if self.playlist.current_item is not None:
                self._load_track_item(self.playlist.current_item, auto_play=False)
            else:
                self.song_title_lbl.setText("Playlist vacía")
                self.song_meta_lbl.setText("Arrastrá un tema o carpeta para empezar")
                self.time_lbl.setText("00:00 / 00:00")
        self._refresh_playlist_ui()

    def clear_playlist(self) -> None:
        self.engine.stop()
        self.playlist.clear()
        self.song_title_lbl.setText("Arrastrá un tema o carpeta para empezar")
        self.song_meta_lbl.setText(
            "Soporta emparejamiento automático: '<Tema> d.wav' + '<Tema> click.mp3'"
        )
        self.time_lbl.setText("00:00 / 00:00")
        self.seek_slider.setValue(0)
        self._update_play_button_state()
        self._refresh_playlist_ui()

    def save_playlist_dialog(self) -> None:
        if not self.playlist.items:
            QMessageBox.information(self, "Playlist vacía", "No hay temas en la lista para guardar.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar Playlist",
            str(Path.home() / "mi_playlist.dpls"),
            "DualTrack Playlist (*.dpls *.json)",
        )
        if file_path:
            if not (file_path.endswith(".dpls") or file_path.endswith(".json")):
                file_path += ".dpls"
            try:
                self.playlist.save_playlist(file_path)
            except Exception as exc:
                QMessageBox.critical(self, "Error al guardar", str(exc))

    def load_playlist_dialog(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Cargar Playlist",
            str(Path.home()),
            "DualTrack Playlist (*.dpls *.json)",
        )
        if file_path:
            try:
                self.engine.stop()
                self.playlist.load_playlist(file_path, append=False)
                self.btn_mode.setChecked(self.playlist.continuous_playback)
                self._refresh_playlist_ui()
                if self.playlist.current_item is not None:
                    self._load_track_item(self.playlist.current_item, auto_play=False)
            except Exception as exc:
                QMessageBox.critical(self, "Error al cargar", str(exc))

    def closeEvent(self, event) -> None:
        self._ui_timer.stop()
        self.engine.shutdown()
        super().closeEvent(event)
