"""Reference-derived HWP/HWPX component system. No document macros are executed."""
import argparse, copy, hashlib, json, re, struct, subprocess, sys, zipfile, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_RUNTIME = ROOT / 'runtime' / 'python'
if LOCAL_RUNTIME.exists():
    sys.path.insert(0, str(LOCAL_RUNTIME))
from lxml import etree as E

NS = {'hp':'http://www.hancom.co.kr/hwpml/2011/paragraph',
      'hh':'http://www.hancom.co.kr/hwpml/2011/head',
      'hs':'http://www.hancom.co.kr/hwpml/2011/section'}
P = '{'+NS['hp']+'}'
PARSER = E.XMLParser(resolve_entities=False, no_network=True)

def read_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def write_json(path, value):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def xml(data): return E.fromstring(data,PARSER)
def serialize(root): return E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
def units_mm(n): return round(float(n)*25.4/7200,3)
def digest(data): return hashlib.sha256(data).hexdigest()
def safe_output(source, target):
    if Path(source).resolve()==Path(target).resolve(): raise ValueError('원본 덮어쓰기는 지원하지 않습니다.')
    Path(target).parent.mkdir(parents=True,exist_ok=True)

def engine():
    local=ROOT/'runtime/python'
    if local.exists(): sys.path.insert(0,str(local))
    from hwpx import HwpxDocument
    return HwpxDocument

def convert(source,target):
    safe_output(source,target)
    d=engine().open(source)
    d.save_to_path(target)
    return {'source':str(source),'output':str(target),'conversion':str(d.conversion_report)}

def tree_dict(el):
    return {'type':E.QName(el).localname,'attributes':dict(el.attrib),
            'children':[tree_dict(c) for c in el]}

def styles(header,section):
    fonts={f.get('lang'):{x.get('id'):x.get('face') for x in f} for f in header.xpath('//hh:fontface',namespaces=NS)}
    used_char={x.get('charPrIDRef') for x in section.xpath('//hp:run',namespaces=NS)}
    used_para={x.get('paraPrIDRef') for x in section.xpath('//hp:p',namespaces=NS)}
    chars={}
    for c in header.xpath('//hh:charPr',namespaces=NS):
        if c.get('id') not in used_char: continue
        ref=c.find('{'+NS['hh']+'}fontRef')
        chars[c.get('id')]={'font_pt':int(c.get('height'))/100,'color':c.get('textColor'),
            'bold':c.find('{'+NS['hh']+'}bold') is not None,
            'fonts':{lang:fonts.get(lang.upper(),{}).get(fid,fid) for lang,fid in ref.attrib.items()},
            'definition':tree_dict(c)}
    paras={c.get('id'):tree_dict(c) for c in header.xpath('//hh:paraPr',namespaces=NS) if c.get('id') in used_para}
    borders={c.get('id'):tree_dict(c) for c in header.xpath('//hh:borderFill',namespaces=NS)}
    page=section.find('.//'+P+'pagePr')
    return {'fonts':fonts,'character_styles':chars,'paragraph_styles':paras,'border_fills':borders,
            'page_raw':tree_dict(page),'paper_mm':[units_mm(page.get('width')),units_mm(page.get('height'))]}

