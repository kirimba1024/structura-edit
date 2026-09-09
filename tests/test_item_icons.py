import pytest

from structura_edit.item_icons import render_icons
from structura_edit.tasks import execute


def assets_available():
    from structura_render.assets import AssetContext
    from structura_render.textures import TextureBank

    return TextureBank(AssetContext()).available()


@pytest.mark.skipif(not assets_available(), reason="client assets are not installed")
def test_render_icons_uses_item_models():
    icons = render_icons(("minecraft:diamond", "minecraft:stone", "modded:missing"), None)
    assert sorted(icons) == ["minecraft:diamond", "minecraft:stone"]
    assert icons["minecraft:diamond"].startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.skipif(not assets_available(), reason="client assets are not installed")
def test_item_icons_task_round_trip():
    icons = execute("item_icons", {"ids": ("minecraft:diamond",), "assets": None})
    assert "minecraft:diamond" in icons


def test_render_icons_empty_ids():
    assert render_icons((), None) == {}
