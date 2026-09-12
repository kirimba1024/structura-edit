import io
import sqlite3
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, replace
from numbers import Integral
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Dict, Optional

from .object_search import ObjectSearch
from .task_protocol import ProgressCallback


RECIPE_OUTPUT_LIMIT = 16_000


class _Output(io.StringIO):
    def write(self, text):
        length = len(text)
        retained = self.getvalue() + text[-RECIPE_OUTPUT_LIMIT:]
        self.seek(0)
        self.truncate()
        super().write(retained[-RECIPE_OUTPUT_LIMIT:])
        return length


@dataclass(frozen=True)
class TaskContext:
    progress: Optional[ProgressCallback] = None
    object_search: Optional[ObjectSearch] = None
    scratch_dir: Optional[str] = None


@dataclass(frozen=True)
class Task:
    execute: Callable[[Dict[str, Any], TaskContext], Any]
    message: str
    protected: bool = False
    resources: bool = False
    replaces_document: bool = False


def _open(args, context):
    from .source_loading import open_with_version_request

    return open_with_version_request(**args)


def _world(args, context):
    from .height_slice import HeightSlice
    from .preview import build_sections
    from .sections import prepare_sections
    from .source_loading import open_source

    options = {key: args[key] for key in ("path", "center", "dimension", "radius", "vertical_radius", "include_entities")}
    session = open_source(**options, world_changes=args.get("world_changes"))
    height = args.get("height", HeightSlice())
    rendered = build_sections(**prepare_sections(session, height=height), assets=args["assets"], progress=context.progress)
    return session, dict(rendered, height=height)


def _save(args, context):
    args["session"].save(args["path"], force=args.get("force", False))
    return args["session"]


def _apply(args, context):
    args["session"].apply(args["change"])
    return args["session"]


def _history(args, context):
    session, index = args["session"], args["index"]
    if isinstance(index, bool) or not isinstance(index, Integral) or not 0 <= index <= len(session.history.entries):
        raise ValueError("Invalid history position")
    total = abs(index - session.history.cursor)
    step = session.undo if index < session.history.cursor else session.redo
    while session.history.cursor != index:
        step()
        if context.progress:
            context.progress("History", total - abs(index - session.history.cursor), total)
    return session


def _render(args, context):
    from .preview import build_sections

    return build_sections(**args, progress=context.progress)


def _render_preview(args, context):
    from .preview import build_sections

    request = args["request"]
    data = build_sections(**request.geometry_args(args["previous"]), progress=context.progress)
    return request.state, data


def _overview_build(args, context):
    from .overview_build import build_overview

    return build_overview(**args, progress=context.progress)


def _overview_open(args, context):
    from .overview_cache import open_snapshot

    return open_snapshot(args["path"])


def _overview_read(args, context):
    from .overview_batches import read_batches

    return read_batches(args["path"], args["keys"])


def _overview_select(args, context):
    from .overview_batches import select_batches

    return select_batches(args['path'], args['target'])


def _overview_surface(args, context):
    from .overview_store import surface_destination

    return surface_destination(args["path"], args["position"])


def _export_review(args, context):
    from .selection_export import export_losses

    return export_losses(args["session"], args["selection"], args["path"])


def _export(args, context):
    return args["session"].export_selection(args["selection"], args["path"])


def _map(args, context):
    from .map_cache import store_maps
    from .map_images import build_source_maps

    images = build_source_maps(args["source"], args["assets"], progress=context.progress)
    atlas = args.get("atlas")
    if atlas is not None:
        try:
            images, atlas = store_maps(atlas, images)
        except (OSError, ValueError, sqlite3.Error) as error:
            return images, None, f"Map cache unavailable: {error}"
    return images, atlas, ""


def _objects(args, context):
    from .object_edits import prepare_object_change

    return prepare_object_change(**args)


