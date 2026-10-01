"""Report capabilities without assuming that a chat app can execute local code."""
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / 'runtime/python').exists():
    sys.path.insert(0, str(ROOT / 'runtime/python'))


def main():
    expected = {'python-hwpx': '6.6.0', 'lxml': '6.1.3', 'olefile': '0.47'}
    packages = {}
    for package, version in expected.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        packages[package] = {'expected': version, 'actual': actual, 'matches': actual == version}
    imports_ok = True
    for module in ['lxml.etree', 'olefile', 'hwpx']:
        try:
            __import__(module)
        except (ImportError, OSError):
            imports_ok = False
    node = ROOT / 'runtime/node/node.exe'
    node_path = str(node) if node.is_file() else shutil.which('node')
    node_version = None
    if node_path:
        try:
            node_version = subprocess.check_output([node_path, '--version'], text=True).strip()
        except (OSError, subprocess.SubprocessError):
            pass
    ready = imports_ok and all(p['matches'] for p in packages.values())
    result = {'python': sys.version.split()[0], 'python_path': sys.executable,
              'packages': packages, 'hwpx_ready': ready,
              'native_hwp_edit_ready': ready and bool(node_version), 'node_version': node_version,
              'native_hancom_layout': 'not_verified', 'gemini_app_end_to_end': 'not_tested'}
    if ready:
        from registry import Registry
        catalog = Registry().sync()
        result['collections'] = len(catalog['collections'])
        result['components'] = len(catalog['components'])
    (ROOT / 'runtime').mkdir(exist_ok=True)
    (ROOT / 'runtime/setup-status.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ready else 1


if __name__ == '__main__':
    sys.exit(main())
