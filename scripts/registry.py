"""Central, local form registry. Paths are relative to the registry directory."""
import argparse
import json
import os
import re
from pathlib import Path

import hangul as h


def key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', value):
        raise ValueError('양식 이름은 영문 소문자·숫자·하이픈으로 지정하세요.')
    return value


def normalized(value):
    return ''.join(str(value or '').split()).casefold()


class Registry:
    def __init__(self, root=None, state=None):
        self.root = Path(root or h.ROOT).resolve()
        self.state = Path(state or self.root / 'library').resolve()
        self.file = self.state / 'registry.json'

    def read(self):
        if self.file.exists():
            data = h.read_json(self.file)
            if data.get('schema_version') != 1:
                raise ValueError('지원하지 않는 레지스트리 버전')
            return data
        return {'schema_version': 1, 'settings': {'preferred_collection': None},
                'search_paths': [self.relative(self.root / 'assets')],
                'collections': {}, 'templates': {}, 'components': {}}

    def relative(self, path):
        target = Path(path).resolve()
        try:
            return Path(os.path.relpath(target, self.state)).as_posix()
        except ValueError:
            # Windows cannot express a relative path between different volumes.
            # Keep ordinary project paths portable; external volumes stay absolute.
            return target.as_posix()

    def absolute(self, path):
        return (self.state / path).resolve()

    def save(self, data):
        self.state.mkdir(parents=True, exist_ok=True)
        if not self.file.exists() or self.read() != data:
            candidate = self.file.with_suffix('.tmp')
            h.write_json(candidate, data)
            candidate.replace(self.file)

    def sync(self):
        data = self.read()
        paths = set()
        for location in data['search_paths']:
            directory = self.absolute(location)
            if directory.is_dir():
                paths.add(directory)
                paths.update(p for p in directory.iterdir() if p.is_dir())
        paths.update(self.absolute(c['path']) for c in data['collections'].values())
        seen = {}
        for folder in sorted(paths):
            if not (folder / 'manifest.json').is_file() or not (folder / 'package-base.zip').is_file():
                continue
            manifest = h.read_json(folder / 'manifest.json')
            name = key(manifest['variant'])
            if name in seen and seen[name] != folder:
                raise ValueError('양식 이름이 여러 폴더에 중복됩니다: ' + name)
            seen[name] = folder
            old = data['collections'].get(name, {})
            builtin = name in {'plan', 'report'} and folder == self.root / 'assets' / name
            source = manifest.get('source', {})
            scope = manifest.get('identity', {})
            entry = {**old, 'id': name, 'label': old.get('label') or manifest.get('label') or name,
                'path': self.relative(folder), 'origin': 'bundled' if builtin else 'document-import',
                'kind': old.get('kind') or manifest.get('kind') or (name if builtin else 'unspecified'),
                'institution': old.get('institution', scope.get('institution', '')),
                'department': old.get('department', scope.get('department', '')),
                'enabled': old.get('enabled', True), 'priority': old.get('priority', 0 if builtin else 100),
                'components': len(manifest['components']), 'sections': len(manifest.get('sections', [])) or 1,
                'manifest_sha256': h.digest((folder / 'manifest.json').read_bytes()),
                'source_filename': source.get('filename'), 'available': True,
                'review': {'structure': 'not-recorded', 'visual': 'pending', 'semantic': 'pending'}}
            iterations = sorted((folder / 'reviews').glob('iteration-*.json'))
            if iterations:
                review = h.read_json(iterations[-1])
                entry['review'] = {'structure': review['structural_status'], 'visual': review['visual_status'],
                                   'semantic': review.get('semantic_status', 'pending'),
                                   'iteration': review['iteration']}
            data['collections'][name] = entry
        for name, entry in data['collections'].items():
            if name not in seen:
                entry['available'] = False
        templates = {}
        components = {}
        for name, entry in data['collections'].items():
            if not entry['available']:
                continue
            if entry['sections'] == 1:
                templates[name + '/' + name + '-reference'] = {
                    'collection': name, 'id': name + '-reference', 'revision': 0,
                    'label': entry['label'] + ' · 원형 예시', 'origin': 'reference',
                    'manifest': entry['path'] + '/manifest.json'}
            manifest = h.read_json(self.absolute(entry['path']) / 'manifest.json')
            for component in manifest['components']:
                components[name + '/' + component['id']] = {
                    'collection': name, 'id': component['id'], 'label': component['label'],
                    'revision': 0, 'path': entry['path'] + '/components/' + component['id'] + '.xml',
                    'origin': 'reference'}
            for directory in (self.state / 'components' / name).glob('*'):
                versions = sorted(directory.glob('v[0-9]*/component.json'))
                if not versions:
                    continue
                path = versions[-1]; component = h.read_json(path)
                components[name + '/' + component['id']] = {
                    'collection': name, 'id': component['id'], 'label': component['label'],
                    'revision': component['revision'], 'path': self.relative(path.parent / 'component.xml'),
                    'metadata': self.relative(path), 'origin': 'user-component'}
            folder = self.state / 'templates' / name
            for directory in folder.glob('*'):
                versions = sorted(directory.glob('v[0-9]*/template.json'))
                if not versions:
                    continue
                path = versions[-1]; template = h.read_json(path)
                templates[name + '/' + template['id']] = {'collection': name, 'id': template['id'],
                    'revision': template['revision'], 'label': template.get('label', template['id']),
                    'origin': 'user-template', 'path': self.relative(path),
                    'components': template['components']}
        data['templates'] = templates
        data['components'] = components
        self.save(data)
        return data

    def collection_path(self, name):
        key(name)
        data = self.sync()
        entry = data['collections'].get(name)
        if not entry or not entry.get('available'):
            raise ValueError('등록되지 않거나 사용할 수 없는 양식: ' + name)
        return self.absolute(entry['path'])

    def watch(self, folder):
        folder = Path(folder).resolve()
        if not folder.is_dir():
            raise ValueError('양식 폴더가 없습니다.')
        data = self.read(); location = self.relative(folder)
        if location not in data['search_paths']:
            data['search_paths'].append(location)
        self.save(data)
        return self.sync()

    def configure(self, name, patch):
        data = self.sync()
        if name not in data['collections']:
            raise ValueError('없는 양식: ' + name)
        allowed = {'label', 'kind', 'institution', 'department', 'enabled', 'priority'}
        if set(patch) - allowed:
            raise ValueError('설정할 수 없는 양식 메타데이터')
        if 'enabled' in patch and not isinstance(patch['enabled'], bool):
            raise ValueError('사용 여부는 참/거짓이어야 합니다.')
        if 'priority' in patch and not isinstance(patch['priority'], int):
            raise ValueError('우선순위는 정수여야 합니다.')
        data['collections'][name].update(patch)
        self.save(data)
        return data['collections'][name]

    def prefer(self, name):
        data = self.sync()
        if name is not None and name not in data['collections']:
            raise ValueError('기본으로 선택할 양식이 없습니다.')
        data['settings']['preferred_collection'] = name
        self.save(data)
        return data['settings']

    def select(self, kind=None, institution=None, department=None, collection=None):
        data = self.sync()
        usable = [c for c in data['collections'].values() if c['available'] and c['enabled']
                  and c['review']['structure'] != 'failed']
        if collection:
            found = next((c for c in usable if c['id'] == collection), None)
            if not found:
                raise ValueError('지정한 양식이 비활성·누락·구조 실패 상태입니다.')
            return {'status': 'selected', 'reason': 'explicit', 'collection': found}
        if kind:
            usable = [c for c in usable if normalized(c['kind']) == normalized(kind)]
        for field, requested in (('institution', institution), ('department', department)):
            if requested:
                usable = [c for c in usable if not c.get(field) or normalized(c[field]) == normalized(requested)]
        preferred = data['settings'].get('preferred_collection')
        ranked = []
        for entry in usable:
            score = entry['priority']
            if institution and entry.get('institution'):
                score += 1000
            if department and entry.get('department'):
                score += 500
            if entry['id'] == preferred:
                score += 10000
            ranked.append((score, entry))
        ranked.sort(key=lambda item: (-item[0], item[1]['id']))
        if not ranked:
            return {'status': 'no-match', 'candidates': []}
        top = [entry for score, entry in ranked if score == ranked[0][0]]
        if len(top) > 1:
            return {'status': 'choose', 'candidates': top}
        return {'status': 'selected', 'reason': 'preferred' if top[0]['id'] == preferred else 'scope-and-priority',
                'collection': top[0]}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--state')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    watch = commands.add_parser('watch'); watch.add_argument('folder')
    configure = commands.add_parser('configure'); configure.add_argument('name'); configure.add_argument('patch')
    prefer = commands.add_parser('prefer'); prefer.add_argument('name')
    select = commands.add_parser('select')
    for arg in ('kind', 'institution', 'department', 'collection'):
        select.add_argument('--' + arg)
    args = parser.parse_args(); registry = Registry(state=args.state)
    if args.command == 'list': result = registry.sync()
    elif args.command == 'watch': result = registry.watch(args.folder)
    elif args.command == 'configure': result = registry.configure(args.name, h.read_json(args.patch))
    elif args.command == 'prefer': result = registry.prefer(None if args.name == 'auto' else args.name)
    else: result = registry.select(args.kind, args.institution, args.department, args.collection)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
