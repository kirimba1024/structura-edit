# Structura Edit

Edit Minecraft schematics from Python or a compact desktop workbench. The same
API prepares changes, previews them, applies them and keeps undo/redo history.
The workbench also edits bounded snapshots of Java worlds, refreshes around the
camera and displays entities through Structura Render.

This is a development release. NBT/SNBT and Sponge v2/v3 are editable. Legacy
`.schematic` opens as an editable Java structure and saves as NBT/SNBT. Litematic,
Bedrock `.mcstructure` and Sponge v1 support viewing, selection and export.
Java 1.18+ worlds support local block/entity edits and explicit Save world; older Java
worlds remain available for viewing and export.

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
uses the core/render commits pinned by that workspace: world writes need the
current core checkout, and previews need render changes after 0.8.1.

On Windows activate with `.venv-edit\Scripts\activate`. The `gui` extra includes
core's world, legacy and Bedrock readers so Open supports every core input format.
Omit `gui` for headless use and choose core's optional readers as needed.
The base import loads neither Qt nor VTK.
The desktop uses Qt Widgets, PyVistaQt and VTK, with no server. Their
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

**Open** on the welcome screen and File → Open use the same picker for schematic
files, Java world folders and `level.dat`. Files stay visible while browsing folders.
Entering a world folder selects its `level.dat` so Open remains available.
The file filter comes from core's supported suffixes: `.nbt`, `.snbt`, `.schem`,
`.schematic`, `.litematic` and `.mcstructure`. Legacy input is normalized to
core's default Java version and its original file is never overwritten by Save.
Open and Import of Sponge v1 without version metadata prompt for the source Java DataVersion;
the command line accepts `--source-data-version`. `--palette-index` selects a
Java NBT palette variant, and `--region` selects a named Litematic region.

## Navigation and selection

The editor has one interaction model: a free perspective camera with permanent
noclip, and region selection. There is no toolbar, active tool, orbit mode or
projection switch for the main camera. Operations open from the Selection menu;
parameter panels stay hidden until requested. One fixed inspector opens on the
right; it cannot float, move sides or change width. Finishing a background preview
updates its result without opening a panel or moving keyboard focus.

