import io

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QPixmap


ICON_SIZE = 32


def render_icons(ids, assets):
    from structura_render.assets import AssetContext
    from structura_render.item_models import item_texture
    from structura_render.textures import TextureBank

    icons = {}
    with AssetContext(assets).activate():
        bank = TextureBank()
        for identifier in ids:
            stem = item_texture(identifier)
            image = bank.read_asset(stem) if stem else None
            if image is None:
                continue
            image = image.convert("RGBA").resize((ICON_SIZE, ICON_SIZE), 0)
            buffer = io.BytesIO()
            image.save(buffer, "PNG")
            icons[identifier] = buffer.getvalue()
    return icons


class ItemIcons(QObject):
    updated = Signal()

    def __init__(self, submit, assets):
        super().__init__()
        self.submit = submit
        self.assets = assets
        self.icons = {}
        self.pending = frozenset()

    def pixmap(self, identifier):
        data = self.icons.get(identifier)
        if data is None:
            return None
        image = QImage.fromData(data)
        return QPixmap.fromImage(image) if not image.isNull() else None

    def request(self, identifiers):
        missing = sorted(set(identifiers) - self.icons.keys() - self.pending)
        if not missing:
            return
        requested = frozenset(missing)
        self.pending = self.pending | requested

        def received(icons):
            self.icons.update(icons)
            self.pending = self.pending - requested
            if len(self.icons) > 512:
                for stale in list(self.icons)[:len(self.icons) - 512]:
                    del self.icons[stale]
            self.updated.emit()

        self.submit("item_icons", received, ids=tuple(missing), assets=self.assets())

    def forget(self):
        self.icons.clear()
        self.pending = frozenset()
