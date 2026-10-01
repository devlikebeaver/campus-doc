# 에이전트를 위한 설치와 준비

이 문서는 다음 Raw 주소로 독립적으로 읽을 수 있습니다.

https://raw.githubusercontent.com/devlikebeaver/campus-doc/main/docs/installation.md

사용자가 준비를 요청하면 기존 정보와 실제 도구를 사용해 진행합니다.
실행 능력이 확인되지 않은 앱에 다른 제품이나 CLI 설치를 임의로 요구하지 않습니다.

## 1. 실제 환경 확인

- URL을 읽을 수 있는가?
- 저장소 ZIP을 내려받고 압축을 풀거나 Git clone할 수 있는가?
- 작업 파일을 읽고 쓸 수 있는가?
- PowerShell 또는 Python 프로그램을 실행할 수 있는가?
- 생성 파일을 사용자에게 반환할 수 있는가?

도구 목록, 실제 호출 또는 오류로 확인합니다. AI의 이름이나 구독 여부만으로 추정하지 않습니다.
대화만 가능한 환경이라면 지원되는 단계와 부족한 도구를 정확히 알립니다.
파일 접근/실행이 불가능한 환경에서 사용자 PC에 설치됐다고 보고하지 않습니다.

## 2. 저장소 확보

원본 문서와 분리된 사용자 작업 폴더를 사용합니다.

```sh
git clone https://github.com/devlikebeaver/campus-doc.git
```

Git이 없으면 다음 ZIP을 내려받아 압축을 풉니다.

https://github.com/devlikebeaver/campus-doc/archive/refs/heads/main.zip

이미 받아 둔 campus-doc이 있으면 그 폴더를 확인하고 재사용합니다.
사용자 추가 양식과 `library/`를 지우고 새로 설치하지 않습니다.
셋업·의존성·결과 파일은 저장소의 `runtime/` 아래로 분리합니다.

## 3. 실행 환경 준비

### Windows 10/11 x64

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

또는 사용자가 압축을 푼 폴더의 `SETUP.cmd`를 두 번 클릭합니다.

이 경로는 시스템에 Python/Node가 없어도 다음을 프로젝트 폴더에 준비합니다.

- Python 3.13.16 embeddable x64
- Node 22.23.3 x64 실행 파일
- python-hwpx 6.6.0, lxml 6.1.3, olefile 0.47의 고정 wheel

공식 Python·Node 배포와 PyPI 파일을 사용합니다. URL과 SHA-256은
`scripts/windows-runtime.json`에 고정합니다. 해시가 다르면 실행 전에 중지합니다.
PowerShell의 실행 정책 옵션은 해당 실행 프로세스에만 적용합니다.
전역 PATH, 레지스트리, 기존 Python 패키지를 변경하지 않습니다.

준비한 런타임을 사용하는 호출:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1 doctor.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1 registry.py list
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1 library.py catalog
```

파일 경로는 PowerShell 인자로 정확하게 전달합니다. 사용자 입력을 셸 코드에 이어 붙이지 않습니다.

### 기존 Python / Linux / macOS

Python 3.13과 pip가 있으면 다음을 실행합니다.

```sh
python scripts/setup.py
python scripts/doctor.py
python scripts/smoke.py
```

`setup.py`는 `requirements.txt`를 `runtime/python`에 설치합니다.
기존 Python 환경을 변경하는 전역 설치를 하지 않습니다.
Node가 없으면 native HWP 바이너리 경로를 준비 완료로 보고하지 않습니다.
HWPX만 요청한 경우 사용 가능한 경로로 진행할 수 있습니다.
Windows 외 환경의 전체 런타임 설치 자동화는 제공하지 않습니다.

## 4. 준비 성공을 증명

Windows bootstrap은 doctor와 smoke를 함께 실행합니다.

- `runtime/setup-status.json`: 실제 import 가능 여부, 버전, HWPX/HWP 실행 가능 상태
- `runtime/smoke-result.json`: 두 HWPX 생성, HWPX 편집, 합성 HWP 고정 길이 편집 결과
- `runtime/samples/`: 생성 파일과 각 QA 파일

파일이 실제로 존재하고 검사 결과가 성공인지 확인합니다.
오류가 있으면 원인을 해결한 뒤 해당 검사만 재실행합니다.
다운로드·압축 해제 성공만으로 문서 엔진 준비를 완료 처리하지 않습니다.

전체 회귀 검사가 필요한 코드 변경에는 다음을 실행합니다.

```sh
python scripts/check.py
python scripts/check_library.py
python scripts/check_registry.py
```

Windows portable 경로에서는 `scripts/run.ps1`을 통해 같은 스크립트를 실행합니다.

## 5. 스킬 사용과 다음 작업

이 저장소 루트의 `SKILL.md`를 에이전트가 읽게 합니다.
호스트에 공식 스킬 등록 기능이 있으면 해당 기능과 파일 제한을 확인하고 등록합니다.
등록이 되지 않으면 현재 작업에서 지침을 읽고 사용했다는 상태로 보고합니다.
존재하지 않는 메뉴나 설치 경로를 만들어 안내하지 않습니다.

`registry.py list`로 중앙 목록을 읽은 뒤 사용자의 양식 생성·수정 요청으로 이어갑니다.
내용은 자연어로 받습니다. 내부 JSON과 스타일 ID 작성은 에이전트가 담당합니다.

## Gemini 앱 경로

GitHub 가져오기는 읽기 기능입니다. 설치와 파일 실행을 자동으로 포함하지 않습니다.
Gemini 스킬 업로드에는 바이너리와 인터넷 스크립트 제한이 있습니다.
Spark의 원격 실행 환경을 쓸 수 있더라도 이 패키지의 런타임·파일 반환을 실제로 검사합니다.

현재 저장소의 Gemini 앱 전체 사용 경로는 미검증입니다.
실행 도구가 없으면 사용자에게 필요한 최소 단계는 다음처럼 안내할 수 있습니다.

1. ZIP 다운로드와 압축 해제
2. Windows에서 SETUP.cmd 실행
3. 실제로 파일 접근·실행을 지원하는 환경 연결

셋업 버튼 실행만으로 Gemini 채팅에 사용자 PC 접근이 생긴다고 말하지 않습니다.
Gemini CLI나 다른 에이전트로 이동하는 선택은 사용자에게 맡깁니다.

## 문제가 생겼을 때

| 현상 | 확인할 사항 |
|---|---|
| GitHub 페이지를 못 읽음 | Raw README 접근을 시도하거나 README 파일을 첨부. 실제 읽은 내용 확인 |
| 해시 불일치 | `runtime/downloads`의 해당 파일과 고정 manifest를 확인. 검사 생략 금지 |
| `lxml` import 오류 | Python 버전·CPU 아키텍처·wheel 대상이 맞는지 확인 |
| Node를 찾지 못함 | `scripts/run.ps1` 또는 `--node`로 프로젝트 런타임 경로 전달 |
| 버전 검사 실패 | 기존 수동 설치와 프로젝트 라이브러리 경로를 확인 |
| 한글이 깨짐 | Windows에서는 `python -X utf8` 사용 |
| 양식 후보가 여러 개 | 기관·부서·종류를 확인하고 동순위 후보를 사용자에게 보여줌 |
| 결과 파일의 외형이 다름 | 동일 엔진으로 페이지를 렌더링하고 글꼴·자간·불렛·표를 확인 |

공식 근거와 제한은 [README](../README.md)의 Gemini 항목 및 [검증 기록](verification.md)을 따릅니다.
