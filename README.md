# Structura Edit

Edit Minecraft schematics from Python or a compact desktop workbench. The same
API prepares changes, previews them, applies them and keeps undo/redo history.
The current foundation also views saved Java worlds, refreshes around the camera
and displays entities through Structura Render.

This is a development release. NBT/SNBT and Sponge v2/v3 are editable. Litematic,
Bedrock `.mcstructure`, Sponge v1 and worlds support viewing, selection and export. Writing changes
back to a world is a later stage.

For the small prototype, start with **Explore demo** on the welcome screen:
fly, select a block, preview Fill, apply, undo and save. The
[module map](docs/structura-edit-architecture.md)
defines the current scope and review sequence.

## Install

From the Structura workspace, use Python 3.9–3.13 and a virtual environment:

```bash
git clone --recurse-submodules https://github.com/kirimba1024/structura.git
cd structura
python -m venv .venv-edit
source .venv-edit/bin/activate
python -m pip install -e 'libs/structura-core[world]' -e 'libs/structura-render[hero]' -e 'libs/structura-edit[gui,world]'
structura-edit
```

This repository is the workspace's `libs/structura-edit` submodule. Development
uses the core/render commits pinned by that workspace; the editor's preview API
needs the current render checkout, including changes after render 0.8.1.

On Windows activate with `.venv-edit\Scripts\activate`. Omit `world` for schematic
editing and `gui` for headless use. The base import loads neither Qt nor VTK.
The desktop uses native Qt Widgets, PyVistaQt and VTK, with no server. Their
installation is substantially larger than this library's own code. Current GUI
verification is on macOS; Windows/Linux still need platform checks.

```bash
structura-edit house.nbt
structura-edit build.schem --assets /path/to/client.jar
structura-edit build.litematic --region Main
structura-edit --world /path/to/saves/MyWorld
structura-edit /path/to/saves/MyWorld
```

Minecraft resources are local. Choose a client JAR through View → Minecraft
resources, or pass an extracted `assets/minecraft` folder to `--assets`. Java code
in the JAR is never executed. Render also discovers local Minecraft resources;
when none are found, blocks use colours and supported
entities use untextured models. Player skins are not fetched from the network.

## Navigation and selection

The editor has one interaction model: a free perspective camera with permanent
noclip, and region selection. There is no toolbar, active tool, orbit mode or
projection switch for the main camera. Operations open from the Selection menu;
parameter panels stay hidden until requested. One native inspector opens beside
the scene at a time, inside the main window. Finishing a background preview
updates its result without opening a panel or moving keyboard focus.

