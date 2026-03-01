# Global Drug Safety Intelligence

해외 체류 중인 한국인을 위한 증상 기반 OTC 의약품 안전 가이드 프로젝트입니다.  
미국 FDA 데이터와 한국 DUR 정보를 결합해, 사용자 증상/프로필 기반 안내를 제공합니다.

## 프로젝트 구조

```text
.
├── skn22_4th_prj/                    # Django 웹 애플리케이션
│   ├── manage.py
│   ├── chat/                         # 메인 페이지, smart search, 약국 API
│   ├── drug/                         # 약품 검색/US 로드맵 API
│   ├── users/                        # 회원가입/로그인/프로필
│   ├── graph_agent/                  # LangGraph 워크플로우
│   ├── services/                     # Supabase/FDA/OpenAI 연동 로직
│   ├── prompts/                      # LLM 프롬프트
│   ├── templates/                    # Django 템플릿
│   └── skn22_4th_prj/                # settings/urls/asgi/wsgi
├── data_pipeline/                    # 데이터 수집/동기화 스크립트
├── mysql/                            # SQL 파일
├── requirements.txt
└── PROJECT_STRUCTURE_OPTIMIZATION.md # 구조 진단/개선안
```

## 아키텍처 요약

- 서버: Django
- AI 흐름: LangGraph (`graph_agent`)
- 외부 연동: OpenAI, FDA Open API, Supabase
- 데이터 저장: Supabase 중심 (Django는 내부 관리용 SQLite 설정 포함)

기본 흐름:

1. 사용자 질의 입력
2. 의도 분류 (`classify_node`)
3. 증상/제품 경로별 데이터 조회 (`retrieve_data_node`)
4. FDA 제품 조회 및 DUR 조회
5. 최종 답변 생성 후 템플릿 렌더링

## 빠른 시작

### 1) 가상환경 및 의존성 설치

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2) `.env` 생성 (저장소 루트)

```env
OPENAI_API_KEY=...
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_KEY=<your-anon-or-service-key>

# Optional
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
GOOGLE_MAPS_API_KEY=<maps-js-key>
KR_API_KEY=<public-data-key>
DJANGO_SECRET_KEY=<django-secret>
LANGSMITH_API_KEY=<langsmith-key>
LANGCHAIN_PROJECT=skn22-4th-django
```

### 3) DB 마이그레이션

```bash
cd skn22_4th_prj
python manage.py migrate
```

### 4) uvicorn 실행

```bash
cd skn22_4th_prj
python run_uvicorn.py
```

또는 직접 실행:

```bash
cd skn22_4th_prj
uvicorn skn22_4th_prj.asgi:application --host 0.0.0.0 --port 8000 --reload
```

접속: `http://127.0.0.1:8000`

## 주요 URL

- `/` : 홈
- `/smart-search/` : 증상/제품 통합 검색
- `/auth/register/`, `/auth/login/`, `/auth/logout/`
- `/user/profile/`
- `/drug/search/` : 약품 검색 API
- `/drug/us-roadmap/` : 미국 OTC 매핑 API

호환 경로(`/drugs/*`, `/api/drugs/*`)도 일부 유지되어 있습니다.

## 데이터 파이프라인

`data_pipeline/`에는 수집/동기화 스크립트가 있습니다.

- 실행 후보:
  - `unified_loader.py`
  - `drug_enrichment_collector.py`
- 레거시 가능성 있음(구 경로 참조):
  - `dur_unified_collector.py`
  - `sync_to_supabase.py`

위 2개는 현재 저장소 구조 기준으로 경로 수정이 필요할 수 있습니다.

## 환경 점검 스크립트

```bash
cd skn22_4th_prj
python check_env.py
python check_tables.py
```

## 주의사항

- 본 시스템은 의료 진단/처방을 대체하지 않습니다.
- 복용 전 의사/약사 상담이 필요합니다.
- `.env`, `db.sqlite3` 등 민감/로컬 파일은 버전 관리에서 제외하세요.
