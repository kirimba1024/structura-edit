from .loading import MAX_GEOMETRY_BYTES, replacement_sizes
from .preview import build_geometry, build_sections
from .sections import prepare_sections
from .source_loading import open_source


def prepare_clipboard(session, *, selection=None, clipboard=None, path=None, assets=None,
                      render=True, scene_bytes=0, transform=None, progress=None):
    if path is not None:
        source = open_source(path)
        clipboard = source.copy(source.select())
    elif clipboard is None:
        clipboard = session.copy(selection)
    if transform is not None:
        clipboard = clipboard.transformed(**transform)
    if progress:
        progress("Clipboard", 1, 2 if render else 1)
    geometry = build_geometry(clipboard.render_source(), assets) if render else None
    if geometry is not None and scene_bytes + geometry["geometry_bytes"] > MAX_GEOMETRY_BYTES:
        raise ValueError("Scene and placement exceed 192 MiB; select a smaller region")
    return clipboard, geometry


def prepare_placement(session, placement, *, assets=None, include_entities=True, section_bytes, progress=None):
    reason = placement.reason(session)
    if reason:
        raise ValueError(reason)
    change = session.paste(placement.clipboard, placement.position, take=placement.take,
                           include_air=placement.include_air)
    prepared = prepare_sections(session, change, previous=(session, None),
                                include_entities=include_entities, previous_entities=include_entities)
    data = build_sections(**prepared, assets=assets, progress=progress)
    replacement_sizes(data, section_bytes)
    return change, data
