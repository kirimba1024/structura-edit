from hashlib import sha256
import json
from uuid import uuid4
import zipfile

import numpy as np
from structura_render.geometry import TexturedMesh

from .file_state import resource_stamp
from .local_store import storage_root
from .array_codec import encode_arrays


CACHE_VERSION = 3
CACHE_BYTES = 512 * 1024**2


class GeometryCache:
    def __init__(self, bank):
        identity = repr((CACHE_VERSION, bank.context.root, resource_stamp(bank.context.root)))
        self.directory = storage_root() / 'geometry' / sha256(identity.encode()).hexdigest()
        self.entries = None

    def path(self, key):
        return self.directory / (key[1].hex() + '.npz')

    def get(self, key):
        try:
            path = self.path(key)
            with zipfile.ZipFile(path) as archive:
                if sum(entry.file_size for entry in archive.infolist()) > 192 * 1024**2:
                    return None
            with np.load(path, allow_pickle=False) as arrays:
                metadata = json.loads(arrays['metadata'].tobytes())
                meshes = [TexturedMesh(*(arrays[f'm{i}_{field}'] for field in ('points', 'quads', 'uv', 'alpha_modes', 'image')))
                          for i in range(metadata.pop('meshes'))]
                flat = [tuple(arrays[f'f{i}_{field}'] for field in ('points', 'faces', 'color'))
                        for i in range(metadata.pop('flat'))]
            return dict(metadata, meshes=meshes, flat=flat, layers={}, signature=key, seconds=0)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, zipfile.BadZipFile):
            return None

    def put(self, key, data):
        arrays = {}
        for i, mesh in enumerate(data['meshes']):
            arrays.update((f'm{i}_{field}', getattr(mesh, field)) for field in ('points', 'quads', 'uv', 'alpha_modes', 'image'))
        for i, part in enumerate(data['flat']):
            arrays.update((f'f{i}_{field}', value) for field, value in zip(('points', 'faces', 'color'), part))
        metadata = dict(meshes=len(data['meshes']), flat=len(data['flat']), geometry_bytes=data['geometry_bytes'],
                        warnings=data['warnings'], textured=data['textured'])
        arrays['metadata'] = np.frombuffer(json.dumps(metadata).encode(), np.uint8)
        payload = encode_arrays(**arrays)
        temporary = self.directory / (uuid4().hex + '.tmp')
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(payload)
            path = self.path(key)
            temporary.replace(path)
            self.prune(path)
        except OSError:
            temporary.unlink(missing_ok=True)

    def prune(self, path):
        if self.entries is None:
            self.entries = {file: (file.stat().st_mtime_ns, file.stat().st_size)
                            for file in self.directory.parent.glob('*/*.npz')}
        self.entries[path] = path.stat().st_mtime_ns, path.stat().st_size
        size = sum(value[1] for value in self.entries.values())
        for file in sorted(self.entries, key=lambda file: self.entries[file][0]):
            if size <= CACHE_BYTES and len(self.entries) <= 2048:
                break
            size -= self.entries.pop(file)[1]
            file.unlink(missing_ok=True)
