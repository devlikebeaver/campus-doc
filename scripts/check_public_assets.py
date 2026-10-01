"""Reject source metadata and cached business values in bundled public examples."""
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as E

ROOT = Path(__file__).resolve().parents[1]
HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
FORBIDDEN_PATTERNS = [rb'KakaoTalk_\d+[^<]*\.(?:png|bmp|jpg)',
                      rb'CLP[0-9a-fA-F]+\.(?:png|bmp|jpg)', rb'OneDrive',
                      rb'[A-Z]:[\\/]Users[\\/]']


def verify_xml(payload):
    tree = E.fromstring(payload)
    for node in tree.iter(HP + 'shapeComment'):
        assert (node.text or '') == 'campus-doc CI placeholder', 'Source image description retained'
    for field in tree.iter(HP + 'fieldBegin'):
        if field.get('type') != 'FORMULA':
            continue
        params = {n.get('name'): n.text or '' for n in field.find(HP + 'parameters')}
        assert params['LastResult'] == '0', 'Original calculated value retained'
        assert params['Command'] == params['Formula'] + '??' + params['ResultFormat'] + ';;0'


def main():
    files = 0
    for kind in ['plan', 'report']:
        for path in (ROOT / 'assets' / kind).rglob('*'):
            if not path.is_file():
                continue
            assert path.suffix not in {'.hwp', '.hwpx', '.pdf', '.bin', '.pyc'}
            payloads = [path.read_bytes()]
            if path.suffix == '.zip':
                with zipfile.ZipFile(path) as archive:
                    payloads = [archive.read(n) for n in archive.namelist() if not n.startswith('BinData/')]
            for payload in payloads:
                for pattern in FORBIDDEN_PATTERNS:
                    assert not re.search(pattern, payload), 'Source-specific metadata: ' + path.name
                if payload.lstrip().startswith(b'<?xml'):
                    verify_xml(payload)
            files += 1
    print(json.dumps({'public_asset_files': files, 'source_filenames': 'removed',
                      'formula_cached_results': 'synthetic-zero', 'internal_metadata_scan': 'passed'}))


if __name__ == '__main__':
    main()
