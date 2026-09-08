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
    args = parser.parse_args(argv)
    try:
        from .ui import launch
    except ImportError as error:
        parser.exit(2, f"Install structura-edit[gui] to open the workbench.\n{error}\n")
    if args.world and args.region:
        parser.error("--region applies to Litematic files; choose a world dimension in View")
    return launch(args.path, assets=args.assets, region=args.region, world=args.world)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
