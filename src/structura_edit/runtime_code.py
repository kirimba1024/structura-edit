from importlib.util import find_spec
from pathlib import Path


class CodeVersion:
    def __init__(self, roots=None):
        self.roots = tuple(Path(find_spec(name).origin).parent for name in ("structura_edit", "structura_core", "structura_render")) if roots is None else roots
        self.version = self.snapshot()

    def snapshot(self):
        result = {}
        for root in self.roots:
            for path in root.rglob("*.py"):
                try:
                    stat = path.stat()
                    result[path] = stat.st_mtime_ns, stat.st_size
                except FileNotFoundError:
                    continue
        return result

    def check(self):
        if self.snapshot() != self.version:
            raise RuntimeError("Editor code was updated. Restart Structura before continuing.")
