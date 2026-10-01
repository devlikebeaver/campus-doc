"""Meaningful regression checks: rich styles, glyphs, table spans and slot limits."""
import copy, tempfile
from pathlib import Path
import hangul as h

with tempfile.TemporaryDirectory(prefix='hangul-design-check-') as temp:
    temp=Path(temp)
    for variant in ['plan','report']:
        data=h.read_json(h.ROOT/'examples'/(variant+'-reference-data.json'))
        file=temp/(variant+'.hwpx');h.assemble(h.ROOT/'examples'/(variant+'-reference-data.json'),file)
        assert h.validate(file)['table_merge_coverage']=='passed'
        import zipfile
        with zipfile.ZipFile(file) as z:section=h.xml(z.read('Contents/section0.xml'))
        manifest=h.read_json(h.ROOT/'assets'/variant/'manifest.json')
        expected=[]
        for c in manifest['components']:
            f=h.xml((h.ROOT/'assets'/variant/'components'/(c['id']+'.xml')).read_bytes())
            expected.extend((r.get('charPrIDRef'),''.join(r.xpath('./hp:t/text()',namespaces=h.NS))) for r in f.xpath('.//hp:run',namespaces=h.NS))
        actual=[(r.get('charPrIDRef'),''.join(r.xpath('./hp:t/text()',namespaces=h.NS))) for r in section.xpath('//hp:run',namespaces=h.NS)]
        assert expected==actual,'Rich run or private glyph changed in generation'
        assert any('\uf06d' in t for _,t in actual),'Reference private-use glyph missing'
        bad=copy.deepcopy(data);bad['fields']['cover']['0']+=' EXCEEDS CAPACITY'
        h.write_json(temp/'bad.json',bad)
        try:h.assemble(temp/'bad.json',temp/'bad.hwpx')
        except ValueError:pass
        else:raise AssertionError('Oversized slot was accepted')
        print(variant+': rich runs/glyphs, style refs, merged tables, overflow guard passed')
print('All regression checks passed.')
