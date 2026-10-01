"""Source-specific SVG preview adapter. Document source bytes are never changed.
The fallback and bullet mapping are backed by the user's native Hancom PDF.
"""
import argparse,copy,json,subprocess
from pathlib import Path
from lxml import etree as E
import hangul as h
SVG='{http://www.w3.org/2000/svg}'

def adapt(svg_path,out_dir,add_page_numbers=False):
    src=E.parse(str(svg_path));root=src.getroot();dst=Path(out_dir);dst.mkdir(parents=True,exist_ok=True)
    pages=root.xpath('./svg:g[@data-page]',namespaces={'svg':SVG[1:-1]});log=[]
    for group in pages:
        page=int(group.get('data-page'));fresh=E.Element(SVG+'svg',nsmap={None:SVG[1:-1]})
        fresh.set('viewBox','0 0 595.28 841.88');fresh.set('width','595.28pt');fresh.set('height','841.88pt')
        fresh.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
        for d in root.findall(SVG+'defs'):fresh.append(copy.deepcopy(d))
        g=copy.deepcopy(group);g.attrib.pop('transform',None);fresh.append(g)
        font_changes=0;glyph_changes=0
        for el in g.iter():
            family=el.get('font-family','')
            if 'HY헤드라인M' in family:
                el.set('font-family',"'HCR Batang','함초롬바탕',serif");font_changes+=1
            if E.QName(el).localname=='text' and el.text and '\uf06d' in el.text:
                # Native PDF embeds Wingdings for U+F06D. A Unicode circle is NOT
                # equivalent. Use the exact original codepoint in that font only.
                pieces=el.text.split('\uf06d');el.text=pieces[0]
                for tail in pieces[1:]:
                    span=E.SubElement(el,SVG+'tspan',attrib={'font-family':'Wingdings'})
                    span.text='\uf06d';span.tail=tail
                glyph_changes+=1
        if add_page_numbers and page>1:
            t=E.SubElement(fresh,SVG+'text',x='297.64',y='817.2',fill='#000000',
                           attrib={'text-anchor':'middle','font-size':'8','font-family':'Malgun Gothic'})
            t.text=f'- {page} -'
        file=dst/f'page_{page:03}.svg';file.write_bytes(h.serialize(fresh))
        log.append({'page':page,'resolved_title_fonts':font_changes,'native_pdf_bullet_mappings':glyph_changes,
                    'page_number_added':add_page_numbers and page>1})
    h.write_json(dst/'adapter-qa.json',{'evidence':'User supplied native Hancom plan PDF, 2026-10-01',
                 'source_document_modified':False,'native_equivalence_claimed':False,'pages':log})
    return log

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('svg');p.add_argument('out_dir');p.add_argument('--page-numbers',action='store_true');a=p.parse_args()
    print(json.dumps(adapt(a.svg,a.out_dir,a.page_numbers),ensure_ascii=False))
