from pathlib import Path


def fingerprint(path):
    try:
        stat = Path(path).stat()
        return [stat.st_mtime_ns, stat.st_size, stat.st_ino]
    except FileNotFoundError:
        return None


def resource_stamp(path):
    path = Path(path).resolve()
    if path.is_dir():
        return [(str(file.relative_to(path)), fingerprint(file)) for file in sorted(path.rglob("*")) if file.is_file()]
    return fingerprint(path)
