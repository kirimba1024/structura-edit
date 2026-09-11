from pathlib import Path

from PySide6.QtGui import QIcon


def tool_icon(name):
    return QIcon(str(Path(__file__).parent / "data" / "tools" / f"{name}.svg"))
