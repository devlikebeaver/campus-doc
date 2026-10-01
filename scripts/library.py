"""Versioned components, example forms and HWPX composition.

The agent translates natural-language requests into these internal operations.
Native HWP preservation remains in hangul.py; this module does not certify layout.
"""
import argparse
import copy
import json
import re
import tempfile
import zipfile
from pathlib import Path

import hangul as h
from registry import Registry

H = '{' + h.NS['hh'] + '}'
REFS = {'charPr': 'charPrIDRef', 'paraPr': 'paraPrIDRef',
        'borderFill': 'borderFillIDRef', 'style': 'styleIDRef'}
OBJECTS = {'tbl', 'pic', 'rect', 'ellipse', 'line', 'polygon', 'curve',
           'connectLine', 'container', 'ole', 'equation', 'textart', 'video'}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', value):
        raise ValueError('이름은 영문 소문자·숫자·하이픈으로 지정하세요.')
    return value


def invalidate(fragment):
    for cache in fragment.xpath('.//hp:linesegarray', namespaces=h.NS):
        cache.getparent().remove(cache)


def slots(fragment):
    return {str(i): {'text': t.text or '',
                    'char_style': t.getparent().get('charPrIDRef'),
                    'in_table': bool(t.xpath('ancestor::hp:tc', namespaces=h.NS))}
            for i, t in enumerate(fragment.xpath('.//hp:t', namespaces=h.NS))}


def fill(fragment, values):
    ts = fragment.xpath('.//hp:t', namespaces=h.NS)
    unknown = set(values) - {str(i) for i in range(len(ts))}
    if unknown:
        raise ValueError('없는 내용 슬롯: ' + str(sorted(unknown)))
    changed = False
    for key, value in values.items():
        if not isinstance(value, str) or any(ord(c) < 32 for c in value):
            raise ValueError('내용 슬롯은 제어문자 없는 문자열이어야 합니다. 줄은 문단으로 나누세요.')
        t = ts[int(key)]
        changed |= (t.text or '') != value
        t.text = value
    if changed:
        invalidate(fragment)
    return changed


def apply_xml_edits(fragment, edits):
    for edit in edits:
        path = edit['path']
        if not isinstance(path, str) or not (path == '.' or path.startswith('./')):
            raise ValueError('컴포넌트 내부의 상대 XPath만 허용합니다.')
        found = fragment.xpath(path, namespaces=h.NS)
        if len(found) != edit.get('count', 1) or any(not hasattr(e, 'attrib') for e in found):
            raise ValueError('컴포넌트 수정 대상 수 불일치: ' + path)
        for element in found:
            for key, value in edit.get('attributes', {}).items():
                if key not in element.attrib or key.endswith('IDRef') or key == 'id':
                    raise ValueError('이 경로로 ID 또는 없는 속성을 변경할 수 없습니다: ' + key)
                element.set(key, str(value))
    if edits:
        invalidate(fragment)


def normalize_rules(rules):
    result = {}
    for rule in rules:
        kind, sid = rule['kind'], str(rule['id'])
        if kind not in REFS:
            raise ValueError('지원하지 않는 스타일 종류: ' + str(kind))
        merged = result.setdefault((kind, sid), {})
        for change in rule['set']:
            path = change.get('path', '.')
            if not (path == '.' or path.startswith('./')):
                raise ValueError('스타일 내부의 상대 XPath만 허용합니다.')
            attrs = merged.setdefault(path, {})
            for attr, value in change['attributes'].items():
                if attr in {'id', 'itemCnt'} or attr.endswith('IDRef'):
                    raise ValueError('스타일 참조 ID는 자동 관리합니다.')
                if attr in {'textColor', 'color', 'faceColor', 'hatchColor'}:
                    if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(value)):
                        raise ValueError('색상은 #RRGGBB 형식입니다.')
                if attr == 'height' and kind == 'charPr' and int(value) <= 0:
                    raise ValueError('글자 크기는 양수여야 합니다.')
                attrs[attr] = str(value)
    return [{'kind': kind, 'id': sid,
             'set': [{'path': path, 'attributes': attrs} for path, attrs in changes.items()]}
            for (kind, sid), changes in result.items()]


