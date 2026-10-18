"""
Winamp-style Playlist Widget with Drag & Drop support for files and folders,
search filter, track reordering, and status indicators for paired Click tracks.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.playlist_manager import DEFAULT_CLICK_VOLUME
from core.track_scanner import TrackItem


class PlaylistTableWidget(QTableWidget):
    """Custom QTableWidget accepting external file/folder Drag & Drop and Delete key."""

    filesDropped = Signal(list)
    deleteRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 5, parent)
        self.setAcceptDrops(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)

        headers = ["#", "Tema", "Carpeta / Disco", "Estado Click", "Vol. Click"]
        self.setHorizontalHeaderLabels(headers)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 42)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.setColumnWidth(2, 180)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(3, 115)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(4, 85)

        self.setStyleSheet(
            """
            QTableWidget {
                background-color: #0d1117;
                alternate-background-color: #121820;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                font-size: 13px;
                selection-background-color: #1f6feb;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #161b22;
                color: #8b949e;
                font-weight: bold;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid #30363d;
                padding: 6px;
            }
            """
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            paths: List[str] = []
            for url in event.mimeData().urls():
                local = url.toLocalFile()
                if local:
                    paths.append(local)
            if paths:
                self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.deleteRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class PlaylistWidget(QFrame):
    """Complete Winamp-style playlist section with toolbar, search filter, and table."""

    filesDropped = Signal(list)
    trackActivated = Signal(int)      # Double-clicked or Enter on track index
    addFilesRequested = Signal()
    addFolderRequested = Signal()
    moveUpRequested = Signal(int)
    moveDownRequested = Signal(int)
    removeTrackRequested = Signal(int)
    clearPlaylistRequested = Signal()
    savePlaylistRequested = Signal()
    loadPlaylistRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PlaylistContainer")
        self._items_cache: List[TrackItem] = []
        self._active_index: int = -1
        self._is_playing: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header & Search Bar Row
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        title_lbl = QLabel("PLAYLIST (BACKING + CLICK AUTO-EMPAREJADO)")
        title_lbl.setStyleSheet("font-weight: 700; font-size: 12px; color: #58a6ff; letter-spacing: 0.6px;")
        top_bar.addWidget(title_lbl)

        self.count_label = QLabel("0 temas")
        self.count_label.setStyleSheet("font-size: 12px; color: #8b949e;")
        top_bar.addWidget(self.count_label)

        top_bar.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Filtrar tema o disco...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedWidth(240)
        self.search_input.setStyleSheet(
            """
            QLineEdit {
                background-color: #0d1117;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #58a6ff;
            }
            """
        )
        self.search_input.textChanged.connect(self._apply_filter)
        top_bar.addWidget(self.search_input)

        layout.addLayout(top_bar)

        # Playlist Table
        self.table = PlaylistTableWidget()
        self.table.filesDropped.connect(self.filesDropped.emit)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.deleteRequested.connect(self._on_delete_current)
        layout.addWidget(self.table, 1)

        # Bottom Action Toolbar
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(6)

        self.btn_add_files = self._make_btn("➕ Abrir Tema(s)", "Seleccionar archivo(s) y cargar su click automáticamente")
        self.btn_add_folder = self._make_btn("📁 Abrir Carpeta", "Cargar carpeta o subcarpetas completas con sus clicks")
        self.btn_up = self._make_btn("⬆ Subir", "Mover tema hacia arriba")
        self.btn_down = self._make_btn("⬇ Bajar", "Mover tema hacia abajo")
        self.btn_remove = self._make_btn("🗑 Quitar", "Quitar tema seleccionado de la lista (Supr)")
        self.btn_clear = self._make_btn("🧹 Limpiar", "Vaciar toda la playlist")

        self.btn_save = self._make_btn("💾 Guardar Lista", "Guardar playlist y volúmenes personalizados (.dpls)")
        self.btn_load = self._make_btn("📂 Cargar Lista", "Abrir una playlist guardada (.dpls)")

        self.btn_add_files.clicked.connect(self.addFilesRequested.emit)
        self.btn_add_folder.clicked.connect(self.addFolderRequested.emit)
        self.btn_up.clicked.connect(self._on_move_up)
        self.btn_down.clicked.connect(self._on_move_down)
        self.btn_remove.clicked.connect(self._on_delete_current)
        self.btn_clear.clicked.connect(self.clearPlaylistRequested.emit)
        self.btn_save.clicked.connect(self.savePlaylistRequested.emit)
        self.btn_load.clicked.connect(self.loadPlaylistRequested.emit)

        btn_bar.addWidget(self.btn_add_files)
        btn_bar.addWidget(self.btn_add_folder)
        btn_bar.addSpacing(8)
        btn_bar.addWidget(self.btn_up)
        btn_bar.addWidget(self.btn_down)
        btn_bar.addWidget(self.btn_remove)
        btn_bar.addWidget(self.btn_clear)
        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_load)
        btn_bar.addWidget(self.btn_save)

        layout.addLayout(btn_bar)

    @staticmethod
    def _make_btn(text: str, tooltip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            """
            QPushButton {
                background-color: #21262d;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #30363d;
                color: #ffffff;
            }
            """
        )
        return btn

    def selected_playlist_index(self) -> int:
        row = self.table.currentRow()
        if row < 0:
            return -1
        item = self.table.item(row, 0)
        if item is None:
            return -1
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _on_cell_double_clicked(self, row: int, _col: int) -> None:
        item = self.table.item(row, 0)
        if item is not None:
            idx = int(item.data(Qt.ItemDataRole.UserRole))
            self.trackActivated.emit(idx)

    def _on_move_up(self) -> None:
        idx = self.selected_playlist_index()
        if idx >= 0:
            self.moveUpRequested.emit(idx)

    def _on_move_down(self) -> None:
        idx = self.selected_playlist_index()
        if idx >= 0:
            self.moveDownRequested.emit(idx)

    def _on_delete_current(self) -> None:
        idx = self.selected_playlist_index()
        if idx >= 0:
            self.removeTrackRequested.emit(idx)

    def refresh(
        self,
        items: List[TrackItem],
        active_index: int,
        is_playing: bool,
        selected_index: int | None = None,
    ) -> None:
        self._items_cache = list(items)
        self._active_index = active_index
        self._is_playing = is_playing

        total = len(items)
        with_click = sum(1 for it in items if it.has_click)
        self.count_label.setText(f"({total} temas · {with_click} con click)")

        self.table.setRowCount(total)
        bold_font = QFont()
        bold_font.setBold(True)

        for idx, track in enumerate(items):
            is_current = idx == active_index
            prefix = ("▶ " if is_playing else "⏸ ") if is_current else ""

            # Column 0: Index
            col_num = QTableWidgetItem(f"{prefix}{idx + 1}")
            col_num.setData(Qt.ItemDataRole.UserRole, idx)
            col_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Column 1: Clean Song Title
            col_title = QTableWidgetItem(track.display_name)
            tooltip_lines = [f"Tema: {track.display_name}"]
            if track.backing_path:
                tooltip_lines.append(f"Backing: {Path(track.backing_path).name}")
            else:
                tooltip_lines.append("Backing: (No disponible)")
            if track.click_path:
                tooltip_lines.append(f"Click: {Path(track.click_path).name}")
            else:
                tooltip_lines.append("Click: (No encontrado)")
            col_title.setToolTip("\n".join(tooltip_lines))

            # Column 2: Folder / Album
            col_folder = QTableWidgetItem(track.folder_name)
            col_folder.setForeground(QColor("#8b949e"))

            # Column 3: Click Status
            if track.has_click and track.has_backing:
                col_status = QTableWidgetItem("🎯 Click OK")
                col_status.setForeground(QColor("#3fb950"))
            elif track.has_click and not track.has_backing:
                col_status = QTableWidgetItem("🥁 Solo Click")
                col_status.setForeground(QColor("#d29922"))
            else:
                col_status = QTableWidgetItem("⚠️ Sin Click")
                col_status.setForeground(QColor("#d29922"))
            col_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Column 4: Click Volume %
            vol_pct = int(round((track.click_volume if track.click_volume is not None else DEFAULT_CLICK_VOLUME) * 100))
            col_vol = QTableWidgetItem(f"{vol_pct}%")
            col_vol.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if track.click_volume is not None and abs(track.click_volume - DEFAULT_CLICK_VOLUME) > 0.005:
                col_vol.setForeground(QColor("#f78166"))
            else:
                col_vol.setForeground(QColor("#8b949e"))

            for col_i, cell in enumerate((col_num, col_title, col_folder, col_status, col_vol)):
                if is_current:
                    cell.setFont(bold_font)
                    if col_i in (0, 1):
                        cell.setForeground(QColor("#58a6ff"))
                self.table.setItem(idx, col_i, cell)

        target_sel = selected_index if selected_index is not None else active_index
        if 0 <= target_sel < total:
            self.table.selectRow(target_sel)

        self._apply_filter(self.search_input.text())

    def _apply_filter(self, query: str) -> None:
        q = query.strip().lower()
        for row in range(self.table.rowCount()):
            if not q:
                self.table.setRowHidden(row, False)
                continue
            title_item = self.table.item(row, 1)
            folder_item = self.table.item(row, 2)
            t_text = title_item.text().lower() if title_item else ""
            f_text = folder_item.text().lower() if folder_item else ""
            match = (q in t_text) or (q in f_text)
            self.table.setRowHidden(row, not match)
