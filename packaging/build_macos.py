import argparse
import hashlib
import json
import platform
import subprocess
import sys
import venv
from pathlib import Path
from tempfile import TemporaryDirectory


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def main():
    parser = argparse.ArgumentParser(description='Build the macOS arm64 Structura Edit application from workspace sources')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--skip-install', action='store_true', help='Reuse the already installed build dependencies')
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        parser.error('Build this application on an Apple Silicon Mac')
    package = Path(__file__).resolve().parent
    project = package.parent
    workspace = project.parent
    build = project / 'build'
    output = (args.output or project / 'dist').resolve()
    environment = build / 'package-env'
    python = environment / 'bin' / 'python'
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(environment)
    if not args.skip_install:
        run(python, '-m', 'pip', 'install', 'pip>=25', 'setuptools>=68', 'wheel', 'pyinstaller==6.22.2')
        run(python, '-m', 'pip', 'install', '-r', package / 'macos-requirements.txt')
    sources = [workspace / name for name in ('structura-core', 'structura-render', 'structura-edit')]
    with TemporaryDirectory(prefix='wheels-', dir=build) as temporary:
        wheels = Path(temporary)
        run(python, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation', '--wheel-dir', wheels, *sources)
        artifacts = [next(wheels.glob(name + '-*.whl')) for name in ('structura_core', 'structura_render', 'structura_edit')]
        run(python, '-m', 'pip', 'install', '--no-deps', '--force-reinstall', *artifacts)
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts}
    run(python, '-m', 'pip', 'check')
    (output / 'build.json').unlink(missing_ok=True)
    run(python, '-m', 'PyInstaller', '--noconfirm', '--distpath', output, '--workpath', build / 'pyinstaller', package / 'StructuraEdit.spec')
    app = output / 'Structura Edit.app'
    run('codesign', '--verify', '--deep', '--strict', app)
    run(app / 'Contents' / 'MacOS' / 'Structura Edit', '--check-installation', output / 'installation-check')
    verification = json.loads((output / 'installation-check' / 'result.json').read_text())
    archive = output / 'Structura-Edit-macOS-arm64.zip'
    run('ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, archive)
    digest = hashlib.sha256()
    with archive.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    manifest = dict(app=str(app), archive=archive.name, sha256=digest.hexdigest(), python=platform.python_version(),
                    platform=platform.platform(), signing='Ad hoc; not notarized', installation_check='passed',
                    versions=verification['versions'], wheels=hashes)
    (output / 'build.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest), flush=True)


if __name__ == '__main__':
    main()
