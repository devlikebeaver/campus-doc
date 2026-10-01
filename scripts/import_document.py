"""Import a document into an isolated sibling collection and recursively inspect it.

Paragraph boundaries are candidates, not a claim of semantic or visual correctness.
Every review iteration records its exact input hashes. Document scripts are data.
"""
import argparse
import copy
import json
import shutil
import struct
import subprocess
import tempfile
import zipfile
import zlib
from pathlib import Path

import hangul as h
from library import check_references, identifier
from registry import Registry


def sections(parts):
    names = [n for n in parts if n.startswith('Contents/section') and n.endswith('.xml')]
    def order(name):
        suffix = Path(name).stem.removeprefix('section')
        if not suffix.isdigit():
            raise ValueError('지원하지 않는 섹션 파일명: ' + name)
        return int(suffix)
    return [(name, h.xml(parts[name])) for name in sorted(names, key=order)]


def grouping(section_list, profile=None, supplied=None):
    if profile:
        if len(section_list) != 1 or len(section_list[0][1]) != h.GROUPS[profile][-1][1]:
            raise ValueError('선택한 참조 프로필과 문단 구조가 다릅니다.')
        return [{'id': key, 'label': label, 'section': section_list[0][0],
                 'start': start, 'end': end, 'page': page}
                for start, end, key, label, page in h.GROUPS[profile]]
    if supplied is not None:
        groups = supplied
    else:
        groups = []
        for si, (name, section) in enumerate(section_list):
            for index, paragraph in enumerate(section):
                text = ''.join(paragraph.xpath('.//hp:t/text()', namespaces=h.NS)).strip()
                groups.append({'id': f's{si:03d}-p{index:04d}', 'section': name,
                    'start': index, 'end': index + 1,
                    'label': text[:48] or '빈 문단·간격·컨트롤', 'page': None})
    known = dict(section_list)
    coverage = {name: set() for name in known}
    seen = set()
    last = (-1, -1)
    order = {name: index for index, name in enumerate(known)}
    for group in groups:
        identifier(group['id'])
        if group['id'] in seen or group['section'] not in known:
            raise ValueError('중복 컴포넌트 또는 없는 섹션')
        seen.add(group['id'])
        start, end = group['start'], group['end']
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(known[group['section']]):
            raise ValueError('컴포넌트 문단 범위 오류')
        position = (order[group['section']], start)
        if position <= last:
            raise ValueError('추출 그룹은 원본 섹션·문단 순서여야 합니다.')
        last = position
        selected = set(range(start, end))
        if selected & coverage[group['section']]:
            raise ValueError('컴포넌트 문단 범위 중첩')
        coverage[group['section']].update(selected)
    if any(coverage[name] != set(range(len(section))) for name, section in section_list):
        raise ValueError('컴포넌트로 추출되지 않은 문단이 있습니다.')
    return groups


def walk(element, path='.'):
    """Include every descendant; cells and runs retain their parent context."""
    node = {'path': path, 'type': h.E.QName(element).localname,
            'attributes': dict(element.attrib), 'children': []}
    if element.text:
        node['text'] = element.text
    for index, child in enumerate(element):
        node['children'].append(walk(child, path + '/' + str(index)))
    return node


def native_extract(source, destination, groups, section_list):
    import olefile
    with olefile.OleFileIO(source) as ole:
        streams = {'/'.join(path): ole.openstream(path).read() for path in ole.listdir()}
    flags = struct.unpack_from('<I', streams['FileHeader'], 36)[0]
    if flags & (2 | 4 | 256):
        raise ValueError('암호화·배포용·서명 문서는 이 추출 경로에서 지원하지 않습니다.')
    raw_sections = {}
    for index, (part, section) in enumerate(section_list):
        name = 'BodyText/Section' + Path(part).stem.removeprefix('section')
        packed = streams.pop(name)
        raw = zlib.decompress(packed, -15) if flags & 1 else packed
        boundaries = [r[2] for r in h.records(raw) if r[0] == 66 and r[1] == 0]
        if not boundaries or boundaries[0] != 0 or len(boundaries) != len(section):
            raise ValueError('HWP와 변환된 HWPX의 문단 대응이 다릅니다.')
        boundaries.append(len(raw))
        raw_sections[part] = (name, raw, boundaries)
    if any(name.startswith('BodyText/Section') for name in streams):
        raise ValueError('변환 결과에 없는 HWP 섹션이 있습니다.')
    binary = destination / 'binary'
    binary.mkdir()
    layout = {'variant': destination.name, 'flags': flags, 'components': [], 'sections': []}
    schema, data = {}, {}
    for group in groups:
        key = group['id']; name, raw, boundaries = raw_sections[group['section']]
        blob = raw[boundaries[group['start']]:boundaries[group['end']]]
        (binary / (key + '.bin')).write_bytes(blob)
        data[key], schema[key] = {}, {}
        for index, record in enumerate(h.records(blob)):
            if record[0] != 67:
                continue
            for si, (start, end) in enumerate(h.plain_spans(record[4])):
                slot = f'{index}:{si}'
                data[key][slot] = record[4][start*2:end*2].decode('utf-16le')
                schema[key][slot] = {'record': index, 'units': [start, end], 'max_utf16_units': end-start}
        layout['components'].append({'id': key, 'label': group['label'], 'page': group.get('page'),
                                      'section': group['section'], 'sha256': h.digest(blob)})
    for part, (name, raw, _) in raw_sections.items():
        layout['sections'].append({'part': part, 'stream': name, 'raw_sha256': h.digest(raw)})
    streams.pop('PrvImage', None)
    h.write_json(binary / 'package-streams.json', {name: value.hex() for name, value in streams.items()})
    h.write_json(binary / 'manifest.json', layout)
    h.write_json(binary / 'field-schema.json', schema)
    h.write_json(destination / 'examples/native-reference-data.json', {'variant': destination.name, 'fields': data})
    return {'available': True, 'sections': len(raw_sections), 'visual_comparison': 'pending'}


