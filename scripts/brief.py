"""Track a semantic brief collected in natural-language conversation.
This is an intake contract, not a claim that arbitrary layouts already render.
"""
import argparse, json
from pathlib import Path
import hangul as h

def next_step(brief):
    identity=brief.get('identity',{});cover=brief.get('cover',{});body=brief.get('body',{})
    missing=[x for x in ['institution','department'] if not identity.get(x)]
    if missing:
        return {'stage':'identity','missing':missing,'question':'기관명과 부서명을 알려주세요.'}
    if identity.get('header_mode') not in ['ci','text']:
        return {'stage':'identity','missing':['header_mode'],'question':'기관 CI를 사용할까요, 기관명만 헤더에 넣을까요?'}
    if identity['header_mode']=='ci' and not identity.get('ci_path'):
        return {'stage':'identity','missing':['ci_path'],'question':'사용할 기관 CI 파일을 보내주세요.','text_only_question_tool':False}
    if not cover.get('title_lines'):
        return {'stage':'cover','missing':['title_lines'],'question':'첫 페이지 제목을 알려주세요. 줄을 나눌 위치도 지정할 수 있습니다.'}
    if not isinstance(cover['title_lines'],list) or not all(isinstance(t,str) and t.strip() for t in cover['title_lines']):
        raise ValueError('표지 제목은 비어 있지 않은 줄의 목록이어야 합니다.')
    if 'date' not in cover:
        return {'stage':'cover','missing':['date'],'question':'표지에 넣을 날짜를 알려주세요. 날짜를 빼도 됩니다.'}
    if not body.get('title'):
        return {'stage':'body-title','missing':['title'],'question':'두 번째 페이지 제목은 무엇으로 할까요? 표지 제목과 같아도 됩니다.'}
    sections=body.get('sections',[])
    if not sections:
        return {'stage':'outline','missing':['sections'],'question':'목차에 넣을 항목을 순서대로 알려주세요. 예: 목적, 개요, 일정, 예산.'}
    if body.get('toc_mode') not in ['section-order','separate-page']:
        return {'stage':'outline','missing':['toc_mode'],'question':'말씀하신 목차를 본문 항목 순서로 쓸까요, 별도의 목차 페이지로 넣을까요?'}
    ids=[]
    for i,section in enumerate(sections):
        if not section.get('title'):raise ValueError('제목 없는 목차 항목: '+str(i))
        sid=section.get('id',str(i));ids.append(sid)
        if 'content' not in section:
            return {'stage':'content','section_id':sid,'missing':['content'],
                    'question':f'“{section["title"]}”에 넣을 내용을 알려주세요. 빈 입력란으로 남겨도 됩니다.'}
        if not isinstance(section['content'],list):raise ValueError('섹션 내용은 본문/불렛/표 블록 목록이어야 합니다.')
        for block in section['content']:
            if block.get('type') not in ['paragraph','bullets','table','note','blank']:
                raise ValueError('지원하지 않는 내용 블록: '+str(block.get('type')))
            if block['type']=='table':
                headers=block.get('headers',[]);rows=block.get('rows',[])
                if not headers or any(len(row)!=len(headers) for row in rows):raise ValueError('표의 열 수가 맞지 않습니다.')
    if len(ids)!=len(set(ids)):raise ValueError('섹션 ID가 중복되었습니다.')
    return {'stage':'ready-for-composition','intake_complete':True,'file_generated':False,
            'summary':{'institution':identity['institution'],'department':identity['department'],
                'cover_title_lines':cover['title_lines'],'body_title':body['title'],
                'section_order':[s['title'] for s in sections],'toc_mode':body['toc_mode']},
            'next_action':'Apply the brief to actual components and verify the generated document.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('brief');p.add_argument('--output');a=p.parse_args()
    result=next_step(h.read_json(a.brief))
    if a.output:h.write_json(a.output,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
