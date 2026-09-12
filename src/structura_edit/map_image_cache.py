from collections import OrderedDict
from contextlib import closing

from PySide6.QtGui import QImage

from .overview_store import OverviewStore


class MapImageCache:
    def __init__(self, limit=64 * 1024**2, max_entries=2048):
        self.limit = limit
        self.max_entries = max_entries
        self.entries = OrderedDict()
        self.bytes = 0

    def read(self, path, keys):
        result, missing = {}, []
        for key in keys:
            identity = path, key
            if identity in self.entries:
                image = self.entries[identity]
                self.entries.move_to_end(identity)
                if image is not None:
                    result[key] = QImage(image)
            else:
                missing.append(key)
        if missing:
            with closing(OverviewStore(path)) as store:
                for key in missing:
                    array = store.read_map(key)
                    image = None if array is None else QImage(array.data, array.shape[1], array.shape[0], array.strides[0],
                                                              QImage.Format.Format_RGBA8888).copy()
                    self.entries[path, key] = image
                    if image is not None:
                        self.bytes += image.sizeInBytes()
                        result[key] = QImage(image)
                    while self.bytes > self.limit or len(self.entries) > self.max_entries:
                        old = self.entries.popitem(last=False)[1]
                        if old is not None:
                            self.bytes -= old.sizeInBytes()
        return result
