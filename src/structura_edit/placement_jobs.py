from .loading import MAX_GEOMETRY_BYTES, replacement_sizes
from .preview import build_geometry, build_sections
from .sections import prepare_sections
from .source_loading import SourceVersionRequired, open_with_version_request
from .height_slice import HeightSlice


def prepare_clipboard(session, *, selection=None, clipboard=None, path=None, source_options=None, assets=None,
                      render=True, scene_bytes=0, transform=None, progress=None):
    if path is not None:
        source = open_with_version_request(path=path, **(source_options or {}))
        if isinstance(source, SourceVersionRequired):
            return source
        clipboard = source.copy(source.select())
    elif clipboard is None:
        clipboard = session.copy(selection)
    if transform is not None:
        clipboard = clipboard.transformed(**transform)
    if progress:
        progress("Clipboard", 1, 2 if render else 1)
    geometry = build_geometry(clipboard.render_source(include_entities=False), assets) if render else None
    if render and clipboard.entities:
        source = clipboard.render_source(include_blocks=False)
        source.size = (1, 1, 1)
        geometry["entities"] = build_geometry(source, assets)
        geometry["geometry_bytes"] += geometry["entities"]["geometry_bytes"]
    if geometry is not None and scene_bytes + geometry["geometry_bytes"] > MAX_GEOMETRY_BYTES:
        raise ValueError("Scene and placement exceed 192 MiB; select a smaller region")
    return clipboard, geometry


def prepare_placement(session, placement, *, assets=None, include_entities=True, section_bytes, progress=None,
                      height=HeightSlice(), retained_bytes=0):
    reason = placement.reason(session)
    if reason:
        raise ValueError(reason)
    change = session.paste(placement.clipboard, placement.position, take=placement.take,
                           include_air=placement.include_air, destination=placement.destination,
                           include_blocks=placement.include_blocks, include_entities=placement.include_entities)
    prepared = prepare_sections(session, change, previous=(session, None),
                                include_entities=include_entities, previous_entities=include_entities,
                                height=height, previous_height=height)
    data = build_sections(**prepared, assets=assets, progress=progress)
    sizes = replacement_sizes(data, section_bytes)
    if sum(sizes.values()) + retained_bytes > MAX_GEOMETRY_BYTES:
        raise ValueError("Scene and next placement exceed 192 MiB; reduce the selection or turn off Keep placing")
    return change, data