GROUPS={
 'plan':[(0,44,'cover','표지',1),(44,46,'body-title','본문 제목 띠',2),
 (46,47,'heading-purpose','번호 제목 · 목적',2),(47,51,'purpose','목적 본문',2),
 (51,52,'heading-overview','번호 제목 · 개요',2),(52,62,'overview','개요 · 들여쓰기 · 강조',2),
 (62,63,'schedule-lecture','특강 일정 · 9열',2),(63,64,'schedule-consult','대면 일정 · 9열',3),
 (64,65,'schedule-remote','비대면 일정 · 9열',3),(65,67,'page4-spacer','4쪽 이미지 · 간격',4),
 (67,68,'heading-effects','번호 제목 · 기대 효과',4),(68,75,'effects','기대 효과 본문',4),
 (75,76,'heading-budget','번호 제목 · 예산',4),(76,77,'budget-label','예산 설명',4),
 (77,78,'budget-table','예산 · 6열',4),(78,80,'budget-notes','예산 주석',4)],
 'report':[(0,44,'cover','표지',1),(44,46,'body-title','본문 제목 띠',2),
 (46,47,'heading-purpose','번호 제목 · 목적',2),(47,51,'purpose','목적 본문',2),
 (51,52,'heading-overview','번호 제목 · 개요',2),(52,63,'overview','개요 · 성과 지표',2),
 (63,64,'schedule-lecture','특강 실적 · 11열',2),(64,65,'schedule-consult','대면 실적 · 11열',3),
 (65,66,'schedule-remote','비대면 실적 · 11열',3),(66,67,'page4-spacer','4쪽 간격',4),
 (67,68,'heading-effects','번호 제목 · 운영 효과',4),(68,75,'effects','운영 효과 본문',4),
 (75,76,'heading-performance','번호 제목 · 운영 성과',4),(76,87,'performance','학과별 성과',4),
 (87,88,'satisfaction-label','만족도 설명',4),(88,89,'satisfaction-table','만족도 · 3열',4),
 (89,92,'opinions-label','기타 의견 · 5쪽 시작',5),(92,94,'opinions','의견 상자',5),
 (94,95,'heading-budget','번호 제목 · 집행 예산',5),(95,96,'budget-label','예산 설명',5),
 (96,97,'budget-table','집행 예산 · 6열',5),(97,99,'budget-notes','예산 주석',5),
 (99,103,'attachments','첨부 목록',5)]}

def table_info(t):
    cells=[]
    for c in t.xpath('./hp:tr/hp:tc',namespaces=NS):
        record={'borderFillIDRef':c.get('borderFillIDRef')}
        for name in ['cellAddr','cellSpan','cellSz','cellMargin','subList']:
            el=c.find(P+name)
            if el is not None: record[name]=dict(el.attrib)
        record['text']=''.join(c.xpath('.//hp:t/text()',namespaces=NS))
        cells.append(record)
    return {'id':t.get('id'),'rows':int(t.get('rowCnt')),'columns':int(t.get('colCnt')),
            'settings':dict(t.attrib),'size':dict(t.find(P+'sz').attrib),
            'position':dict(t.find(P+'pos').attrib),'cells':cells}

def extract(source,variant):
    """Decompose the section; new documents are assembled from these fragments."""
    dst=ROOT/'assets'/variant; (dst/'components').mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(source) as z:
        parts={n:z.read(n) for n in z.namelist()}
    section=xml(parts.pop('Contents/section0.xml')); header=xml(parts['Contents/header.xml'])
    # Do not carry a stale preview or executable scripts into a new document.
    for n in list(parts):
        if n.startswith('Preview/') or n.startswith('Scripts/'): parts.pop(n)
    with zipfile.ZipFile(dst/'package-base.zip','w',zipfile.ZIP_DEFLATED) as z:
        for n,b in parts.items(): z.writestr(n,b,compress_type=zipfile.ZIP_STORED if n=='mimetype' else zipfile.ZIP_DEFLATED)
    top=list(section); manifest={'variant':variant,'namespace_map':section.nsmap,
        'section_attributes':dict(section.attrib),'source_hwpx_sha256':digest(Path(source).read_bytes()),
        'page_count_reference':4 if variant=='plan' else 5,'components':[],
        'rules':{'style_namespace':variant,'preserve_rich_runs':True,'mix_variants_without_style_remap':False,
                 'growth_requires_reflow_and_render':True,'reference_pagination_is_cached':True}}
    fields={}; field_meta={}
    for start,end,key,label,page in GROUPS[variant]:
        fragment=E.Element('component',id=key)
        for p in top[start:end]: fragment.append(copy.deepcopy(p))
        (dst/'components'/(key+'.xml')).write_bytes(serialize(fragment))
        ts=fragment.xpath('.//hp:t',namespaces=NS)
        fields[key]={str(i):(t.text or '') for i,t in enumerate(ts)}
        field_meta[key]={str(i):{'char_style':t.getparent().get('charPrIDRef'),
            'source_utf16_units':len((t.text or '').encode('utf-16le'))//2,
            'in_table':bool(t.xpath('ancestor::hp:tc',namespaces=NS))} for i,t in enumerate(ts)}
        manifest['components'].append({'id':key,'label':label,'page':page,'paragraphs':end-start,
          'source_top_paragraphs':[start,end-1],'text_slots':len(ts),
          'char_styles':sorted({r.get('charPrIDRef') for r in fragment.xpath('.//hp:run',namespaces=NS)}),
          'tables':[table_info(t) for t in fragment.xpath('.//hp:tbl',namespaces=NS)],
          'pictures':[tree_dict(p) for p in fragment.xpath('.//hp:pic',namespaces=NS)],
          'paragraph_geometry':[{'properties':dict(p.attrib),
              'line_cache':[dict(l.attrib) for l in p.xpath('./hp:linesegarray/hp:lineseg',namespaces=NS)]} for p in fragment]})
    write_json(dst/'manifest.json',manifest)
    write_json(dst/'tokens.json',styles(header,section))
    write_json(dst/'field-schema.json',field_meta)
    write_json(ROOT/'examples'/(variant+'-reference-data.json'),{'variant':variant,'mode':'reference','fields':fields})
    return manifest