def apply_styles(header, fragment, rules):
    """Copy shared definitions before editing; other instances retain their styles."""
    mapping, created = {}, []
    normalized = normalize_rules(rules)
    for rule in list(normalized):
        if rule['kind'] != 'borderFill':
            continue
        for kind in ('charPr', 'paraPr'):
            used = {e.get(REFS[kind]) for e in fragment.iter()}
            for definition in header.xpath('//hh:' + kind, namespaces=h.NS):
                if definition.get('id') not in used or definition.get('borderFillIDRef') != rule['id']:
                    continue
                if not any(r['kind'] == kind and r['id'] == definition.get('id') for r in normalized):
                    normalized.append({'kind': kind, 'id': definition.get('id'), 'set': []})
    for rule in normalized:
        kind, old = rule['kind'], rule['id']
        found = header.xpath('//hh:' + kind + '[@id=$sid]', namespaces=h.NS, sid=old)
        if len(found) != 1:
            raise ValueError('없는 스타일: ' + kind + '/' + old)
        if not any(e.get(REFS[kind]) == old for e in fragment.iter()):
            # Border definitions may be referenced by the component's char/para styles.
            refs = {e.get('charPrIDRef') for e in fragment.iter()}
            refs |= {e.get('paraPrIDRef') for e in fragment.iter()}
            indirect = kind == 'borderFill' and any(
                e.get('id') in refs and e.get('borderFillIDRef') == old
                for e in header.xpath('//hh:charPr|//hh:paraPr', namespaces=h.NS))
            if not indirect:
                raise ValueError('이 컴포넌트에서 사용하지 않는 스타일: ' + kind + '/' + old)
        definition = copy.deepcopy(found[0])
        parent = found[0].getparent()
        new = str(max(int(e.get('id')) for e in parent if e.get('id') is not None) + 1)
        definition.set('id', new)
        for change in rule['set']:
            nodes = definition.xpath(change['path'], namespaces=h.NS)
            if len(nodes) != 1 or not hasattr(nodes[0], 'attrib'):
                raise ValueError('스타일 수정 대상이 유일하지 않습니다: ' + change['path'])
            for key, value in change['attributes'].items():
                if key not in nodes[0].attrib:
                    raise ValueError('없는 스타일 속성: ' + key)
                nodes[0].set(key, value)
        parent.append(definition)
        if 'itemCnt' in parent.attrib:
            parent.set('itemCnt', str(len(parent)))
        mapping[(REFS[kind], old)] = new
        created.append(definition)
    for element in list(fragment.iter()) + [e for definition in created for e in definition.iter()]:
        for attr, value in list(element.attrib.items()):
            if (attr, value) in mapping:
                element.set(attr, mapping[(attr, value)])
    if mapping:
        invalidate(fragment)
    return mapping


def check_references(header, fragment, package_names):
    for kind, ref in REFS.items():
        known = {e.get('id') for e in header.xpath('//hh:' + kind, namespaces=h.NS)}
        missing = {e.get(ref) for e in fragment.iter() if ref in e.attrib} - known
        if missing:
            raise ValueError('스타일 참조 누락: ' + ref + ' ' + str(sorted(missing)))
    # A component may use bundled images, but importing an unrelated style/resource
    # namespace without remapping is deliberately rejected.
    for node in fragment.iter():
        if 'binaryItemIDRef' in node.attrib:
            bid = node.get('binaryItemIDRef')
            if not any(Path(n).stem == bid for n in package_names if n.startswith('BinData/')):
                raise ValueError('이미지 자원 누락: ' + bid)
    for node in header.xpath('//hh:fontRef', namespaces=h.NS):
        for lang, fid in node.attrib.items():
            available = header.xpath('//hh:fontface[@lang=$lang]/hh:font[@id=$fid]',
                                     namespaces=h.NS, lang=lang.upper(), fid=fid)
            if not available:
                raise ValueError('글꼴 참조 누락: ' + lang + '/' + fid)


