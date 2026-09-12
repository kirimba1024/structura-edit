import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from structura_core.nbt_io import atomic_write
from structura_core.world_backup import create_directory, digest, sync_directory


MAX_RECORD_BYTES = 128 * 1024 * 1024


def storage_root():
    configured = os.environ.get("STRUCTURA_EDIT_DATA")
    return Path(configured).expanduser() if configured else Path.home() / ".local" / "share" / "structura-edit"


def read_json(path):
    path = Path(path)
    if path.stat().st_size > MAX_RECORD_BYTES:
        raise ValueError("Local record exceeds 128 MiB")
    return json.loads(path.read_text(encoding="utf-8"))


def _sync_file(path):
    with path.open("r+b" if os.name == "nt" else "rb") as stream:
        os.fsync(stream.fileno())


def publish_bundle(root, key, write):
    directory = Path(root) / key
    create_directory(directory)
    identifier = uuid4().hex
    with TemporaryDirectory(prefix=".writing-", dir=directory) as temporary:
        stage = Path(temporary)
        metadata = write(stage)
        files = {path.relative_to(stage).as_posix(): digest(path) for path in stage.rglob("*") if path.is_file()}
        metadata = dict(metadata, schema=1, files=files)
        (stage / "record.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        for file in stage.rglob("*"):
            if file.is_file():
                _sync_file(file)
        sync_directory(stage)
        installed = directory / identifier
        stage.rename(installed)
        sync_directory(directory)
    pointer = directory / "current.json"
    old = read_json(pointer).get("current") if pointer.exists() else None
    atomic_write(pointer, json.dumps({"current": identifier, "previous": old}).encode())
    _sync_file(pointer)
    sync_directory(directory)
    sync_directory(directory.parent)
    for child in directory.iterdir():
        if child.is_dir() and len(child.name) == 32 and all(c in "0123456789abcdef" for c in child.name) and child.name not in (identifier, old):
            shutil.rmtree(child)
    return installed


def read_bundle(path):
    path = Path(path)
    metadata = read_json(path / "record.json")
    if metadata.get("schema") != 1:
        raise ValueError("Unsupported local record version")
    for name, stamp in metadata["files"].items():
        if Path(name).name != name or name in (".", "..") or digest(path / name) != stamp:
            raise ValueError("Local record is incomplete or changed")
    return metadata


def list_bundles(root):
    rows = []
    for pointer in Path(root).glob("*/current.json"):
        try:
            current = read_json(pointer)["current"]
            if len(current) != 32 or any(c not in "0123456789abcdef" for c in current):
                continue
            path = pointer.parent / current
            metadata = read_json(path / "record.json")
            rows.append(dict(metadata, path=str(path)))
        except (ValueError, OSError, KeyError, TypeError):
            continue
    return sorted(rows, key=lambda row: row.get("updated", ""), reverse=True)