def _object_search(args, context):
    from .object_search import ObjectSearch

    search = context.object_search if context.object_search is not None else ObjectSearch()
    query = args["query"] if "query" in args else dict(text=args['text'], kind=args['category'], selection=args['selection'], offset=args['offset'])
    return search.find(args["session"], **query)


def _nbt_targets(args, context):
    from .nbt_batch import collect_nbt_targets

    return collect_nbt_targets(args['session'], search=context.object_search, **args['query'])


def _nbt_batch(args, context):
    from .nbt_batch import replace_nbt_values

    return replace_nbt_values(args['session'], args['targets'], args['path'], args['text'], progress=context.progress)


def _operation(args, context):
    from .commands import COMMANDS

    return COMMANDS[args["mode"]].execute(args["session"], args["selection"], **args["values"])


def _clipboard(args, context):
    from .placement_jobs import prepare_clipboard

    return prepare_clipboard(**args, progress=context.progress)


def _placement(args, context):
    from .placement_jobs import prepare_placement

    return prepare_placement(**args, progress=context.progress)


def _placement_plan(args, context):
    return args["placement"].plan(args["session"])


def _placement_area(args, context):
    from .world_placement import load_placement_area

    return load_placement_area(args["session"], args["placement"])


def _repeat(args, context):
    from .clipboard_placement import plan_stack

    options = {key: value for key, value in args.items() if key not in ("session", "height")}
    return plan_stack(args["session"], **options)


def _recipe(args, context):
    session = args["session"]
    branch = session.fork()
    output = _Output()
    namespace = {"edit": branch, "selection": args["selection"]}
    with TemporaryDirectory(prefix="recipe-", dir=context.scratch_dir) as directory, redirect_stdout(output), redirect_stderr(output):
        branch.history.persistent = True
        branch.history.path = str(Path(directory) / "history.sqlite")
        exec(compile(args["code"], "<structura recipe>", "exec"), namespace)
    return session.diff(branch), output.getvalue()


def _paint(args, context):
    from .paint import paint_stroke

    return paint_stroke(**{key: value for key, value in args.items() if key != "height"})


def _planar(args, context):
    from .planar import planar_selection

    return planar_selection(args["session"], args["start"], args["normal"])


def _connected(args, context):
    from .connected import connected_selection

    return connected_selection(args["session"], args["start"], criterion=args["criterion"], progress=context.progress)


def _fragment_save(args, context):
    from .fragments import save_fragment

    return save_fragment(**args)


def _fragment_list(args, context):
    from .fragments import list_fragments

    return list_fragments()


def _fragment_load(args, context):
    from .fragments import load_fragment

    return load_fragment(args["path"])


def _draft_save(args, context):
    from .drafts import save_draft

    return save_draft(args["session"])


def _draft_list(args, context):
    from .drafts import list_drafts

    return list_drafts()


def _draft_restore(args, context):
    from .drafts import restore_draft

    return restore_draft(args["path"])


def _catalog(args, context):
    from .material_catalog import material_catalog

    return material_catalog(args.get("assets"))


def _item_icons(args, context):
    from .item_icons import render_icons

    return render_icons(args["ids"], args["assets"])


def _changes(args, context):
    from .changes_view import unsaved_changes

    return unsaved_changes(args["session"])


def _backups(args, context):
    from structura_core.world_staging import list_backups, restore_backup, verify_backup

    if args.get("restore"):
        return {"restored": restore_backup(args["world"], args["backup"], progress=context.progress, expected=args.get("expected"))}
    if args.get("verify"):
        if args.get("world"):
            from structura_core.world_backup import inspect_restore

            return inspect_restore(args["world"], args["backup"], progress=context.progress)
        return {"verified": verify_backup(args["backup"], progress=context.progress)}
    return {"backups": list_backups(args["world"])}


def _conflicts(args, context):
    from structura_core.world_write import world_conflicts

    session = args["session"]
    patch = {position: tuple((cell.state, cell.data.nbt if cell.keep_nbt and cell.data else None) for cell in pair)
             for position, pair in session.world_changes.patch.items()}
    return world_conflicts(session.path, patch)