class Library:
    def __init__(self, state=None, root=None):
        self.root = Path(root or h.ROOT).resolve()
        self.state = Path(state or self.root / 'library').resolve()

    def variant(self, variant):
        identifier(variant)
        return Registry(self.root, self.state).collection_path(variant)

    def revision(self, kind, variant, name):
        self.variant(variant)
        path = self.state / kind / variant / identifier(name)
        revisions = [int(p.name[1:]) for p in path.glob('v[0-9]*') if p.name[1:].isdigit()]
        return max(revisions, default=0)

    def component(self, variant, name, revision=None):
        identifier(name)
        rev = self.revision('components', variant, name) if revision is None else revision
        if not isinstance(rev, int) or rev < 0:
            raise ValueError('컴포넌트 버전이 올바르지 않습니다.')
        if rev == 0:
            base = self.variant(variant)
            item = next((c for c in h.read_json(base / 'manifest.json')['components']
                         if c['id'] == name), None)
            if item is None:
                raise ValueError('없는 기본 컴포넌트: ' + name)
            fragment = h.xml((base / 'components' / (name + '.xml')).read_bytes())
            meta = {'id': name, 'revision': 0, 'variant': variant, 'label': item['label'],
                    'style_rules': [], 'source': 'reference', 'fields': slots(fragment)}
        else:
            base = self.state / 'components' / variant / name / f'v{rev:04d}'
            meta = h.read_json(base / 'component.json')
            payload = (base / 'component.xml').read_bytes()
            if h.digest(payload) != meta['sha256']:
                raise ValueError('저장된 컴포넌트 무결성 오류')
            fragment = h.xml(payload)
        return meta, fragment

    def save_component(self, variant, name, fragment, meta, expected=None):
        current = self.revision('components', variant, name)
        if expected is not None and current != expected:
            raise ValueError('컴포넌트 버전 충돌: 최신 버전을 먼저 읽으세요.')
        self.check_component(variant, fragment, meta.get('style_rules', []))
        revision = current + 1
        target = self.state / 'components' / variant / identifier(name) / f'v{revision:04d}'
        target.mkdir(parents=True, exist_ok=False)
        fragment.set('id', name)
        payload = h.serialize(fragment)
        meta = {**meta, 'id': name, 'variant': variant, 'revision': revision,
                'sha256': h.digest(payload), 'fields': slots(fragment),
                'native_visual_comparison': 'pending'}
        (target / 'component.xml').write_bytes(payload)
        h.write_json(target / 'component.json', meta)
        Registry(self.root, self.state).sync()
        return meta

    def check_component(self, variant, fragment, rules):
        if fragment.tag != 'component' or not len(fragment) or any(p.tag != h.P + 'p' for p in fragment):
            raise ValueError('컴포넌트는 하나 이상의 hp:p 문단을 포함해야 합니다.')
        with zipfile.ZipFile(self.variant(variant) / 'package-base.zip') as base:
            header = h.xml(base.read('Contents/header.xml'))
            working = copy.deepcopy(fragment)
            apply_styles(header, working, rules)
            check_references(header, working, base.namelist())
            section = h.E.Element('{' + h.NS['hs'] + '}sec')
            for p in working:
                section.append(p)
            # Use the same merge coverage checks as complete documents.
            with tempfile.TemporaryDirectory(prefix='component-check-') as temp:
                test = Path(temp) / 'check.hwpx'
                with zipfile.ZipFile(test, 'w') as z:
                    z.writestr('Contents/header.xml', h.serialize(header))
                    z.writestr('Contents/section0.xml', h.serialize(section))
                h.validate(test)

    def add(self, spec):
        variant, name = spec['variant'], identifier(spec['id'])
        if self.revision('components', variant, name) or any(
                c['id'] == name for c in h.read_json(self.variant(variant) / 'manifest.json')['components']):
            raise ValueError('이미 있는 컴포넌트는 edit-component로 수정하세요.')
        source_modes = sum(key in spec for key in ('from', 'xml_file', 'paragraphs'))
        if source_modes != 1:
            raise ValueError('기존 컴포넌트, XML, 새 문단 중 한 가지 생성 방식을 지정하세요.')
        rules = []
        if 'from' in spec:
            ref = spec['from']
            parent, fragment = self.component(variant, ref['id'], ref.get('revision'))
            rules = parent.get('style_rules', [])
            provenance = {'id': ref['id'], 'revision': parent['revision']}
        elif 'xml_file' in spec:
            fragment = h.xml(Path(spec['xml_file']).read_bytes())
            provenance = 'imported-xml-same-style-namespace'
        else:
            fragment = h.E.Element('component', id=name, nsmap=h.NS)
            for paragraph in spec['paragraphs']:
                p = h.E.SubElement(fragment, h.P + 'p', id='0',
                    paraPrIDRef=str(paragraph['paragraph_style']), styleIDRef='0',
                    pageBreak='0', columnBreak='0', merged='0')
                for run in paragraph['runs']:
                    r = h.E.SubElement(p, h.P + 'run', charPrIDRef=str(run['character_style']))
                    h.E.SubElement(r, h.P + 't').text = run['text']
            provenance = 'new-paragraphs'
        fill(fragment, spec.get('text', {}))
        apply_xml_edits(fragment, spec.get('xml_edits', []))
        rules = normalize_rules(rules + spec.get('styles', []))
        return self.save_component(variant, name, fragment,
            {'label': spec.get('label', name), 'source': provenance, 'style_rules': rules}, expected=0)

    def edit(self, variant, name, patch):
        current, fragment = self.component(variant, name)
        expected = patch.get('expected_revision', current['revision'])
        if expected != current['revision']:
            raise ValueError('컴포넌트 수정의 기준 버전이 다릅니다.')
        fill(fragment, patch.get('text', {}))
        apply_xml_edits(fragment, patch.get('xml_edits', []))
        rules = normalize_rules(current.get('style_rules', []) + patch.get('styles', []))
        return self.save_component(variant, name, fragment,
            {**current, 'label': patch.get('label', current['label']), 'style_rules': rules,
             'previous_revision': current['revision']}, expected=expected)

    def template(self, variant, name, revision=None):
        identifier(name)
        rev = self.revision('templates', variant, name) if revision is None else revision
        if rev == 0 and name == variant + '-reference':
            m = h.read_json(self.variant(variant) / 'manifest.json')
            if len(m.get('sections', [])) > 1:
                raise ValueError('다중 섹션의 원형 재구성은 import_document.py rebuild를 사용하세요.')
            return {'id': name, 'revision': 0, 'variant': variant,
                    'label': m.get('label') or ('운영계획서 예시 양식' if variant == 'plan' else '결과보고서 예시 양식'),
                    'components': [{'instance': c['id'], 'component': c['id'], 'revision': 0}
                                   for c in m['components']]}
        return h.read_json(self.state / 'templates' / variant / name / f'v{rev:04d}' / 'template.json')

    def save_template(self, spec):
        variant, name = spec['variant'], identifier(spec['id'])
        base = self.variant(variant)
        if len(h.read_json(base / 'manifest.json').get('sections', [])) > 1:
            raise ValueError('새 조합은 현재 단일 섹션 양식만 지원합니다.')
        current = self.revision('templates', variant, name)
        if spec.get('expected_revision', current) != current:
            raise ValueError('양식 버전 충돌')
        items, instances = [], set()
        section_positions = []
        for index, item in enumerate(spec['components']):
            instance = identifier(item['instance'])
            if instance in instances:
                raise ValueError('문서 내 컴포넌트 이름 중복: ' + instance)
            instances.add(instance)
            meta, fragment = self.component(variant, item['component'], item.get('revision'))
            if fragment.xpath('.//hp:secPr', namespaces=h.NS):
                section_positions.append(index)
            items.append({**item, 'revision': meta['revision']})
        if section_positions != [0]:
            raise ValueError('페이지·헤더 설정을 포함한 컴포넌트가 첫 위치에 한 번 필요합니다.')
        if any(not isinstance(i.get('page_break_before', False), bool) for i in items):
            raise ValueError('페이지 구분은 참/거짓으로 지정하세요.')
        revision = current + 1
        result = {**spec, 'revision': revision, 'components': items,
                  'component_versions_pinned': True, 'native_visual_comparison': 'pending'}
        target = self.state / 'templates' / variant / name / f'v{revision:04d}'
        target.mkdir(parents=True, exist_ok=False)
        h.write_json(target / 'template.json', result)
        Registry(self.root, self.state).sync()
        return result

    def catalog(self):
        result = {'components': [], 'templates': []}
        variants = sorted(name for name, entry in Registry(self.root, self.state).sync()['collections'].items()
                          if entry['available'] and entry['enabled'])
        for variant in variants:
            m = h.read_json(self.variant(variant) / 'manifest.json')
            names = {c['id'] for c in m['components']}
            names |= {p.name for p in (self.state / 'components' / variant).glob('*') if p.is_dir()}
            for name in sorted(names):
                meta, _ = self.component(variant, name)
                result['components'].append({k: meta[k] for k in ('id', 'variant', 'revision', 'label')})
            names = {variant + '-reference'} if len(m.get('sections', [])) <= 1 else set()
            names |= {p.name for p in (self.state / 'templates' / variant).glob('*') if p.is_dir()}
            for name in sorted(names):
                result['templates'].append(self.template(variant, name))
        return result

    def form_data(self, variant, name, revision=None):
        template = self.template(variant, name, revision)
        fields = {}
        for item in template['components']:
            _, fragment = self.component(variant, item['component'], item['revision'])
            fields[item['instance']] = {key: value['text'] for key, value in slots(fragment).items()}
        return {'variant': variant, 'template': name, 'template_revision': template['revision'],
                'fields': fields}

    def compose(self, data, target):
        variant = data['variant']
        template = self.template(variant, data['template'], data['template_revision'])
        instances = {item['instance'] for item in template['components']}
        if set(data.get('fields', {})) - instances:
            raise ValueError('양식에 없는 문서 내용 컴포넌트')
        m = h.read_json(self.variant(variant) / 'manifest.json')
        section = h.E.Element('{' + h.NS['hs'] + '}sec', nsmap=m['namespace_map'], **m['section_attributes'])
        object_counter = 1000000000
        paragraph_counter = 1
        evidence = []
        with zipfile.ZipFile(self.variant(variant) / 'package-base.zip') as base:
            header = h.xml(base.read('Contents/header.xml'))
            section_positions = []
            for index, item in enumerate(template['components']):
                meta, fragment = self.component(variant, item['component'], item['revision'])
                fill(fragment, data.get('fields', {}).get(item['instance'], {}))
                apply_styles(header, fragment, meta.get('style_rules', []))
                if fragment.xpath('.//hp:secPr', namespaces=h.NS):
                    section_positions.append(index)
                if item.get('page_break_before'):
                    fragment[0].set('pageBreak', '1')
                # New composition has a different order; old line positions cannot
                # establish correct page layout. Let the native editor reflow it.
                invalidate(fragment)
                for element in fragment.iter():
                    local = h.E.QName(element).localname
                    if local == 'p' and element.tag.startswith(h.P):
                        element.set('id', str(paragraph_counter))
                        paragraph_counter += 1
                    elif local in OBJECTS and element.tag.startswith(h.P):
                        element.set('id', str(object_counter))
                        if 'zOrder' in element.attrib:
                            element.set('zOrder', str(object_counter - 1000000000))
                        object_counter += 1
                check_references(header, fragment, base.namelist())
                for paragraph in fragment:
                    section.append(paragraph)
                evidence.append({'instance': item['instance'], 'component': item['component'],
                                 'revision': item['revision']})
            if section_positions != [0]:
                raise ValueError('페이지·헤더 설정이 첫 컴포넌트에 한 번 필요합니다.')
            destination = Path(target)
            if destination.suffix.lower() != '.hwpx':
                raise ValueError('새 컴포넌트 조합의 출력은 HWPX입니다. 네이티브 HWP는 기존 생성기를 사용하세요.')
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Validate a completed candidate before publishing it to the target path.
            with tempfile.TemporaryDirectory(prefix='form-compose-', dir=destination.parent) as temp:
                candidate = Path(temp) / 'candidate.hwpx'
                with zipfile.ZipFile(candidate, 'w', zipfile.ZIP_DEFLATED) as z:
                    for info in base.infolist():
                        content = base.read(info.filename)
                        if info.filename == 'Contents/header.xml':
                            content = h.serialize(header)
                        if not info.filename.startswith(('Scripts/', 'Preview/')):
                            z.writestr(info, content)
                    z.writestr('Contents/section0.xml', h.serialize(section))
                    z.writestr('Preview/PrvText.txt', '\n'.join(section.xpath('.//hp:t/text()', namespaces=h.NS)).encode('utf-8'))
                checks = h.validate(candidate)
                candidate.replace(destination)
        result = {'output': str(destination), 'template': template['id'], 'revision': template['revision'],
                  'components': evidence, 'structural_checks': checks, 'line_cache': 'invalidated-for-reflow',
                  'native_visual_comparison': 'pending', 'paragraphs': paragraph_counter - 1}
        h.write_json(str(destination) + '.qa.json', result)
        return result

    def edit_content(self, data, patch, target):
        """Change one document's data and recompose without publishing components."""
        updated = copy.deepcopy(data)
        all_fields = self.form_data(data['variant'], data['template'], data['template_revision'])['fields']
        for instance, changes in patch.items():
            if instance not in all_fields:
                raise ValueError('없는 내용 컴포넌트: ' + instance)
            for slot, change in changes.items():
                if slot not in all_fields[instance]:
                    raise ValueError('없는 내용 슬롯: ' + instance + '/' + slot)
                current = updated.get('fields', {}).get(instance, {}).get(slot, all_fields[instance][slot])
                if not isinstance(change, dict) or set(change) != {'before', 'after'}:
                    raise ValueError('내용 수정은 before/after 값을 지정하세요.')
                if current != change['before']:
                    raise ValueError('내용이 예상과 다릅니다: ' + instance + '/' + slot)
                updated.setdefault('fields', {}).setdefault(instance, {})[slot] = change['after']
        result = self.compose(updated, target)
        h.write_json(str(target) + '.data.json', updated)
        result['library_components_changed'] = False
        result['data_output'] = str(target) + '.data.json'
        h.write_json(str(target) + '.qa.json', result)
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', help='User-specific writable library directory')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('catalog')
    add = commands.add_parser('add-component'); add.add_argument('spec')
    edit = commands.add_parser('edit-component')
    edit.add_argument('variant'); edit.add_argument('name'); edit.add_argument('patch')
    template = commands.add_parser('save-template'); template.add_argument('spec')
    form = commands.add_parser('form-data')
    form.add_argument('variant'); form.add_argument('name'); form.add_argument('output')
    form.add_argument('--revision', type=int)
    compose = commands.add_parser('compose'); compose.add_argument('data'); compose.add_argument('output')
    content = commands.add_parser('edit-content')
    content.add_argument('data'); content.add_argument('patch'); content.add_argument('output')
    args = parser.parse_args(); library = Library(args.state)
    if args.command == 'catalog':
        result = library.catalog()
    elif args.command == 'add-component':
        result = library.add(h.read_json(args.spec))
    elif args.command == 'edit-component':
        result = library.edit(args.variant, args.name, h.read_json(args.patch))
    elif args.command == 'save-template':
        result = library.save_template(h.read_json(args.spec))
    elif args.command == 'form-data':
        result = library.form_data(args.variant, args.name, args.revision)
        h.write_json(args.output, result)
    elif args.command == 'edit-content':
        result = library.edit_content(h.read_json(args.data), h.read_json(args.patch), args.output)
    else:
        result = library.compose(h.read_json(args.data), args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
