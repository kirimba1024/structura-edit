from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata


packages = ('structura_edit', 'structura_core', 'structura_render', 'amulet', 'PyMCTranslate')
datas = []
hiddenimports = []
for package in packages:
    datas.extend(collect_data_files(package))
    hiddenimports.extend(collect_submodules(package))
for distribution in ('structura-edit', 'structura-core', 'structura-render', 'amulet-core', 'PyMCTranslate',
                     'pyvistaqt', 'PySide6-Essentials', 'meshoptimizer'):
    datas.extend(copy_metadata(distribution, recursive=True))

a = Analysis(
    [str(Path(SPECPATH) / 'launcher.py')],
    pathex=[str(Path(SPECPATH).parent / 'tests')],
    datas=datas,
    binaries=collect_dynamic_libs('meshoptimizer', search_patterns=['_meshoptimizer*.so', '_meshoptimizer*.pyd']),
    hiddenimports=hiddenimports,
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'tkinter', 'pytest', 'IPython', 'jupyter'],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='Structura Edit',
    console=False, argv_emulation=False, target_arch='arm64',
)
collection = COLLECT(exe, a.binaries, a.datas, name='Structura Edit')
app = BUNDLE(
    collection, name='Structura Edit.app', bundle_identifier='io.github.kirimba1024.structura-edit',
    info_plist={
        'CFBundleDisplayName': 'Structura Edit',
        'CFBundleShortVersionString': '0.1.0',
        'CFBundleVersion': '0.1.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '13.0',
    },
)
