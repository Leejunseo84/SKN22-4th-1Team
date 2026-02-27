# 호출 단순화(응답 동일) 정리

## 목적
- 현재 응답 형태/내용을 유지하면서 외부 호출 수와 지연 시간을 줄인다.

## 1. `normalize_symptom_query` 호출 제거 (우선 적용)
- 대상: `skn22_4th_prj/graph_agent/nodes_v2.py` 의 `classify_node`
- 현재 상태:
  - `AIService.normalize_symptom_query(query)` + `AIService.classify_intent(query)`를 병렬 호출
  - `cache_key`는 state에 저장만 되고 실제 캐시 분기(`is_cached=True`)가 없어 응답 생성에 영향 없음
- 변경:
  - `classify_intent(query)`만 호출
  - `cache_key`는 `None`으로 유지(필드 호환성 유지)
- 기대 효과:
  - 요청당 OpenAI 호출 1회 감소
  - 응답 결과 동일

## 2. OTC 제품 조회를 `can_take=True` 성분만 수행
- 대상: `skn22_4th_prj/graph_agent/nodes_v2.py` 의 `generate_symptom_answer_node`
- 현재 상태:
  - 모든 성분에 대해 FDA OTC 제품 조회 후, `can_take=False` 성분 결과는 최종 출력에서 버림
- 변경:
  - AI 판정 후 복용 가능 성분만 `MapService.get_us_otc_products_by_ingredient` 호출
- 기대 효과:
  - FDA 호출 수 감소, 응답 시간 단축
  - 최종 출력 동일

## 3. 프로필 조회를 증상 질의에서만 수행
- 대상: `skn22_4th_prj/chat/views.py` 의 `smart_search`
- 현재 상태:
  - 로그인 세션이 있으면 모든 검색에서 Supabase 프로필 조회
- 변경:
  - `symptom_recommendation` 경로에서만 프로필 조회
- 기대 효과:
  - 불필요한 Supabase 호출 감소
  - 제품/일반 질의 응답 동일

## 4. 그래프 컴파일 결과 재사용
- 대상: `skn22_4th_prj/chat/views.py`
- 현재 상태:
  - 요청마다 `build_graph()` 호출
- 변경:
  - 모듈 로드 시 1회 컴파일 후 재사용
- 기대 효과:
  - 내부 오버헤드 감소
  - 응답 내용 동일

## 진행 상태
- [x] 1번 적용
- [x] 2번 적용
- [x] 3번 적용
- [x] 4번 적용
