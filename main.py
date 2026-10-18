"""
Entry point for SebaRockerPlayer (Backing + Click Synchronized Player).
Compatible with macOS and Windows.
"""

from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("SebaRockerPlayer")
    app.setOrganizationName("SebaRockerPlayer")

    # Optional CLI paths (files or folders passed as arguments or dropped onto the app icon)
    initial_paths = sys.argv[1:] if len(sys.argv) > 1 else None

    window = MainWindow(initial_paths=initial_paths)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
