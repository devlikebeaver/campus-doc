"""Exercise real composition and version isolation using the supplied components."""
import copy
import json
import tempfile
import zipfile
from pathlib import Path

import hangul as h
from library import Library


def load(path):
    with zipfile.ZipFile(path) as z:
        return h.xml(z.read('Contents/header.xml')), h.xml(z.read('Contents/section0.xml'))


def heading_colors(header, section):
    result = []
    for t in section.xpath('//hp:t', namespaces=h.NS):
        if (t.text or '') not in {'목     적', '추진 일정', '검토 항목'}:
            continue
        sid = t.getparent().get('charPrIDRef')
        style = header.xpath('//hh:charPr[@id=$sid]', namespaces=h.NS, sid=sid)[0]
        result.append((t.text, style.get('textColor')))
    return result


def main():
    with tempfile.TemporaryDirectory(prefix='hangul-library-test-') as temp:
        temp = Path(temp)
        lib = Library(temp / 'library')
        reference_hashes = {str(p): h.digest(p.read_bytes())
                            for p in (h.ROOT / 'assets').rglob('*') if p.is_file()}
        # A genuinely new paragraph component, retaining the exact private glyph.
        new = lib.add({'variant': 'plan', 'id': 'new-note', 'label': '추가 주석',
            'paragraphs': [{'paragraph_style': '55', 'runs': [
                {'character_style': '41', 'text': '\uf06d '},
                {'character_style': '50', 'text': '새 컴포넌트 내용'}]}]})
        assert new['revision'] == 1
        add_spec = {'variant': 'plan', 'id': 'heading-schedule', 'label': '추진 일정 제목',
                    'from': {'id': 'heading-purpose', 'revision': 0},
                    'text': {'0': '5', '1': '추진 일정'}}
        lib.add(add_spec)
        template_spec = {'variant': 'plan', 'id': 'library-test', 'label': '조합 시험',
            'components': [
                {'instance': 'cover', 'component': 'cover', 'revision': 0},
                {'instance': 'body-title', 'component': 'body-title', 'revision': 0},
                {'instance': 'original-heading', 'component': 'heading-purpose', 'revision': 0},
                {'instance': 'original-body', 'component': 'purpose', 'revision': 0},
                {'instance': 'custom-heading', 'component': 'heading-schedule'},
                {'instance': 'custom-note', 'component': 'new-note'},
                {'instance': 'table-a', 'component': 'schedule-lecture', 'revision': 0},
                {'instance': 'table-b', 'component': 'schedule-lecture', 'revision': 0}]}
        first = lib.save_template(template_spec)
        data = lib.form_data('plan', 'library-test')
        output = temp / 'first.hwpx'
        result = lib.compose(data, output)
        assert result['structural_checks']['table_merge_coverage'] == 'passed'
        head, section = load(output)
        assert ('추진 일정', '#214368') in heading_colors(head, section)
        objects = section.xpath('//hp:tbl|//hp:pic', namespaces=h.NS)
        assert len({e.get('id') for e in objects}) == len(objects), 'Duplicated object IDs'
        # Editing publishes version 2, while the existing form remains pinned to 1.
        edited = lib.edit('plan', 'heading-schedule', {'expected_revision': 1,
            'styles': [{'kind': 'charPr', 'id': '40',
                        'set': [{'path': '.', 'attributes': {'textColor': '#2F6248'}}]}]})
        assert edited['revision'] == 2
        lib.compose(data, temp / 'pinned.hwpx')
        assert ('추진 일정', '#214368') in heading_colors(*load(temp / 'pinned.hwpx'))
        second_spec = copy.deepcopy(template_spec)
        second_spec['expected_revision'] = 1
        second = lib.save_template(second_spec)
        data2 = lib.form_data('plan', 'library-test')
        assert second['components'][4]['revision'] == 2
        lib.compose(data2, temp / 'updated.hwpx')
        colors = heading_colors(*load(temp / 'updated.hwpx'))
        assert ('추진 일정', '#2F6248') in colors
        assert ('목     적', '#214368') in colors, 'Shared style changed another component'
        # Content changes affect the document only, not a component or template.
        component_hashes = {str(p): h.digest(p.read_bytes()) for p in (temp / 'library').rglob('*') if p.is_file()}
        content = lib.edit_content(data2, {'custom-heading': {'1': {'before': '추진 일정', 'after': '검토 항목'}}},
                                   temp / 'content.hwpx')
        assert content['library_components_changed'] is False
        assert ('검토 항목', '#2F6248') in heading_colors(*load(temp / 'content.hwpx'))
        assert component_hashes == {str(p): h.digest(p.read_bytes()) for p in (temp / 'library').rglob('*') if p.is_file()}
        try:
            lib.edit('plan', 'heading-schedule', {'expected_revision': 1, 'text': {'1': '실패해야 함'}})
        except ValueError:
            pass
        else:
            raise AssertionError('Stale revision accepted')
        try:
            lib.add({'variant': 'plan', 'id': 'invalid-style',
                     'paragraphs': [{'paragraph_style': '999999', 'runs': [
                         {'character_style': '50', 'text': '오류'}]}]})
        except ValueError:
            pass
        else:
            raise AssertionError('Unknown style accepted')
        assert reference_hashes == {str(p): h.digest(p.read_bytes())
                                    for p in (h.ROOT / 'assets').rglob('*') if p.is_file()}
        for variant in ('plan', 'report'):
            lib.compose(lib.form_data(variant, variant + '-reference'), temp / (variant + '.hwpx'))
            _, section = load(temp / (variant + '.hwpx'))
            assert '\uf06d' in ''.join(section.xpath('//hp:t/text()', namespaces=h.NS))
        print(json.dumps({'new_component': 'passed', 'component_revision': 'passed',
            'template_version_pinning': 'passed', 'scoped_styles': 'passed',
            'object_id_uniqueness': 'passed', 'content_edit_isolation': 'passed',
            'stale_revision_rejection': 'passed', 'style_reference_rejection': 'passed',
            'plan_and_report_composition': 'passed', 'reference_assets_unchanged': 'passed',
            'native_visual_comparison': 'pending'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
