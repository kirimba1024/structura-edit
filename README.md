# Structura Edit

Minecraft schematic editing from Python and a desktop workbench. Both use the
same ChangeSet → preview → Apply → Undo/Redo operations. Java worlds are edited
through bounded loaded areas; Apply stays local until **Save world**.

This is a development release. NBT/SNBT, Sponge v2/v3 and normalized legacy
`.schematic` are editable. Litematic, Bedrock `.mcstructure` and Sponge v1 support
viewing, selection and export. Java world writing supports DataVersion 2844–3955
in existing chunks/sections. Other versions are view-only; changing a version
number or pasting across versions is not a conversion.

## Install and launch

Use Python 3.9–3.13. Edit 0.1.0a2 requires core 0.6.2 and render 0.8.2 or newer
within their current minor series; older wheels are rejected during installation.
The GUI includes Qt/VTK and optional format readers; the base import loads neither
Qt nor VTK. Native GUI verification is currently on macOS.

Available downloads are listed in [GitHub Releases](https://github.com/kirimba1024/structura-edit/releases).
Install a downloaded Python wheel with its GUI extra:

```bash
python -m pip install './structura_edit-0.1.0a2-py3-none-any.whl[gui]'
structura-edit
```

For development, install all three source packages from the workspace:

```bash
git clone --recurse-submodules https://github.com/kirimba1024/structura.git
cd structura
python -m venv .venv-edit
source .venv-edit/bin/activate
python -m pip install -e 'libs/structura-core[world,legacy,bedrock]' -e 'libs/structura-render[hero,overview]' -e 'libs/structura-edit[gui,test,typing]'
structura-edit
```

On Windows activate with `.venv-edit\Scripts\activate`. For headless use omit
`gui` and choose core's optional readers as needed. A bundled Apple Silicon app
and its installation check are described in [packaging](packaging/README.md).

```bash
structura-edit house.nbt --assets /path/to/client.jar
structura-edit build.litematic --region Main
structura-edit /path/to/saves/MyWorld
```

Open accepts schematic files, Java world folders and `level.dat`. Minecraft assets
are local; without them, fallback colours are used. JAR code is never executed.
Start with **Explore demo**: select a block → Fill preview → Apply → Undo → Save.

## Python example

```python
from structura_edit import EditSession

edit = EditSession.open("house.nbt")
change = edit.replace(edit.select(), "minecraft:oak_planks", "minecraft:spruce_planks")
edit.apply(change)
edit.save("house-edited.nbt")
```

## Read by task

| Need | Document |
|---|---|
| Controls, tools, world saving and recovery | [Workbench guide](docs/workbench.md) |
| Selections, changes, clipboard, entities and recipes | [Python API](docs/api.md) |
| State owners, async acceptance and subsystem boundaries | [Architecture](docs/structura-edit-architecture.md) |
| World overview, coverage and LOD contracts | [World view](docs/world-view.md) |
| Checks, native scenarios and benchmarks | [Verification](docs/verification.md) |
| Current work and next priorities | [Plan](docs/structura-edit-roadmap.md) |
| Past decisions and measured evidence | [Archive](docs/archive/README.md) |

Update the relevant current document when behaviour changes. Historical reports
are evidence, not additional requirements or required startup reading.