def assemble(data_path,target):
    data=read_json(data_path); variant=data['variant']; dst=ROOT/'assets'/variant
    m=read_json(dst/'manifest.json'); section=E.Element('{'+NS['hs']+'}sec',nsmap=m['namespace_map'],**m['section_attributes'])
    changes=[]
    for component in m['components']:
        key=component['id']; f=xml((dst/'components'/(key+'.xml')).read_bytes())
        ts=f.xpath('.//hp:t',namespaces=NS); values=data['fields'][key]
        if set(values)!={str(i) for i in range(len(ts))}: raise ValueError('슬롯 불일치: '+key)
        for i,t in enumerate(ts):
            old=t.text or ''; new=values[str(i)]
            if not isinstance(new,str): raise ValueError('본문 값은 문자열이어야 합니다.')
            if old==new: continue
            # Longer or different-width glyphs still require a rendered comparison.
            # Reject code-unit growth in fixed mode rather than silently overflowing.
            if len(new.encode('utf-16le'))>len(old.encode('utf-16le')):
                raise ValueError('고정 양식 슬롯 초과: '+key+'/'+str(i)+'; reflow 편집을 사용하세요.')
            t.text=new
            changes.append({'component':key,'slot':i,'before':old,'after':new})
        for p in list(f): section.append(p)
    safe_output(dst/'package-base.zip',target)
    with zipfile.ZipFile(dst/'package-base.zip') as base,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for info in base.infolist():
            content=base.read(info.filename)
            if info.filename=='Contents/header.xml' and data.get('theme'):
                head=xml(content)
                theme=data['theme']
                for e in head.iter():
                    for attr,value in list(e.attrib.items()):
                        if attr in {'textColor','color','faceColor','hatchColor'}:
                            color=theme.get('colors',{}).get(value)
                            if color:
                                if not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('색상은 #RRGGBB 형식입니다.')
                                e.set(attr,color)
                        elif attr=='face' and E.QName(e).localname=='font':
                            e.set(attr,theme.get('fonts',{}).get(value,value))
                        elif attr=='width' and E.QName(e).localname.endswith('Border'):
                            width=theme.get('line_widths',{}).get(value)
                            if width:
                                if not re.fullmatch(r'\d+(?:\.\d+)? mm',width):raise ValueError('선 굵기는 mm 단위입니다.')
                                e.set(attr,width)
                content=serialize(head)
            z.writestr(info,content)
        z.writestr('Contents/section0.xml',serialize(section))
        z.writestr('Preview/PrvText.txt','\n'.join(section.xpath('//hp:t/text()',namespaces=NS)).encode('utf-8'))
    result={'variant':variant,'components_assembled':len(m['components']),'changes':changes,'theme':data.get('theme',{}),
            'source_document_read_at_generation':False,'native_hancom_verified':False}
    write_json(str(target)+'.qa.json',result)
    return result

def edit_hwpx(source,target,edits):
    safe_output(source,target); d=engine().open(source); hits=[]
    for edit in read_json(edits):
        old,new=edit['old'],edit['new']; expected=edit.get('count',1)
        # Count by running on a throw-away deep conversion is unnecessary; this API
        # exposes exact count. Never accept a partial/ambiguous operation silently.
        n=d.text.replace(old,new,limit=expected,everywhere=True)
        if n!=expected: raise ValueError(f'치환 건수 {n}, 예상 {expected}: {old}')
        hits.append({'old':old,'new':new,'count':n})
    report=d.save_to_path(target,mode='patch',fallback='error',return_report=True)
    result={'edits':hits,'engine_report':str(report),'native_hancom_verified':False}
    write_json(str(target)+'.qa.json',result)
    return result

