"""Generate public examples and verify real editing paths in the active runtime."""
import json
import shutil
from pathlib import Path

import hangul as h


def main():
    folder = h.ROOT / 'runtime/samples'
    folder.mkdir(parents=True, exist_ok=True)
    result = {'hwpx_generation': {}, 'hwpx_edit': 'pending', 'native_hwp_edit': 'unavailable',
              'native_visual_comparison': 'pending', 'gemini_app_end_to_end': 'not_tested'}
    for kind in ['plan', 'report']:
        target = folder / (kind + '.hwpx')
        h.assemble(h.ROOT / 'examples' / (kind + '-example-data.json'), target)
        result['hwpx_generation'][kind] = h.validate(target)
    edits = folder / 'edit.json'
    h.write_json(edits, [{'old': '예시 프로그램 운영계획서', 'new': '시험 프로그램 운영계획서', 'count': 1}])
    h.edit_hwpx(folder / 'plan.hwpx', folder / 'plan-edited.hwpx', edits)
    h.validate(folder / 'plan-edited.hwpx')
    result['hwpx_edit'] = 'passed'
    node = h.ROOT / 'runtime/node/node.exe'
    node_path = str(node) if node.is_file() else shutil.which('node')
    if node_path:
        # Synthetic HWP fixture; no original user document is distributed or read.
        h.convert(folder / 'plan.hwpx', folder / 'plan.hwp')
        h.write_json(edits, [{'old': '예시부서', 'new': '시험부서', 'count': 1}])
        evidence = h.edit_hwp_fixed(folder / 'plan.hwp', folder / 'plan-edited.hwp', edits, node_path)
        assert evidence['all_nontext_records_identical']
        result['native_hwp_edit'] = 'passed'
    h.write_json(h.ROOT / 'runtime/smoke-result.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
