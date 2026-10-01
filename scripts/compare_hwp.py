import argparse,struct,zlib
from collections import Counter
from pathlib import Path
import olefile
import hangul as h

def stream_map(path):
    with olefile.OleFileIO(path) as f:return {'/'.join(p):f.openstream(p).read() for p in f.listdir()}
def compare(before,after):
    a,b=stream_map(before),stream_map(after);shared=set(a)&set(b)
    result={'before_sha256':h.digest(Path(before).read_bytes()),'after_sha256':h.digest(Path(after).read_bytes()),
      'removed_streams':sorted(set(a)-set(b)),'added_streams':sorted(set(b)-set(a)),
      'changed_streams':sorted(p for p in shared if a[p]!=b[p]),'unchanged_streams':sorted(p for p in shared if a[p]==b[p])}
    for name in ['DocInfo','BodyText/Section0']:
        def unpack(streams):
            flag=struct.unpack_from('<I',streams['FileHeader'],36)[0]
            return h.records(zlib.decompress(streams[name],-15) if flag&1 else streams[name])
        ar,br=unpack(a),unpack(b);ac,bc=Counter(r[0] for r in ar),Counter(r[0] for r in br)
        changed={tag:sum(x!=y for x,y in zip([r[4] for r in ar if r[0]==tag],[r[4] for r in br if r[0]==tag]))
            +abs(ac[tag]-bc[tag]) for tag in set(ac)|set(bc) if [r[4] for r in ar if r[0]==tag]!=[r[4] for r in br if r[0]==tag]}
        result[name]={'before_records':len(ar),'after_records':len(br),'changed_records_by_tag':changed,
            'character_shape_records_identical':[r[4] for r in ar if r[0]==68]==[r[4] for r in br if r[0]==68],
            'paragraph_headers_identical':[r[4] for r in ar if r[0]==66]==[r[4] for r in br if r[0]==66],
            'line_geometry_identical':[r[4] for r in ar if r[0]==69]==[r[4] for r in br if r[0]==69]}
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('before');p.add_argument('after');p.add_argument('--output');a=p.parse_args()
    r=compare(a.before,a.after)
    if a.output:h.write_json(a.output,r)
    print(__import__('json').dumps(r,ensure_ascii=False,indent=2))
