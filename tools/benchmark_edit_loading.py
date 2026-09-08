import argparse
import cProfile
import gc
import json
import pickle
import sys
from pathlib import Path
from time import perf_counter

from structura_edit import EditSession
from structura_edit.map_images import build_maps
from structura_edit.preview import build_preview, build_sections
from structura_edit.sections import prepare_sections

try:
    import resource
except ImportError:
    resource = None


def measure(open_session, assets, *, sections=False):
    start = perf_counter()
    session = open_session()
    opened = perf_counter()
    geometry = build_preview(session, assets=assets)
    rendered = perf_counter()
    maps = build_maps(session, assets=assets)
    mapped = perf_counter()
    payload = pickle.dumps((session, geometry), protocol=pickle.HIGHEST_PROTOCOL)
    packed = perf_counter()
    pickle.loads(payload)
    unpacked = perf_counter()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource else None
    result = dict(size=session.size, blocks=len(session._document.source.present),
                read_seconds=opened - start, mesh_seconds=rendered - opened,
                map_seconds=mapped - rendered, serialize_seconds=packed - mapped,
                deserialize_seconds=unpacked - packed, payload_mib=len(payload) / 2**20,
                geometry_mib=geometry["geometry_bytes"] / 2**20,
                maps_mib=sum(image.nbytes for image in maps.values()) / 2**20,
                peak_rss_mib=rss / (2**20 if sys.platform == "darwin" else 1024) if rss is not None else None)
    if sections:
        edit = EditSession.from_structure(session._document.source)
        start = perf_counter()
        full = build_sections(**prepare_sections(edit), assets=assets)
        result["sectioned_full_seconds"] = perf_counter() - start
        result["section_count"] = len(full["sections"])
        result["sectioned_geometry_mib"] = full["geometry_bytes"] / 2**20
        position = tuple(min(8, length - 1) for length in edit.size)
        target = "minecraft:stone" if edit.state_at(position) == "minecraft:glass" else "minecraft:glass"
        change = edit.set_block(position, target)
        start = perf_counter()
        build_preview(edit, change, assets=assets)
        result["full_edit_seconds"] = perf_counter() - start
        start = perf_counter()
        request = prepare_sections(edit, change, previous=(edit.fork(), None))
        prepared = perf_counter()
        update = build_sections(**request, assets=assets)
        result.update(edit_prepare_seconds=prepared - start, edit_mesh_seconds=perf_counter() - prepared,
                      edit_sections=len(update["sections"]), edit_request_kib=len(pickle.dumps(request)) / 1024,
                      edit_geometry_kib=update["geometry_bytes"] / 1024)
    return result


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--world")
    source.add_argument("--schematic")
    parser.add_argument("--radii", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--vertical", type=int, default=32)
    parser.add_argument("--assets")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--sections", action="store_true", help="Compare complete geometry with a one-block section update")
    args = parser.parse_args()
    profile = cProfile.Profile() if args.profile else None
    if profile:
        profile.enable()
    results = []
    if args.world:
        from structura_core.world import JavaWorld
        from structura_edit.world_view import WorldView

        world = JavaWorld(args.world)
        for radius in args.radii:
            gc.collect()
            result = measure(lambda: WorldView(world, world.read_region(
                radius=radius, vertical_radius=args.vertical, dimension=world.start_dimension)), args.assets, sections=args.sections)
            result.update(radius=radius, vertical_radius=args.vertical)
            results.append(result)
            print(json.dumps(result), flush=True)
    else:
        result = measure(lambda: EditSession.open(args.schematic), args.assets, sections=args.sections)
        results.append(result)
        print(json.dumps(result), flush=True)
    if profile:
        profile.disable()
        profile.dump_stats(args.profile)
    args.output.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