| Input | Action |
|---|---|
| Hold WASD or arrows | Continuous flight; forward follows the view |
| E / Space, Q | Up, down |
| Shift while flying | Fly faster |
| Hold right mouse and move | Look from the camera position; release restores the cursor |
| Shift+` or View → Fly / freelook | Look without holding a button; move one finger on a trackpad |
| Esc or click while in freelook | Keep the camera position, release the cursor; the exit click does not select |
| Left click | Select one block as a 1×1×1 region; a plain click starts a new selection |
| Hold Shift after selecting | Preview a cuboid from the first block to the block under the cursor |
| Left click while holding Shift | Commit the displayed region, including both endpoint blocks |
| Release Shift before clicking | Cancel the temporary cuboid and retain the committed selection |
| − / + (also = without Shift) | Halve / double flight speed |
| Mouse wheel while looking | Adjust flight speed; trackpad scrolling does not change it |
| F | Frame the scene |
| M in the viewport | Expand or close the map; Escape also closes it |
| Enter in the viewport | Apply the ready preview |
| Escape | Release mouse look, otherwise discard a preview or clear the selection |
| F5 | Refresh the current world around the camera |

Movement starts with a key press and continues on every frame until release;
it does not depend on keyboard repeat. Opposite directions cancel, aliases do
not add speed, and diagonal flight has the same speed as straight flight.
Focus loss, app switching and modal dialogs clear held input. Text fields
retain normal keyboard input. Mouse look keeps the camera position and field
of view fixed and samples captured cursor movement once per frame. Releasing
RMB or pressing Escape restores the cursor; app switching releases it without
moving it into another app. Flight has no collision checks or post-release drift.
The initial speed is 24 blocks/s, or 96 with Shift. Base speed is limited to
0.5–256 blocks/s. These tunables live together in `navigation.py`. Freelook has
the same movement and focus rules as RMB look; Shift boosts without extending
the selection. No trackpad button or scroll gesture is required to fly.

The same map canvas works as a compact 3×2 minimap and a large map on **M**.
Click a projection to enlarge it; the other five become small square icons. The
**Six views** header restores the grid. Drag to pan, use the wheel to zoom around
the cursor, and press **F** to recenter on the camera. On a trackpad, scroll with
two fingers to pan and pinch to zoom at the cursor. Each projection remembers
its own center and zoom. M/Escape closes the map and restores viewport focus;
typing M in an inspector remains normal text input. Double-click a settled
projection to move the camera in that plane and return to the scene.

The map uses sharp pixels, square frames, small labels and a light palette.
Images preserve their proportions in every size, including compact icons.
The scene has a flat sky background; visual values live in `appearance.py`.
The minimap header
collapses it to one row; its M button expands it. Enlarging and switching views
reuse the current images. Large views preserve block proportions. Map gestures
never select blocks or fly the camera underneath the map.

Hover uses a light, thin block outline. A click leaves a stronger mint outline
with a faint fill. Shift shows a dashed temporary cuboid while retaining the
committed selection; moving off the scene or releasing Shift removes the
temporary cuboid. Small XYZ axes show orientation. The pointer is a crosshair;
RMB look and freelook show a small central reticle. These overlays do not take focus.

Preview shows only changed blocks as translucent geometry; erased blocks have
a faint red wireframe. Unchanged surroundings stay opaque. Neighbor-dependent
shapes use the complete voxel state in both layers. Apply restores normal
opacity and removes deletion ghosts without rebuilding the ready preview.
Enter applies, Escape discards. A four-pixel progress bar appears in the status
bar after 300 ms for longer tasks: real section/projection counts when available,
otherwise busy mode. Cancel stays beside it and never moves keyboard focus.

Fill, Replace, Erase, Move blocks and Duplicate use the same region commands as
the Python API. Move and Duplicate take integer X/Y/Z offsets and use the regular
Preview → Apply workflow. A successful Move also moves the selection to its
destination. Coordinate entry and material counts are available in Selection;
Python recipes are in Edit. Other shape operations remain available from Python.
Coordinates and move offsets commit when Enter is pressed or the field loses
focus, so typing a multi-digit value does not apply intermediate digits.

## Worlds

Choose File → Open world once, or use `--world`. The first view is near the saved
player position, falling back to spawn. **F5 / View → Refresh world** rereads the same world around the camera.
View → World radius and location contains dimensions, vertical range and
Restore Defaults. Refresh preserves the world-space camera and any
selection that still fits the loaded region.

The default window spans 3 × 3 chunks and a section-aligned vertical radius of
32 blocks. Use the compact **Refresh · F5** button or F5 to reload that radius
around the current camera. Flying never checks region boundaries, starts reads
or schedules geometry/map rebuilds. Disk reads and geometry building run in a
worker process while the old scene remains usable. Repeated explicit requests
retain only the latest queued request. World requests take priority over pending
minimap work. Open and F5 rebuild the bounded window as independent 16³ sections.
Schematic preview, discard, undo and redo replace only affected sections and
boundary neighbors. Apply reuses the completed preview. Unchanged actors stay
on the GPU; entities form a separate static layer. Previous 3D world windows are
released; the 2D map accumulates visited areas as described below. World loading
remains manual.

Refresh and world settings are available only while a world is open. F5 in a
schematic does not reopen an earlier world or discard schematic changes.

Entities come from chunk NBT, entity region files, `level.dat` and `playerdata`.
Their saved positions and NBT feed render's existing models, including sheep,
pigs and players. View → Show entities controls their visibility. This displays
saved state; it does not simulate mobs or read Minecraft's unsaved memory.

The reader targets Java 1.13+ Anvil palettes. Fixtures cover dense and padded
block packing, negative coordinates and external entity chunks; a real Java
1.21 world was also checked. Absent chunks are tracked separately and prevent
export of an incomplete selection. The editor caps world windows at 2 million
cells before reading and 750,000 stored blocks while reading. Schematic previews
are limited to 8 million cells before allocating dense voxel arrays. Geometry
over 192 MiB is rejected after building, before transfer to the GUI; this is
not a total process-memory limit. The GUI also checks the combined geometry budget
of retained and replacement sections before creating actors. No world file is
opened for writing by this stage.

The large map accumulates images from explicit world loads/F5, including when
the minimap is collapsed. Cached terrain is dimmer; a dashed box marks the
currently loaded volume. Dragging reads cached images in a background thread,
never chunks. Camera movement and Refresh do not recenter or rescale the map.
Unknown chunks remain unknown, rather than becoming air.

The cache is `structura-edit/atlas-v1.sqlite` in the OS cache directory, outside
the save (`~/Library/Caches/structura-edit` on macOS). It uses transactional PNG
tiles of 128×128 blocks at one pixel per block. Up to 192 visible tiles use about
12 MiB of RGBA images; image transfer briefly needs additional copies. Disk
eviction keeps at most 4096 tiles and 48 MiB of payload/metadata, with a 64 MiB
SQLite page ceiling. Zoom-out is bounded by the visible-tile budget; there is no
LOD pyramid or scan of the entire world.

World, dimension, resource revision and projection depth are separate cache
keys. Large world views label their depth interval: a top view covers its Y
slice, a side view its X/Z slice. Different depths never get stitched together.
On an explicit refresh, changed `.mca`/`.mcc` signatures invalidate dependent
tiles conservatively. A source change during reading prevents caching that
snapshot. Damaged tiles are discarded; unavailable cache storage still allows
the current map to work. Cached areas reflect their last explicit refresh.

Measurements and current design are recorded in the
[section rendering audit](docs/archive/structura-edit/structura-edit-sections-2026-09-08.md).
To measure another save or schematic without starting the GUI:

```bash
python libs/structura-edit/tools/benchmark_edit_loading.py --world /path/to/saves/MyWorld --radii 1 2 3 --output /tmp/loading.json
python libs/structura-edit/tools/benchmark_edit_loading.py --schematic example.nbt --output /tmp/schematic.json
python libs/structura-edit/tools/benchmark_edit_loading.py --world /path/to/saves/MyWorld --radii 1 2 3 --sections --output /tmp/sections.json
```

Run from the repository root. `--profile /tmp/loading.prof` adds a cProfile
record; compare timings without profiling. `--sections` compares full geometry
with a one-block edit, including section preparation and request size. Peak RSS is available on macOS/Linux
and is a cumulative high-water mark for the benchmark process, excluding the GUI.

```python
from structura_core.world import JavaWorld