def extract(source, name, profile=None, groups=None, reference_pdf=None, root=None,
            kind=None, institution='', department=''):
    root = Path(root or h.ROOT).resolve()
    destination = root / 'assets' / identifier(name)
    if destination.exists():
        raise ValueError('같은 이름의 전용 폴더가 이미 있습니다. 기존 폴더는 덮어쓰지 않습니다.')
    source = Path(source).resolve()
    if source.suffix.lower() not in {'.hwp', '.hwpx'}:
        raise ValueError('추출 입력은 HWP 또는 HWPX입니다. PDF는 외형 참조로 지정하세요.')
    if reference_pdf and Path(reference_pdf).suffix.lower() != '.pdf':
        raise ValueError('외형 참조는 PDF여야 합니다.')
    destination.mkdir(parents=True)
    sources = destination / 'source'; sources.mkdir()
    original = sources / ('original' + source.suffix.lower())
    shutil.copyfile(source, original)
    original_hash = h.digest(source.read_bytes())
    prepared = original
    conversion = None
    if source.suffix.lower() == '.hwp':
        prepared = sources / 'prepared.hwpx'
        conversion = h.convert(original, prepared)
    with zipfile.ZipFile(prepared) as z:
        if z.testzip() is not None:
            raise ValueError('입력 패키지 CRC 오류')
        parts = {key: z.read(key) for key in z.namelist()}
    section_list = sections(parts)
    if not section_list or any(p.tag != h.P + 'p' for _, section in section_list for p in section):
        raise ValueError('지원하지 않는 섹션 문단 구조')
    supplied_groups = groups is not None
    groups = grouping(section_list, profile, groups)
    manifest = {'variant': name, 'label': source.stem + ' · 추출 양식',
        'namespace_map': section_list[0][1].nsmap,
        'section_attributes': dict(section_list[0][1].attrib),
        'page_count_reference': (4 if profile == 'plan' else 5) if profile else None,
        'kind': kind or profile or 'unspecified',
        'identity': {'institution': institution, 'department': department},
        'source': {'filename': source.name, 'sha256': original_hash,
                   'format': source.suffix.lower(), 'stored': original.relative_to(destination).as_posix(),
                   'prepared': prepared.relative_to(destination).as_posix()},
        'sections': [{'part': part, 'namespace_map': section.nsmap,
                      'attributes': dict(section.attrib)} for part, section in section_list],
        'components': [], 'rules': {'style_namespace': name,
            'grouping': 'reference-profile' if profile else 'custom' if supplied_groups else 'paragraph-candidates',
            'semantic_review_required': True, 'visual_review_required': True,
            'existing_collections_modified': False}}
    (destination / 'components').mkdir()
    section_map = dict(section_list)
    fields, schema = {}, {}
    for group in groups:
        key = group['id']; fragment = h.E.Element('component', id=key)
        for paragraph in list(section_map[group['section']])[group['start']:group['end']]:
            fragment.append(copy.deepcopy(paragraph))
        payload = h.serialize(fragment)
        (destination / 'components' / (key + '.xml')).write_bytes(payload)
        texts = fragment.xpath('.//hp:t', namespaces=h.NS)
        fields[key] = {str(i): t.text or '' for i, t in enumerate(texts)}
        schema[key] = {str(i): {'char_style': t.getparent().get('charPrIDRef'),
            'source_utf16_units': len((t.text or '').encode('utf-16le'))//2,
            'in_table': bool(t.xpath('ancestor::hp:tc', namespaces=h.NS))} for i, t in enumerate(texts)}
        manifest['components'].append({'id': key, 'label': group['label'], 'section': group['section'],
            'page': group.get('page'), 'paragraphs': group['end'] - group['start'],
            'source_top_paragraphs': [group['start'], group['end'] - 1],
            'text_slots': len(texts), 'sha256': h.digest(payload),
            'char_styles': sorted({r.get('charPrIDRef') for r in fragment.xpath('.//hp:run', namespaces=h.NS)}),
            'tables': [h.table_info(t) for t in fragment.xpath('.//hp:tbl', namespaces=h.NS)]})
    with zipfile.ZipFile(destination / 'package-base.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for part, value in parts.items():
            if part not in section_map and not part.startswith(('Preview/', 'Scripts/')):
                z.writestr(part, value, compress_type=zipfile.ZIP_STORED if part == 'mimetype' else zipfile.ZIP_DEFLATED)
    combined = h.E.Element('inspection')
    for _, section in section_list:
        combined.append(copy.deepcopy(section))
    h.write_json(destination / 'tokens.json', h.styles(h.xml(parts['Contents/header.xml']), combined))
    manifest['package_base_sha256'] = h.digest((destination / 'package-base.zip').read_bytes())
    h.write_json(destination / 'field-schema.json', schema)
    h.write_json(destination / 'examples/reference-data.json', {'variant': name, 'fields': fields})
    if reference_pdf:
        shutil.copyfile(reference_pdf, sources / 'reference.pdf')
        manifest['source']['reference_pdf_sha256'] = h.digest(Path(reference_pdf).read_bytes())
    if original.suffix == '.hwp':
        manifest['native'] = native_extract(original, destination, groups, section_list)
    else:
        manifest['native'] = {'available': False}
    h.write_json(destination / 'manifest.json', manifest)
    report = review(destination)
    Registry(root).sync()
    return {'collection': name, 'directory': str(destination), 'components': len(groups),
            'sections': len(section_list), 'structural_review': report['structural_status'],
            'visual_review': report['visual_status'], 'source_unchanged': h.digest(source.read_bytes()) == original_hash,
            'conversion_report': conversion}


def composed_sections(project, manifest):
    roots = {s['part']: h.E.Element('{' + h.NS['hs'] + '}sec', nsmap=s['namespace_map'], **s['attributes'])
             for s in manifest['sections']}
    for component in manifest['components']:
        fragment = h.xml((project / 'components' / (component['id'] + '.xml')).read_bytes())
        for paragraph in fragment:
            roots[component['section']].append(paragraph)
    return roots


def review(project):
    project = Path(project).resolve(); manifest = h.read_json(project / 'manifest.json')
    findings, trees = [], []
    inputs = {}
    if h.digest((project / 'package-base.zip').read_bytes()) != manifest['package_base_sha256']:
        findings.append({'kind': 'changed-style-package', 'detail': '추출된 스타일·이미지 패키지가 변경됨'})
    if h.digest((project / manifest['source']['stored']).read_bytes()) != manifest['source']['sha256']:
        findings.append({'kind': 'changed-source-copy', 'detail': '보관한 원본 사본의 해시가 변경됨'})
    with zipfile.ZipFile(project / 'package-base.zip') as base:
        header = h.xml(base.read('Contents/header.xml'))
        names = base.namelist()
        original = project / manifest['source']['prepared']
        with zipfile.ZipFile(original) as baseline:
            roots = composed_sections(project, manifest)
            for component in manifest['components']:
                payload = (project / 'components' / (component['id'] + '.xml')).read_bytes()
                inputs[component['id']] = h.digest(payload)
                fragment = h.xml(payload)
                try:
                    check_references(header, fragment, names)
                except (ValueError, AssertionError) as error:
                    findings.append({'component': component['id'], 'kind': 'reference', 'detail': str(error)})
                trees.append({'id': component['id'], 'label': component['label'], 'section': component['section'],
                              'page_hint': component.get('page'), 'tree': walk(fragment)})
                if inputs[component['id']] != component['sha256']:
                    findings.append({'component': component['id'], 'kind': 'changed-fragment',
                                     'detail': '원본 추출본 이후 변경됨. 수정 이력과 차이를 확인하세요.'})
            for part, section in roots.items():
                expected = h.xml(baseline.read(part))
                if h.E.tostring(expected, method='c14n') != h.E.tostring(section, method='c14n'):
                    findings.append({'section': part, 'kind': 'source-difference',
                                     'detail': '컴포넌트 재조합이 원본 섹션과 다릅니다.'})
                with tempfile.TemporaryDirectory(prefix='recursive-check-', dir=project) as temp:
                    candidate = Path(temp) / 'check.hwpx'
                    with zipfile.ZipFile(candidate, 'w') as z:
                        z.writestr('Contents/header.xml', h.serialize(header))
                        z.writestr('Contents/section0.xml', h.serialize(section))
                    try:
                        h.validate(candidate)
                    except (AssertionError, ValueError) as error:
                        findings.append({'section': part, 'kind': 'structure', 'detail': str(error) or '표 병합·스타일 검사 실패'})
    review_dir = project / 'reviews'; review_dir.mkdir(exist_ok=True)
    versions = [int(p.stem.removeprefix('iteration-')) for p in review_dir.glob('iteration-*.json')]
    iteration = max(versions, default=0) + 1
    report = {'iteration': iteration, 'collection': manifest['variant'],
        'input_component_hashes': inputs, 'structural_status': 'failed' if findings else 'passed',
        'findings': findings, 'visual_status': 'pending', 'semantic_status': 'pending',
        'recursive_tree': 'component-tree.json',
        'visual_checks': ['first-page and body-page layout', 'declared and resolved fonts',
                          'letter spacing and width ratio', 'exact bullet glyph',
                          'header and CI', 'table borders, merges, padding and page breaks'],
        'ready_for_shared_library': False}
    h.write_json(review_dir / 'component-tree.json', trees)
    h.write_json(review_dir / f'iteration-{iteration:04d}.json', report)
    return report


def rebuild(project, target, node='node'):
    project = Path(project).resolve(); target = Path(target).resolve()
    if target.is_relative_to(project):
        raise ValueError('원본·컴포넌트 보관 폴더 밖에 새 시험 파일을 저장하세요.')
    report = review(project)
    if report['structural_status'] != 'passed':
        raise ValueError('구조 검토 결과가 실패한 추출본은 재구성하지 않습니다.')
    manifest = h.read_json(project / 'manifest.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == '.hwpx':
        roots = composed_sections(project, manifest)
        with zipfile.ZipFile(project / 'package-base.zip') as base, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
            for info in base.infolist():
                z.writestr(info, base.read(info.filename))
            for part, section in roots.items():
                z.writestr(part, h.serialize(section))
            z.writestr('Preview/PrvText.txt', '\n'.join(''.join(section.xpath('.//hp:t/text()', namespaces=h.NS))
                                                      for section in roots.values()).encode('utf-8'))
        result = {'output': str(target), 'xml_sections_equal_to_prepared_source': True,
                  'native_visual_comparison': 'pending'}
    elif target.suffix.lower() == '.hwp' and manifest['native']['available']:
        binary = project / 'binary'; meta = h.read_json(binary / 'manifest.json')
        streams = h.read_json(binary / 'package-streams.json')
        for section in meta['sections']:
            blobs = []
            for component in meta['components']:
                if component['section'] == section['part']:
                    blob = (binary / (component['id'] + '.bin')).read_bytes()
                    if h.digest(blob) != component['sha256']:
                        raise ValueError('네이티브 컴포넌트 무결성 오류')
                    blobs.append(blob)
            raw = b''.join(blobs)
            if h.digest(raw) != section['raw_sha256']:
                raise ValueError('네이티브 섹션이 원본과 다릅니다.')
            if meta['flags'] & 1:
                compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
                packed = compressor.compress(raw) + compressor.flush()
            else:
                packed = raw
            streams[section['stream']] = packed.hex()
        recipe = project / 'reviews/native-rebuild-streams.json'
        h.write_json(recipe, streams)
        subprocess.run([node, str(h.ROOT / 'scripts/ole_create.cjs'), str(target), str(recipe)], check=True)
        recipe.unlink()
        result = {'output': str(target), 'native_body_records_equal_to_source': True,
                  'native_visual_comparison': 'pending', 'stale_preview_bitmap_removed': True}
    else:
        raise ValueError('HWPX 또는 네이티브 추출 자원이 있는 HWP로 재구성하세요.')
    h.write_json(str(target) + '.qa.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(); commands = parser.add_subparsers(dest='command', required=True)
    extract_parser = commands.add_parser('extract')
    extract_parser.add_argument('source'); extract_parser.add_argument('--name', required=True)
    extract_parser.add_argument('--profile', choices=['plan', 'report'])
    extract_parser.add_argument('--groups'); extract_parser.add_argument('--reference-pdf')
    extract_parser.add_argument('--kind'); extract_parser.add_argument('--institution', default='')
    extract_parser.add_argument('--department', default='')
    check = commands.add_parser('review'); check.add_argument('project')
    compose = commands.add_parser('rebuild'); compose.add_argument('project'); compose.add_argument('output')
    compose.add_argument('--node', default='node')
    args = parser.parse_args()
    if args.command == 'extract':
        result = extract(args.source, args.name, args.profile, h.read_json(args.groups) if args.groups else None,
                         args.reference_pdf, kind=args.kind, institution=args.institution, department=args.department)
    elif args.command == 'review':
        result = review(args.project)
    else:
        result = rebuild(args.project, args.output, args.node)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