TASKS = {
    "overview_build": Task(_overview_build, "Preparing world overview…", resources=True),
    "overview_open": Task(_overview_open, "Opening world overview…"),
    "overview_read": Task(_overview_read, "Refining view…"),
    "overview_select": Task(_overview_select, "Choosing detail…"),
    "overview_surface": Task(_overview_surface, "Preparing destination…"),
    "open": Task(_open, "Opening…", replaces_document=True),
    "world": Task(_world, "Loading world…", resources=True, replaces_document=True),
    "save": Task(_save, "Saving…", protected=True),
    "apply": Task(_apply, "Applying…", protected=True),
    "history": Task(_history, "Restoring history…", protected=True),
    "render": Task(_render, "Building preview…", resources=True),
    "render_preview": Task(_render_preview, "Building preview…", resources=True),
    "export_review": Task(_export_review, "Checking export…"),
    "export": Task(_export, "Exporting…", protected=True),
    "map": Task(_map, "", resources=True),
    "objects": Task(_objects, "Preparing object data…"),
    "object_search": Task(_object_search, "Finding objects…"),
    "nbt_targets": Task(_nbt_targets, "Collecting all search results…"),
    "nbt_batch": Task(_nbt_batch, "Preparing object data changes…"),
    "operation": Task(_operation, "Preparing change…"),
    "paint": Task(_paint, "Preparing paint stroke…"),
    "planar": Task(_planar, "Selecting a flat face…"),
    "connected": Task(_connected, "Selecting connected blocks…"),
    "fragment_save": Task(_fragment_save, "Saving fragment…", protected=True),
    "fragment_list": Task(_fragment_list, "Reading fragments…"),
    "fragment_load": Task(_fragment_load, "Loading fragment…"),
    "draft_save": Task(_draft_save, "Saving local draft…", protected=True),
    "draft_list": Task(_draft_list, "Reading local drafts…"),
    "draft_restore": Task(_draft_restore, "Recovering local draft…", replaces_document=True),
    "catalog": Task(_catalog, "Reading material catalog…"),
    "item_icons": Task(_item_icons, "", resources=True),
    "changes": Task(_changes, "Collecting unsaved changes…"),
    "backups": Task(_backups, "Reading backups…"),
    "restore_backup": Task(_backups, "Restoring backup…", protected=True),
    "conflicts": Task(_conflicts, "Checking the world for conflicts…"),
    "clipboard": Task(_clipboard, "Preparing clipboard…", resources=True),
    "placement": Task(_placement, "Preparing placement…", resources=True),
    "placement_plan": Task(_placement_plan, "Checking placement rule…"),
    "placement_area": Task(_placement_area, "Loading the destination…", replaces_document=True),
    "repeat": Task(_repeat, "Preparing copies…"),
    "recipe": Task(_recipe, "Running recipe…"),
}


def task_definition(kind):
    try:
        return TASKS[kind]
    except KeyError:
        raise ValueError(f"Unknown task: {kind}") from None


def execute(kind, args, progress=None, *, object_search=None, scratch_dir=None):
    task = task_definition(kind)
    if task.resources:
        from .resources import refresh_resources

        refresh_resources(args.get("assets"))
    result = task.execute(args, TaskContext(progress, object_search, scratch_dir))
    if kind in ("operation", "recipe", "repeat", "placement_plan", "paint", "nbt_batch"):
        from .change_report import report_change

        if kind == "recipe":
            change = result[0]
        elif kind in ("repeat", "placement_plan", "nbt_batch"):
            change = result.change
        else:
            change = result
        change = replace(change, report=report_change(args["session"], change, args.get("height")))
        if kind == "recipe":
            return change, result[1]
        if kind in ("repeat", "placement_plan", "nbt_batch"):
            return replace(result, change=change)
        return change
    return result