world = JavaWorld("/path/to/saves/MyWorld")
region = world.read_region((0, 80, 0), radius=1, vertical_radius=32)
structure = region.structure
print(region.loaded, region.missing, len(structure.entities))
```

## Python editing

```python
from structura_edit import EditSession

edit = EditSession.open("house.nbt")
selection = edit.select()
change = edit.replace(selection, "minecraft:oak_planks", "minecraft:spruce_planks")
preview = edit.snapshot(change)
edit.apply(change)
edit.undo()
edit.redo()
edit.save("house-edited.nbt")
```

`open_source(path)` is the common entry for a schematic, world folder or
`level.dat`; all return the same session interface with local block coordinates,
`size` and world `origin`. File decoding uses core. Native Sponge metadata is
retained separately for lossless saves. Bedrock reading needs
`structura-core[bedrock]`; its current core translation covers blocks and reports
conversion losses. Sponge v1 without DataVersion requires an explicit
`source_data_version` through the Python API, or conversion with core first.

```python
from structura_edit import open_source

edit = open_source("build.litematic", region="Main")
world = open_source("/path/to/saves/MyWorld", center=(0, 80, 0), radius=1)
```

Bounds are half-open: `edit.select(((0, 0, 0), (16, 8, 16)))` includes x/z 0–15,
y 0–7. Fill, replace, erase, move, duplicate and basic shapes produce a ChangeSet.
A change belongs to one document revision; later edits invalidate old previews.
`transaction()` groups changes into one undo step and rolls back exceptions.
The default operation budget is 500,000 changed cells. History keeps every
applied step of the open document in a temporary SQLite journal, with an
independent 500,000-cell RAM cache. Evicting cached changes never removes Undo.
Save preserves the history; a new edit after Undo discards the Redo branch.
Edit → History lists operations and restores any retained step. Apply and
history reads run outside the GUI thread. A journal write failure leaves the
document unchanged. Closing the document ends its history; journals are cleaned
up at process exit and do not provide recovery after restarting the application.

Python `copy(selection)` creates a detached clipboard; `paste(clipboard, lower,
take=False, include_air=False)` prepares one change. Take checks that its source
revision is still current and removes source blocks only at Apply. Copying
between documents preserves block states, block-entity NBT and extra block
record fields; it does not translate Minecraft versions or copy entities/biomes.
The destination must fit inside the document. Cursor placement and its GUI
Copy/Take/Paste actions are still being implemented; Move/Duplicate currently
use the offset panel described above.

Selection menus expose the implemented operations and a compact material
histogram. The Python panel supplies a disposable `edit` branch and `selection`.
Preview recipe runs ordinary local Python with filesystem access; only explicit
execution runs code. Exceptions, reset of operation settings and cancellation
leave the parent document unchanged.

Untouched records, entities and alternative palettes are retained. A changed
block ID removes incompatible block-entity NBT; undo restores it. Moving blocks
moves their block-entity data; entities and biomes stay in place. Replace can
retain compatible vanilla family properties, with explicit target properties
winning. This is not full game-version registry validation.

Missing schematic cells remain missing unless filled. Erase writes explicit
air. Sponge saves retain their native version and metadata. Saves use core's
atomic writer; cross-format conversion and edited Litematic saving are separate.

## Development

```bash
python -m pip install -e 'libs/structura-edit[test]'
python -m pytest libs/structura-edit/tests
python libs/structura-edit/tests/smoke_gui.py libs/structura-render/src/structura_render/data/examples/demo.nbt
python libs/structura-edit/tests/smoke_world.py /path/to/saves/MyWorld
python libs/structura-edit/tests/smoke_sections.py
python libs/structura-edit/tests/smoke_map.py libs/structura-render/src/structura_render/data/examples/demo.nbt
python libs/structura-edit/tests/smoke_map.py /path/to/saves/MyWorld
```

GUI smoke tests use a hidden window and produce JSON measurements. The schematic
smoke also saves its own widget and VTK framebuffer images for layout checks. World tests read the selected save; schematic tests save to a
temporary directory. Project rules are in the workspace `AGENTS.md`; the
[roadmap](docs/structura-edit-roadmap.md) separates the foundation from later
world writing, clipboard transformations, brushes and terrain operations.

The [module map](docs/structura-edit-architecture.md) describes ownership and
data flow. Historical reports are in the [archive](docs/archive/structura-edit/README.md),
excluded from ordinary search. Read them only when investigating an earlier decision.