def records(data):
    out=[]; pos=0
    while pos<len(data):
        start=pos
        if pos+4>len(data): raise ValueError('HWP 레코드 헤더가 잘렸습니다.')
        h=struct.unpack_from('<I',data,pos)[0]; pos+=4; size=h>>20
        if size==4095:
            size=struct.unpack_from('<I',data,pos)[0];pos+=4
        if pos+size>len(data): raise ValueError('HWP 레코드 내용이 잘렸습니다.')
        out.append((h&1023,(h>>10)&1023,start,pos,data[pos:pos+size]));pos+=size
    return out

def plain_spans(payload):
    if len(payload)%2:raise ValueError('홀수 길이 UTF-16 레코드')
    units=list(struct.unpack('<'+'H'*(len(payload)//2),payload)); spans=[];begin=0;i=0
    while i<len(units):
        if units[i]<32:
            if begin<i:spans.append((begin,i))
            i+=8 if units[i] in {1,2,3,11,12,14,15,16,17,18,21,22,23} else 1
            begin=i
        else:i+=1
    if begin<len(units):spans.append((begin,len(units)))
    return spans

def extract_hwp(source,variant):
    import olefile
    dst=ROOT/'assets'/variant/'binary';dst.mkdir(parents=True,exist_ok=True)
    with olefile.OleFileIO(source) as o:
        streams={'/'.join(p):o.openstream(p).read() for p in o.listdir()}
    flags=struct.unpack_from('<I',streams['FileHeader'],36)[0]
    if flags & (2|4|256):raise ValueError('지원하지 않는 보호 형식')
    section=streams.pop('BodyText/Section0');raw=zlib.decompress(section,-15) if flags&1 else section
    rs=records(raw);starts=[r[2] for r in rs if r[0]==66 and r[1]==0]
    if len(starts)!=GROUPS[variant][-1][1]:raise ValueError('원본 최상위 문단 수 불일치: '+str(len(starts)))
    if starts[0]!=0:raise ValueError('문단 앞 섹션 레코드를 별도로 처리해야 합니다.')
    starts.append(len(raw))
    streams.pop('PrvImage',None)
    write_json(dst/'package-streams.json',{k:v.hex() for k,v in streams.items()})
    schema={};data={};layout={'variant':variant,'flags':flags,'components':[],'source_sha256':digest(Path(source).read_bytes())}
    for a,b,key,label,page in GROUPS[variant]:
        blob=raw[starts[a]:starts[b]];(dst/(key+'.bin')).write_bytes(blob)
        data[key]={};schema[key]={}
        for ri,r in enumerate(records(blob)):
            if r[0]!=67:continue
            for si,(x,y) in enumerate(plain_spans(r[4])):
                text=r[4][2*x:2*y].decode('utf-16le');slot=f'{ri}:{si}'
                data[key][slot]=text;schema[key][slot]={'record':ri,'units':[x,y],'max_utf16_units':y-x}
        layout['components'].append({'id':key,'page':page,'label':label,'fragment_bytes':len(blob)})
    write_json(dst/'manifest.json',layout);write_json(dst/'field-schema.json',schema)
    write_json(ROOT/'examples'/(variant+'-binary-reference-data.json'),{'variant':variant,'fields':data})
    return {'components':len(layout['components']),'top_paragraphs':len(starts)-1}

def assemble_hwp(data_path,target,node='node'):
    """Create an OLE document from native paragraph fragments and styled fields."""
    data=read_json(data_path);variant=data['variant'];dst=ROOT/'assets'/variant/'binary'
    manifest=read_json(dst/'manifest.json');schema=read_json(dst/'field-schema.json');parts=[];edits=[];all_text=[]
    for c in manifest['components']:
        key=c['id'];blob=(dst/(key+'.bin')).read_bytes();buf=bytearray(blob);rs=records(blob)
        if set(data['fields'][key])!=set(schema[key]):raise ValueError('HWP 입력 슬롯 불일치: '+key)
        for slot,meta in schema[key].items():
            value=data['fields'][key][slot];r=rs[meta['record']];x,y=meta['units'];old=r[4][x*2:y*2].decode('utf-16le')
            if len(value.encode('utf-16le'))>(y-x)*2:raise ValueError('HWP 고정 슬롯 길이 초과: '+key+'/'+slot)
            if any(ord(ch)<32 for ch in value):raise ValueError('본문 슬롯에 제어문자는 허용되지 않습니다.')
            filled=value+' '*((y-x)-len(value.encode('utf-16le'))//2)
            if old!=filled:edits.append({'component':key,'slot':slot,'before':old,'after':filled})
            buf[r[3]+x*2:r[3]+y*2]=filled.encode('utf-16le');all_text.append(value)
        after=records(bytes(buf));assert all(a[4]==b[4] for a,b in zip(rs,after) if a[0]!=67)
        parts.append(bytes(buf))
    streams=read_json(dst/'package-streams.json');raw=b''.join(parts)
    if manifest['flags']&1:
        co=zlib.compressobj(9,zlib.DEFLATED,-15);body=co.compress(raw)+co.flush()
    else:body=raw
    streams['BodyText/Section0']=body.hex();streams['PrvText']='\r\n'.join(all_text).encode('utf-16le').hex()
    Path(target).parent.mkdir(parents=True,exist_ok=True)
    recipe=Path(str(target)+'.streams.json');write_json(recipe,streams)
    subprocess.run([node,str(ROOT/'scripts/ole_create.cjs'),str(target),str(recipe)],check=True);recipe.unlink()
    result={'variant':variant,'components_assembled':len(parts),'changed_text_spans':len(edits),
        'edits':edits,'all_nontext_records_identical_to_fragments':True,'style_header_native_bytes_retained':True,
        'source_file_opened_during_generation':False,'stale_cover_preview_removed':True,'native_visual_comparison':'pending'}
    write_json(str(target)+'.qa.json',result);return result

def edit_hwp_fixed(source,target,edits,node='node'):
    """Same UTF-16 length only: change paragraph text bytes, retain every shape record."""
    import olefile
    safe_output(source,target)
    rules=read_json(edits)
    for r in rules:
        if not r['old'] or len(r['old'].encode('utf-16le'))!=len(r['new'].encode('utf-16le')):
            raise ValueError('HWP 고정 편집은 같은 UTF-16 길이만 허용합니다. 길이 변경은 HWPX reflow 경로를 사용하세요.')
        if any(ord(c)<32 for c in r['old']+r['new']): raise ValueError('제어문자는 편집하지 않습니다.')
    changed={}; events=[]; counts=[0]*len(rules)
    with olefile.OleFileIO(source) as o:
        header=o.openstream('FileHeader').read(); flags=struct.unpack_from('<I',header,36)[0]
        if flags & (2|4|256): raise ValueError('암호화/배포용/전자서명 문서는 이 경로로 수정하지 않습니다.')
        for path in o.listdir(streams=True,storages=False):
            name='/'.join(path)
            if not name.startswith('BodyText/Section'): continue
            packed=o.openstream(path).read(); raw=zlib.decompress(packed,-15) if flags&1 else packed
            rs=records(raw); buf=bytearray(raw)
            for j,(tag,level,start,offset,b) in enumerate(rs):
                if tag!=67: continue
                # Locate matches in plain UTF-16 spans only. Control data is opaque.
                spans=plain_spans(b)
                for ri,r in enumerate(rules):
                    if counts[ri]>=r.get('count',1): continue
                    needle=r['old'].encode('utf-16le'); replacement=r['new'].encode('utf-16le')
                    for a,c in spans:
                        current=bytes(buf[offset+a*2:offset+c*2]); where=current.find(needle)
                        while where>=0 and counts[ri]<r.get('count',1):
                            if where%2: raise ValueError('UTF-16 비정렬 일치')
                            at=offset+a*2+where;buf[at:at+len(needle)]=replacement
                            counts[ri]+=1;events.append({'stream':name,'record':j,'utf16_offset':a+where//2,'old':r['old'],'new':r['new']})
                            where=current.find(needle,where+len(needle))
            if bytes(buf)!=raw:
                # Exact invariant: all non-text records are byte-identical.
                after=records(bytes(buf))
                assert len(rs)==len(after)
                assert all(a[4]==b[4] for a,b in zip(rs,after) if a[0]!=67)
                if flags&1:
                    co=zlib.compressobj(9,zlib.DEFLATED,-15); changed[name]=(co.compress(buf)+co.flush()).hex()
                else: changed[name]=bytes(buf).hex()
        if counts!=[r.get('count',1) for r in rules]: raise ValueError('치환 건수 불일치: '+str(counts))
        # Update text preview; keep the cover bitmap, since edits in this path do
        # not target the cover in tested fixtures. QA explicitly exposes its status.
        if o.exists('PrvText'):
            prev=o.openstream('PrvText').read().decode('utf-16le')
            for r in rules: prev=prev.replace(r['old'],r['new'],r.get('count',1))
            changed['PrvText']=prev.encode('utf-16le').hex()
    recipe=Path(str(target)+'.streams.json');write_json(recipe,changed)
    subprocess.run([node,str(ROOT/'scripts/ole_patch.cjs'),str(source),str(target),str(recipe)],check=True)
    recipe.unlink()
    result={'edits':events,'all_nontext_records_identical':True,'glyphs_and_character_runs_preserved':True,
        'changed_streams':list(changed),'cover_preview_regenerated':False,'native_hancom_verified':False}
    write_json(str(target)+'.qa.json',result);return result

def validate(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        h=xml(z.read('Contents/header.xml'));s=xml(z.read('Contents/section0.xml'))
        known={e.get('id') for e in h.xpath('//hh:charPr',namespaces=NS)}
        missing={r.get('charPrIDRef') for r in s.xpath('//hp:run',namespaces=NS)}-known
        if missing: raise ValueError('글자 스타일 참조 누락: '+str(missing))
        para={e.get('id') for e in h.xpath('//hh:paraPr',namespaces=NS)}
        assert not ({r.get('paraPrIDRef') for r in s.xpath('//hp:p',namespaces=NS)}-para)
        for table in s.xpath('//hp:tbl',namespaces=NS):
            rows,cols=int(table.get('rowCnt')),int(table.get('colCnt'));occupied=set()
            for cell in table.xpath('./hp:tr/hp:tc',namespaces=NS):
                a=cell.find(P+'cellAddr');b=cell.find(P+'cellSpan')
                x,y=int(a.get('colAddr')),int(a.get('rowAddr'));w,t=int(b.get('colSpan')),int(b.get('rowSpan'))
                assert 0<=x<x+w<=cols and 0<=y<y+t<=rows
                for yy in range(y,y+t):
                    for xx in range(x,x+w):
                        assert (xx,yy) not in occupied, '셀 중첩';occupied.add((xx,yy))
            assert len(occupied)==rows*cols,'병합 셀 커버리지 누락'
        return {'zip_crc':'passed','xml':'passed','style_refs':'passed','table_merge_coverage':'passed',
            'tables':len(s.xpath('//hp:tbl',namespaces=NS)),'native_layout':'not_verified'}

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('convert');c.add_argument('source');c.add_argument('target')
    c=sub.add_parser('extract');c.add_argument('source');c.add_argument('variant',choices=['plan','report'])
    c=sub.add_parser('extract-hwp');c.add_argument('source');c.add_argument('variant',choices=['plan','report'])
    c=sub.add_parser('generate');c.add_argument('data');c.add_argument('target')
    c=sub.add_parser('generate-hwp');c.add_argument('data');c.add_argument('target');c.add_argument('--node',default='node')
    for name in ['edit-hwpx','edit-hwp-fixed']:
        c=sub.add_parser(name);c.add_argument('source');c.add_argument('target');c.add_argument('edits')
        if name=='edit-hwp-fixed': c.add_argument('--node',default='node')
    c=sub.add_parser('validate');c.add_argument('source')
    a=p.parse_args()
    if a.cmd=='convert':result=convert(a.source,a.target)
    elif a.cmd=='extract':result=extract(a.source,a.variant)
    elif a.cmd=='extract-hwp':result=extract_hwp(a.source,a.variant)
    elif a.cmd=='generate':result=assemble(a.data,a.target)
    elif a.cmd=='generate-hwp':result=assemble_hwp(a.data,a.target,a.node)
    elif a.cmd=='edit-hwpx':result=edit_hwpx(a.source,a.target,a.edits)
    elif a.cmd=='edit-hwp-fixed':result=edit_hwp_fixed(a.source,a.target,a.edits,a.node)
    else:result=validate(a.source)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
