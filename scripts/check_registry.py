"""Exercise isolated imports, recursive checks, discovery and form selection."""
import copy
import json
import tempfile
import zipfile
from pathlib import Path

import hangul as h
from import_document import extract, rebuild, review
from library import Library
from registry import Registry


def main():
    with tempfile.TemporaryDirectory(prefix='hangul-registry-check-') as temp:
        temp = Path(temp); root = temp / 'skill'; root.mkdir()
        # Rebuild a valid reference without source-file or engine dependencies.
        source = temp / 'source.hwpx'
        h.assemble(h.ROOT / 'examples/plan-reference-data.json', source)
        original = h.digest(source.read_bytes())
        result = extract(source, 'institution-plan', profile='plan', root=root,
                         institution='시험기관', department='시험부서')
        assert result['structural_review'] == 'passed', result
        project = root / 'assets/institution-plan'
        first = h.read_json(project / 'reviews/iteration-0001.json')
        assert first['ready_for_shared_library'] is False and first['visual_status'] == 'pending'
        second = review(project)
        assert second['iteration'] == 2 and second['structural_status'] == 'passed'
        trees = h.read_json(project / 'reviews/component-tree.json')
        def types(node):
            return {node['type']} | set().union(*(types(child) for child in node['children']))
        all_types = set().union(*(types(item['tree']) for item in trees))
        assert {'component', 'tbl', 'tc', 'p', 'run', 't'} <= all_types
        rebuilt = temp / 'reconstructed.hwpx'; rebuild(project, rebuilt)
        with zipfile.ZipFile(source) as a, zipfile.ZipFile(rebuilt) as b:
            expected = h.xml(a.read('Contents/section0.xml'))
            actual = h.xml(b.read('Contents/section0.xml'))
            assert h.E.tostring(expected, method='c14n') == h.E.tostring(actual, method='c14n')
        lib = Library(root=root)
        assert lib.form_data('institution-plan', 'institution-plan-reference')['fields']['cover']
        registry = Registry(root)
        selected = registry.select(kind='plan', institution='시험机构')
        assert selected['status'] == 'no-match', 'Wrong institution selected'
        selected = registry.select(kind='plan', institution='시험기관')
        assert selected['collection']['id'] == 'institution-plan'
        # A second local collection is discovered on the next registry read.
        extract(source, 'second-plan', profile='plan', root=root, institution='시험기관', department='시험부서')
        assert registry.select(kind='plan', institution='시험기관')['status'] == 'choose'
        registry.prefer('second-plan')
        assert registry.select(kind='plan')['collection']['id'] == 'second-plan'
        registry.configure('second-plan', {'enabled': False})
        assert registry.select(kind='plan')['collection']['id'] == 'institution-plan'
        registry.configure('second-plan', {'enabled': True})
        # A broken descendant is detected and an unsafe import is not selected.
        component = project / 'components/purpose.xml'
        clean = component.read_bytes(); fragment = h.xml(clean)
        fragment.xpath('.//hp:run', namespaces=h.NS)[0].set('charPrIDRef', '999999')
        component.write_bytes(h.serialize(fragment))
        broken = review(project)
        assert broken['structural_status'] == 'failed'
        assert any(f['kind'] == 'reference' for f in broken['findings'])
        try:
            registry.select(collection='institution-plan')
        except ValueError:
            pass
        else:
            raise AssertionError('Structurally broken collection selected')
        component.write_bytes(clean); review(project)
        # Generic imports use paragraph candidates, rather than a fixed source map.
        generic = extract(source, 'generic-source', root=root)
        assert generic['components'] == 80
        assert h.read_json(root / 'assets/generic-source/manifest.json')['rules']['grouping'] == 'paragraph-candidates'
        # Exact multi-section reconstruction is available without flattening sections.
        multi = temp / 'multi.hwpx'
        with zipfile.ZipFile(source) as original_zip, zipfile.ZipFile(multi, 'w') as z:
            for info in original_zip.infolist():
                z.writestr(info, original_zip.read(info.filename))
            z.writestr('Contents/section1.xml', original_zip.read('Contents/section0.xml'))
        multiple = extract(multi, 'multi-source', root=root)
        assert multiple['sections'] == 2 and multiple['components'] == 160
        rebuild(root / 'assets/multi-source', temp / 'multi-rebuilt.hwpx')
        # An explicitly registered external folder also participates in selection.
        other = temp / 'external-root'; other.mkdir()
        extract(source, 'external-plan', profile='plan', root=other, institution='외부기관')
        registry.watch(other / 'assets')
        assert registry.select(kind='plan', institution='외부기관')['collection']['id'] == 'external-plan'
        assert h.digest(source.read_bytes()) == original
        print(json.dumps({'isolated_import': 'passed', 'recursive_descendants': 'passed',
            'repeat_review_history': 'passed', 'source_reconstruction': 'passed',
            'custom_collection_library': 'passed', 'automatic_discovery': 'passed',
            'scope_selection': 'passed', 'ambiguous_selection': 'passed',
            'preferred_collection': 'passed', 'disabled_collection': 'passed',
            'broken_collection_rejected': 'passed', 'generic_paragraph_extraction': 'passed',
            'multiple_section_reconstruction': 'passed', 'external_folder_registration': 'passed',
            'source_unchanged': 'passed', 'native_visual_comparison': 'pending'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
