# 자연어로 사용하는 다섯 가지 기능

사용자가 설명하는 대상이 컴포넌트인지, 양식인지, 작성된 문서의 내용인지를
먼저 대화 맥락으로 구분한다. 아래 명령과 JSON은 에이전트의 내부 인터페이스다.
사용자에게 코드, 슬롯 번호, 스타일 ID를 작성하게 하지 않는다.

| 기능 | 자연어 요청 예 | 저장되는 결과 |
|---|---|---|
| 컴포넌트 추가 | “이 제목 모양으로 추진 일정 제목도 만들어줘.” | 재사용 가능한 새 컴포넌트 |
| 컴포넌트 수정 | “추진 일정 제목 컴포넌트의 색을 초록으로 바꿔줘.” | 해당 컴포넌트의 새 버전 |
| 예시 양식 | “운영계획서와 결과보고서 예시를 보여줘.” | 사용할 수 있는 조합과 기본 내용 |
| 양식 생성·수정 | “표지, 목적, 일정표, 예산표 순서로 양식 만들어줘.” | 순서·페이지 구분·컴포넌트 버전을 지정한 양식과 문서 |
| 내용 수정 | “이번 문서의 추진 일정 제목을 검토 항목으로 바꿔줘.” | 해당 문서만 수정한 사본 |

## 컴포넌트

`scripts/library.py`는 기본 라이브러리(plan 16개, report 23개)와 사용자 라이브러리를
함께 조회한다. 새로운 컴포넌트는 기존 컴포넌트 복제, 같은 스타일 기준을 사용하는
XML 가져오기, 새 문단·글자 run 작성으로 추가할 수 있다. 표·도형은 기존 컴포넌트의
구조를 복제하거나 XML을 준비한다. 임의 표 설계나 다른 기관 CI 가져오기가 모두
자동 구현되었다고 설명하지 않는다.

수정할 때 기존 버전을 덮어쓰지 않고 새 버전을 저장한다. `expected_revision`은
오래된 버전을 기준으로 한 수정을 막는다. 글자·문단·테두리 정의를 바꿀 때는
해당 컴포넌트가 쓰는 스타일 정의를 복제하고 참조를 다시 연결한다. 같은 원본
스타일 번호를 쓰는 다른 컴포넌트까지 바꾸지 않는다.

컴포넌트의 글꼴 참조, 크기, 자간, 장평, 색상, 문단 속성, 테두리 속성은 HWPX의
실제 정의를 수정한다. 예를 들어 글자 크기 16pt는 `charPr`의 `height="1600"`이다.
정의에 없는 속성, 다른 스타일 기준의 ID, 없는 이미지 자원을 조용히 허용하지 않는다.
Wingdings U+F06D 불렛과 여러 run의 서로 다른 글꼴을 일괄 정규화하지 않는다.

```text
python -X utf8 scripts/library.py catalog
python -X utf8 scripts/library.py add-component examples/component-add.json
python -X utf8 scripts/library.py edit-component plan example-heading examples/component-edit.json
python -X utf8 scripts/library.py add-component examples/new-paragraph.json
```

## 예시 양식과 양식 생성

기본 예시는 `plan-reference`, `report-reference`다. 공개 예시는 익명 HWPX 컴포넌트다. 네이티브 HWP 생성은 사용자가 자기 문서에서 추출한 바이너리 자원이 있을 때 사용한다.

새 양식은 컴포넌트 인스턴스 목록으로 저장한다. 같은 일정표를 여러 번 넣어도
문서 내 개체 ID를 새로 배정한다. 동일 컴포넌트의 서로 다른 내용은 인스턴스별로
관리한다. `page_break_before`로 명시적인 페이지 구분을 지정할 수 있다.
페이지·헤더 설정을 가진 컴포넌트는 맨 앞에 한 번 포함한다.

컴포넌트 버전은 양식에 고정한다. 컴포넌트 수정만으로 이전 양식과 기존 문서가
바뀌지 않는다. “모든 양식에 적용”을 요청하면 해당 양식들의 컴포넌트 버전을
갱신하여 각각 새 양식 버전을 저장한다.

```text
python -X utf8 scripts/library.py save-template examples/template-library.json
python -X utf8 scripts/library.py form-data plan example-form DOCUMENT-DATA.json
python -X utf8 scripts/library.py compose DOCUMENT-DATA.json OUTPUT.hwpx
```

사용자 라이브러리 경로는 `--state DIRECTORY`로 지정할 수 있다. 다른 사람에게
배포할 때는 개인 라이브러리와 배포된 기본 컴포넌트를 구분하고, 하드코딩된
개인 PC 경로를 사용하지 않는다.

## 내용 수정

생성한 문서의 내용은 별도 데이터로 관리한다. `edit-content`는 수정 전 내용이
예상과 일치하는지 확인하고, 문서와 갱신된 `.data.json`을 생성한다. 컴포넌트와
양식의 저장된 버전은 바꾸지 않는다.

```text
python -X utf8 scripts/library.py edit-content DOCUMENT-DATA.json examples/content-edit.json UPDATED.hwpx
```

외부 HWP/HWPX는 기존 `hangul.py edit-hwp-fixed` 또는 `edit-hwpx`로 수정한다.
자연어 요청이 어느 파일의 어느 내용인지 불명확할 때만 그 대상을 확인한다.

## 현재 실행·검증 범위

컴포넌트 관리와 새 조합은 HWPX 경로에서 구현했다. 원본 네이티브 HWP 유지 경로는
기존 생성·수정 기능을 사용한다. HWPX를 HWP로 저장하는 별도 모델 직렬화를 원본
바이너리와 동등하다고 설명하지 않는다.

새 순서나 변경된 내용에 원본의 오래된 줄 위치를 강제로 적용하지 않는다. 이 경로는
줄 캐시를 제거하여 재조판 대상으로 저장한다. 따라서 구조 검사 통과가 원본과 같은
자간·페이지 수·표 높이를 뜻하지 않는다. 한컴에서의 렌더링과 비교는 별도 검증이다.

`check_library.py`는 새 문단 생성, 컴포넌트 버전, 양식 버전 고정, 다른 컴포넌트와
스타일 분리, 개체 ID 중복 방지, 문서 내용만 수정, 버전 충돌·참조 오류 거부,
계획서·보고서 조합, 기본 자원 불변을 실제 파일로 검사한다.

Gemini 앱에서 GitHub URL과 설정 프롬프트만으로 설치·실행하는 과정은 아직 검증하지
않았다. 대화 입력, 라이브러리 구현, Gemini 앱 배포를 각각의 완료 상태로 보고한다.
