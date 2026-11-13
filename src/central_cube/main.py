"""CENTRAL CUBE desktop application entry point."""
from __future__ import annotations

import sys
from pathlib import Path

from platformdirs import user_data_dir


def main() -> int:
    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is not installed. Run: pip install -e '.[dev]'")
        return 2

    from central_cube.core.database import Database
    from central_cube.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("CENTRAL CUBE")
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    logo_path = bundle_root / "assets" / "central_cube.ico"
    if logo_path.exists():
        app.setWindowIcon(QIcon(str(logo_path)))
    data_dir = Path(user_data_dir("CentralCube", "CentralCube"))
    database = Database(data_dir / "central_cube.sqlite3")
    window = MainWindow(database)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