| Input | Action |
|---|---|
| Hold WASD or arrows | Continuous flight; forward follows the view |
| E / Space, Q | Up, down |
| Shift while flying | Fly faster |
| Move the mouse or one finger after loading | Free look starts automatically; no button is needed |
| Hold right mouse and move | Look from the camera position; release restores the cursor |
| Shift+` or View → Fly / freelook | Look without holding a button; move one finger on a trackpad |
| Esc while in freelook | Keep the camera position and release the cursor |
| Left click | Select an entity or one block; freelook selects at the crosshair and stays active |
| Hold Shift after selecting | Preview a cuboid from the first block to the block under the cursor |
| Left click while holding Shift | Commit the displayed region, including both endpoint blocks |
| Release Shift before clicking | Cancel the temporary cuboid and retain the committed selection |
| − / + (also = without Shift) | Halve / double flight speed |
| Mouse wheel while looking | Adjust flight speed; trackpad scrolling does not change it |
| I / middle click in the viewport | Pick the exact block state under the pointer; in freelook, use the crosshair |
| F | Frame the scene |
| M in the viewport | Expand or close the map; Escape also closes it |
| Enter in the viewport | Apply the ready preview |
| Escape | Release mouse look, otherwise discard a preview or clear the selection |
| F5 | Refresh the current world around the camera |

Pick material sets the shared **To** value for Fill/Replace and other material
operations without changing blocks, the selection or flight. The status line
shows the sampled state; block-entity contents are not copied. Picking is disabled
during preview, placement and background work. `I` also works on the Russian
keyboard layout; it remains normal text input inside fields.

**Selection → Materials** opens a searchable list of loaded block states, with
the last 12 picked or used materials first. Counts describe the loaded area.
The **From…**, **To…** and **Only material…** field labels open the same picker
for that field. Type to filter, use arrows and Enter, or double-click a row;
Escape returns to the field unchanged. Other block IDs can be typed directly
into the operation fields. Recent materials last for the application session,
including document switches; no world loading or asset scanning is involved.

Movement starts with a key press and continues on every frame until release;
it does not depend on keyboard repeat. Opposite directions cancel, aliases do
not add speed, and diagonal flight has the same speed as straight flight.
Focus loss, app switching and modal dialogs clear held input. Text fields
retain normal keyboard input. Mouse look keeps the camera position and field
of view fixed and consumes accumulated mouse-move events once per frame.
On macOS, native relative mouse deltas retain fractional trackpad movement and
do not depend on the cursor reaching a screen edge. Other Qt platforms use an
edge-recentering fallback that excludes synthetic cursor movements. Escape restores
the cursor; app switching releases it without moving it into another app. Latched
freelook resumes when the viewport regains focus; explicitly pressing Escape leaves
it released. RMB release ends temporary look only. Flight has no collision checks
or post-release drift.
The initial speed is 24 blocks/s, or 96 with Shift. Base speed is limited to
0.5–256 blocks/s. These tunables live together in `navigation.py`. Freelook has
the same movement and focus rules as RMB look; Shift boosts without extending
the selection. No trackpad button or scroll gesture is required to fly.

The same map canvas works as a compact 3×2 minimap and a large map on **M**.
The camera stays in the center of every compact view. Each view starts at the
camera's block: Top looks down from its Y, Bottom up, and the four side views
look away from its X/Z. Surfaces beyond the cut remain visible; a ceiling above
the camera no longer hides the floor in Top. Moving within a block only pans
existing images; crossing a block rebuilds the affected pair of views in the background.
Click a projection to enlarge it; the other five become small square icons. The
**Six views** header restores the grid. Drag to pan, use the wheel to zoom around
the cursor, and press **F** to recenter on the camera. On a trackpad, scroll with
two fingers to pan and pinch to zoom at the cursor. In the large map, manual pan
or zoom releases that projection from camera following; F resumes following.
Returning to the compact map always centers the camera. M/Escape restores viewport focus;
typing M in an inspector remains normal text input. Double-click a settled
projection to move the camera in that plane and return to the scene.

The map uses sharp pixels, square frames, small labels and a light palette.
Images preserve their proportions in every size, including compact icons.
Large projections preserve 16×16 Minecraft textures within an eight-million-pixel
budget. Compact views use a smaller texture budget during flight. Saved map areas retain detail; distant cached tiles are reduced
to the screen scale with at most 64 MiB of decoded tile pixels. Saved and current
areas use the same world coordinates and opacity. The large map can show previously
cached areas with the same depth interval around the current snapshot.
The scene has a flat sky background; visual values live in `appearance.py`.
Controls use a shared four-pixel layout grid, flat one-pixel frames and square
buttons. The bundled [Monocraft](https://github.com/IdreesInc/Monocraft) font has
Cyrillic support and uses an integer pixel size without antialiasing. Its OFL
license and pinned source are included under `data/fonts`. `theme.py` installs
Qt Fusion; `data/editor.qss` owns the common skin, including menus, checkboxes
and file dialogs. Native window decorations remain managed by the OS.
The minimap header
collapses it to one row; its M button expands it. Enlarging and switching views
reuse the renderer, with texture detail adjusted for the available pixel budget. Large views preserve block proportions. Map gestures
never select blocks or fly the camera underneath the map.

**View → Height slice** or **All Y** in the status bar opens the height controls.
Choose All layers, Up to Y or Single layer; Y is a world coordinate. Use camera
height sets the cut to the current camera. Hidden roofs stop blocking clicks,
cut surfaces are rebuilt, and all six maps follow the same range. Entities are
shown whole when their position falls inside it. World map tiles from other
loaded areas are hidden while a slice is active. Switching heights keeps the
camera and viewport size, does not change blocks or create Undo, and preserves
the world Y on F5 and schematic expansion. Editing still uses the full selection.

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
Errors leave an **Error…** button in the status bar; it opens the full selectable
message with **Copy error**. Restart the editor after changing its Python source files.

Fill, Replace, Erase and Move blocks use the same region commands as the Python
API. Move takes integer X/Y/Z offsets and uses the regular Preview → Apply workflow.
Duplicate uses the shared clipboard placement strip. A successful Move also moves the selection to its
destination. Coordinate entry and material counts are available in Selection;
Python recipes are in Edit. Other shape operations remain available from Python.
Coordinates and move offsets commit when Enter is pressed or the field loses
focus, so typing a multi-digit value does not apply intermediate digits.
**Blocks** expands a compact texture-and-count strip. Hover an item for its block
name and full ID. Empty space is excluded from these counts; world counts cover
loaded blocks. **View → Chunk outlines** shows chunk boundaries with 2 px lines
at 35% opacity; schematic bounds remain a separate faint dashed outline.

## Clipboard placement

The strip over the bottom of the scene offers **Copy, Take, Duplicate, Paste, Repeat and Export**.
Showing selection details or placement controls does not resize the viewport.
File → Import schematic places an external file through the same clipboard path.
The ghost follows the cursor against block faces; over empty space it uses a
horizontal placement plane. Click to pin it, then drag a labelled X/Y/Z handle to move
in whole blocks. The handles keep their screen size as you zoom. Escape during a drag
restores its starting position; releasing or losing focus ends the drag without placing.
**Options…** reveals exact XYZ, Flip X/Z and Copy air. Arrows also adjust position:
left/right change X, up/down change Z, Shift+up/down change Y. WASD still flies.
**Enter / Place** commits one undo step; **Escape / Cancel** preserves the source.
Take removes its source only together with the final placement on Apply.
**Blocks / Entities** choose what to place, with counts in the placement strip.
Both are enabled initially. Blocks include inventories and other block data;
entities include mobs, frames and their passengers. Player profiles stay in place.
Copies get new UUIDs; Take keeps the originals. Turning either group off changes
only actor visibility, without rebuilding geometry. Both groups share one Undo.
**Keep placing** keeps the clipboard and its geometry ready for the next spot. Each
placement is a separate Undo; Take clears its source only on the first placement.
The Copy air checkbox explicitly includes omitted/air cells. A schematic grows automatically
when a placement exceeds its bounds, including negative X/Y/Z. The camera keeps its
world position; Apply and Undo include the resize. A faint dashed outline marks the
current extent. The View menu toggles schematic bounds and chunk contours.
Very large grids show at most 64 lines per horizontal axis near the camera position
at the time the guides are built. Clipboard geometry is built once and repositioned
through actor transforms. The clipboard survives opening another document.
Rotate ±90° and Mirror X/Z transform block states, entity positions, headings and
hanging anchors together. Existing biomes and unselected entity world positions remain
unchanged when schematic bounds grow. World placements still require loaded,
existing terrain; missing chunks are not generated.

**Repeat** or Edit → Repeat selection opens a compact strip: extra copies, direction,
gap and Blocks / Entities. A gap of 0 puts copies edge to edge. Preview shows the whole series and change counts;
Place copies commits it as one Undo. Changing a parameter clears the old preview.
Copy air affects only each copy's box, leaving gaps unchanged. The original stays.

The rule button defaults to **Replace all**. **Keep existing** fills air only;
**Only material** matches a block ID or an exact state from loaded materials or direct
input, including mod IDs. Copy air also obeys the rule. Conditional placement uses
**Preview → Place** with actual changes and changed/skipped counts. **Adjust** returns
to moving the ghost; **Cancel** exits. No matches means no change and no Undo entry.
Take preserves skipped source cells, including overlapping moves. Rules affect
blocks only; entities are placed independently, including with an entities-only copy.
Missing world chunks/sections are never treated as air. Narrow areas reflow controls without
resizing the scene.

## Objects and inventories

**Objects → Find objects…** (Ctrl/Cmd+F) opens a compact panel over the scene.
Search by ID or words such as `armor stand`, `chest`, or `mymod:`. Filters cover
entities, blocks, or **Block data** (blocks carrying NBT); **In selection** limits
the search to the selected region. Results use loaded data, including unsaved
edits and objects hidden by a height slice. Empty space is excluded.

Each page holds at most 64 objects. **Show** selects and frames the result;
**Select** keeps the camera in place; **Inspect** opens its data. Select one block
or multiple entities on the current page; separated blocks are never replaced by
their bounding box. Full IDs and world coordinates appear below the list and on
hover. Show restores All layers if the result is outside the current height slice.
The panel preserves viewport size; Escape closes it and releases focus to the scene.

Python uses the same search through `edit.find_objects("chest", kind="data", limit=64)`.
The returned page has `rows`, `total` and `offset`; each row carries local `position`,
`identity`, `kind`, and an entity `key` when applicable. Add `edit.origin` for world
coordinates. Pass `selection=selection` to restrict the region, or `offset=64` for
the next page. Search does not change the document or its history.

Click an entity to select it; Shift+click adds or removes one from the group.
The selection strip's **Entities** button, or Objects → Select entities in region,
selects all entities in the selected cuboid; without a cuboid it uses the loaded area.
Region filtering runs in the worker; selecting the whole loaded area needs no NBT
parsing or background job. Selection outlines use one combined line mesh.
Objects provides Move, Duplicate, Rotate and Delete. These operations run in the worker,
are one Undo step, and update both the scene and map markers. Duplicate gives entities
and their passengers new UUIDs and selects the new copies. Hanging entities rotate in 90° steps. Player profiles
can be inspected, moved and edited; exclude them when duplicating or deleting a group.

**Inspect…** opens the same inspector for selected entities or a single block.
Structure shows a typed NBT tree, populated in pages of 128 fields. **Find** searches
field names, paths and values, including fields not yet expanded. Select a result and
use **Edit value…** to change a number or literal text without writing NBT syntax.
Numeric types and their ranges are retained, including exact 64-bit integers.

**Inventories** locates nested item records by `id`/`Id` and `count`/`Count`, without
requiring a vanilla container ID or slot layout. Search by item ID or path;
**Edit count…** changes the amount and **Open item…** reveals its full structure.
Unknown mod fields are retained. Changes stay in the inspector until **Apply changes**;
**Cancel** discards drafts. Apply commits all changed objects as one Undo step.
The **NBT text** tab remains available for advanced structural edits.

Search runs in a background thread with 128 results per page, bounded to 100,000
visited fields and 128 nesting levels. A limited search is labelled explicitly;
complete data remains available in Structure and NBT text. Closing the inspector
cancels pending search work. See [inspector design and checks](docs/object-inspector.md).
This is generic data editing, not validation of every mod's custom rules or models.

## Worlds

Choose File → Open and select the world folder, or pass its path on the command line
(`--world` remains supported). The first view is near the saved
player position, falling back to spawn. **F5 / View → Refresh world** rereads the same world around the camera.
View → World radius and location contains dimensions, vertical range and
Restore Defaults. Refresh preserves the world-space camera, pending edits and session history,
including edits outside the new window. Selection survives when it still fits.
Refresh is unavailable during a placement or operation preview.

The default window spans 3 × 3 chunks and a section-aligned vertical radius of
32 blocks. Use the compact **Refresh · F5** button or F5 to reload that radius
around the current camera. Flying never checks region boundaries, starts reads
or schedules geometry/map rebuilds. Disk reads and geometry building run in a
worker process while the old scene remains usable. Repeated explicit requests
retain only the latest queued request. World requests take priority over pending
minimap work. Open and F5 rebuild the bounded window as independent 16³ sections.
Schematic preview, discard, undo and redo replace only affected sections and
boundary neighbors. Apply reuses the completed preview. Unchanged actors stay
on the GPU; entities form a separate layer rebuilt when their data changes. Previous 3D world windows are
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
of retained and replacement sections before creating actors.

**Apply only changes the local session. Save world writes accumulated edits.**
Editing requires existing chunks and sections in Java 1.18+; absent terrain is
not generated. Save keeps the undo history. Undo after Save creates a reverse
local patch, sent to disk by the next Save. New operations allow up to 500,000
pending changed cells; history navigation can exceed that limit to retain Undo.

The core writer compares each touched block and block-entity NBT with its original
value in freshly read chunks. Matching edits are merged; already-saved values are
accepted; conflicts stop Save without overwriting them. Region packing uses Amulet,
and unrelated NBT, biomes and entities are retained. Height/light caches and affected
POI validity are invalidated for Minecraft to rebuild. Region copies are prepared
and verified before installation. Originals and a file manifest remain in
`<world>/.structura/backups/<save-id>`; backups are not automatically deleted.
Save does not rebuild unchanged 3D geometry.

Entity changes use the same staging and backup mechanism. Save reads the entity's
original storage, merges its updated payload, and moves ordinary entities between
existing chunks when necessary. Player changes are written to their profile or
`level.dat`, with matching local `playerdata` mirrored. Unknown fields are retained;
conflicting disk data stops Save. Saved entity edits remain undoable after F5.

Structura serializes its own saves and rechecks file hashes before replacement.
This is best-effort disk editing: it does not lock Minecraft, exclude the final
race with another writer, or provide atomicity across multiple files. On a partial
I/O error the pending patch and backup remain available. Conflict resolution and
backup restoration currently require Undo/reopening or manual recovery; there is
no Force button or recovery browser yet.

The atlas stores the current camera cuts when the large map is open; compact
flight does not write map tiles to disk. A dashed box marks the currently loaded
volume. Dragging reads cached images in a background thread, never chunks.
An explicitly panned large view keeps its center until F; compact views always follow the camera.
Unknown chunks remain unknown, rather than becoming air.

The cache is `structura-edit/atlas-v1.sqlite` in the OS cache directory, outside
the save (`~/Library/Caches/structura-edit` on macOS). It uses transactional PNG
tiles of 128×128 blocks at 16 pixels per block. Up to 192 visible tiles are decoded
at the requested screen scale, bounded to 64 MiB of RGBA pixels; decoding and
image transfer briefly need additional copies. Disk
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
Unsaved edits and operation previews appear in the current images but never
overwrite the persistent atlas.

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
`source_data_version` through the Python API; Open and Import request it in the GUI.

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
record fields and ordinary entities; it does not translate Minecraft versions or copy biomes.
`copy`, `paste` and `stack` accept `include_blocks=True, include_entities=True`.
Players are excluded. Passenger trees travel with their root entity and count as
one entry. Copy creates new root/passenger UUIDs; Take retains identity and world
provenance. The separate Move blocks operation remains limited to blocks.
Schematic destinations expand the document as needed within the preview budget.
The GUI uses the shared clipboard
placement workflow described above; Move blocks uses the offset panel.

`stack(selection, copies, step, include_air=False)` prepares additional copies at
`selection.lower + n * step`, for `n` from 1 through `copies`. The nonzero integer
step may use several axes. All copies read the same clipboard; the last destination
wins where copies overlap. Work and extent budgets are checked before building the
change, which applies and undoes as a single operation.

Both `paste` and `stack` accept `destination=DestinationRule()` from `structura_edit`.
Use `DestinationRule("air")` to keep existing blocks, or
`DestinationRule("material", "minecraft:stone")` to replace only stone. Conditions read
the unchanged destination snapshot. Filtered Take protects skipped source cells from
incoming copies; dependent moves may also be skipped to keep their data intact.

`structura_edit.object_edits` provides `entity_items`, `transform_entities`,
`block_data`, `edit_block_data` and `edit_entity_data`. Mutation functions prepare
ordinary ChangeSets for `edit.apply`, previews, transactions and Undo. A block's
state remains separate from its block-entity payload; the inspector combines both.

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
python libs/structura-edit/tests/smoke_objects.py
python libs/structura-edit/tests/smoke_placement.py
python libs/structura-edit/tests/smoke_placement_tools.py
python libs/structura-edit/tests/smoke_destination_rules.py
python libs/structura-edit/tests/smoke_map.py libs/structura-render/src/structura_render/data/examples/demo.nbt
python libs/structura-edit/tests/smoke_map.py /path/to/saves/MyWorld
```

The viewport renders on demand and coalesces repeated requests into one queued Qt
frame. Binary-alpha textures such as leaves use an opaque depth pass with transparent
texels discarded; only blended materials and ghosts use depth peeling. There is no
permanent FPS widget. To measure completed frames during scripted mouse/WASD input:

```bash
python libs/structura-edit/tests/benchmark_flight.py example.nbt --visible --close --ghost --output /tmp/flight.json
```

The five-second benchmark reports completed-frame intervals and time inside VTK Render,
including the viewport's actual pixel size. It opens the source without saving it.

GUI smoke tests use a hidden window and produce JSON measurements. The schematic
smoke also saves its own widget and VTK framebuffer images for layout checks. World tests read the selected save; schematic tests save to a
temporary directory. Project rules are in the workspace `AGENTS.md`; the
[roadmap](docs/structura-edit-roadmap.md) separates the foundation from later
world writing, clipboard transformations, brushes and terrain operations.

The [module map](docs/structura-edit-architecture.md) describes ownership and
data flow. Historical reports are in the [archive](docs/archive/structura-edit/README.md),
excluded from ordinary search. Read them only when investigating an earlier decision.
