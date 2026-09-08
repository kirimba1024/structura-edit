from functools import lru_cache
from pathlib import Path

from .file_state import resource_stamp


_active = None


def resolve_assets(assets):
    from structura_render.assets import minecraft_assets_source

    return Path(assets).expanduser().resolve() if assets else minecraft_assets_source()


def refresh_resources(assets):
    global _active
    source = resolve_assets(assets)
    key = source, resource_stamp(source)
    if key != _active:
        texture_bank.cache_clear()
        _active = key


@lru_cache(maxsize=1)
def texture_bank(assets):
    from structura_render.assets import AssetContext
    from structura_render.textures import TextureBank

    return TextureBank(AssetContext(assets))
