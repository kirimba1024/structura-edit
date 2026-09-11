import builtins
import subprocess
import sys

import pytest

from structura_edit.__main__ import main


@pytest.fixture
def failed_gui_import(monkeypatch):
    original = builtins.__import__

    def install(error):
        def importing(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'ui' and level == 1:
                raise error
            return original(name, globals, locals, fromlist, level)
        monkeypatch.setattr(builtins, '__import__', importing)
    return install


@pytest.mark.parametrize('name', ['PySide6', 'pyvista', 'pyvistaqt', 'vtkmodules'])
def test_cli_explains_missing_gui_dependency(failed_gui_import, capsys, name):
    failed_gui_import(ModuleNotFoundError(f'No module named {name}', name=name))
    with pytest.raises(SystemExit) as error:
        main([])
    assert error.value.code == 2
    assert 'Install structura-edit[gui]' in capsys.readouterr().err


@pytest.mark.parametrize('error', [ImportError('Invalid imported helper'),
                                  ModuleNotFoundError('Missing internal module', name='structura_edit.missing')])
def test_cli_preserves_unexpected_import_failures(failed_gui_import, error):
    failed_gui_import(error)
    with pytest.raises(type(error)) as raised:
        main([])
    assert raised.value is error


def test_base_import_and_help_do_not_import_gui():
    code = '''import builtins
original = builtins.__import__
def importing(name, *args, **kwargs):
    assert name.split('.')[0] not in ('PySide6', 'vtk', 'vtkmodules', 'pyvista', 'pyvistaqt')
    return original(name, *args, **kwargs)
builtins.__import__ = importing
import structura_edit
assert structura_edit.__version__
from structura_edit.__main__ import main
main(['--help'])
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert '--source-data-version' in result.stdout
