import argparse
import multiprocessing
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description="Structura Edit desktop workbench")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("path", nargs="?")
    source.add_argument("--world", help="Java world folder containing level.dat")
    parser.add_argument("--assets", help="Minecraft client JAR or extracted assets/minecraft folder")
    parser.add_argument("--region", help="Named Litematic region to view")
    parser.add_argument("--palette-index", type=int, default=0, help="Java NBT palette variant")
    parser.add_argument("--source-data-version", type=int, help="Source Java DataVersion for Sponge v1 without version metadata")
    from .loading import MAX_RADIUS

    parser.add_argument("--world-radius", type=int, choices=range(MAX_RADIUS + 1), help="Override view distance in chunks; use 1 for quick development runs")
    args = parser.parse_args(argv)
    try:
        from .ui import launch
    except ModuleNotFoundError as error:
        if error.name not in ("PySide6", "pyvista", "pyvistaqt", "vtk", "vtkmodules", "qtpy"):
            raise
        parser.exit(2, f"Install structura-edit[gui] to open the workbench.\n{error}\n")
    if args.world and args.region:
        parser.error("--region applies to Litematic files; choose a world dimension in View")
    if args.world and (args.palette_index or args.source_data_version is not None):
        parser.error("Palette and source version options apply to schematic files")
    return launch(args.path, assets=args.assets, region=args.region, palette_index=args.palette_index,
                  source_data_version=args.source_data_version, world=args.world, world_radius=args.world_radius)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
