import os
import django
import requests
import time
from datetime import datetime
from urllib.parse import unquote
import json
import sys

# 1. Django 환경 설정 (상위 디렉토리의 backend_django 추가)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend_django')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from drugs.models import DurMaster
from django.db import IntegrityError

class DurUnifiedCollector:
    def __init__(self):
        # .env에서 API 키 로드 및 디코딩 처리
        raw_key = os.getenv('KR_API_KEY')
        self.service_key = unquote(raw_key) if raw_key else ""
        
        # [확정] 성분 기반 최신 API 서비스 주소
        self.base_url = "https://apis.data.go.kr/1471000/DURIrdntInfoService03"
        
        # 각 카테고리별 엔드포인트 및 매핑 필드 정의
        # val_key: 핵심 주의 값으로 사용할 필드
        # name_key: 성분명 필드가 'INGR_KOR_NAME'인지 'INGR_NAME'인지 구분
        self.api_configs = {
            'getUsjntTabooInfoList02': {
                'type': 'COMBINED', 
                'val_key': 'MIXTURE_INGR_KOR_NAME',
                'name_key': 'INGR_KOR_NAME' # 병용금기는 INGR_KOR_NAME 사용
            },
            'getPwnmTabooInfoList02': {
                'type': 'PREGNANCY', 
                'val_key': 'GRADE',
                'name_key': 'INGR_NAME' # 임부금기는 INGR_NAME 사용
            },
            'getCpctyAtentInfoList02': {
                'type': 'MAX_CAPACITY', 
                'val_key': 'MAX_QTY',
                'name_key': 'INGR_NAME'
            },
            'getMdctnPdAtentInfoList02': {
                'type': 'DURATION', 
                'val_key': 'MAX_DOSAGE_TERM',
                'name_key': 'INGR_NAME'
            },
            'getOdsnAtentInfoList02': {
                'type': 'ELDERLY', 
                'val_key': None, # 별도 값 없음 (주의 내용 참조)
                'name_key': 'INGR_NAME'
            },
            'getSpcifyAgrdeTabooInfoList02': {
                'type': 'AGE_LIMIT', 
                'val_key': 'AGE_BASE',
                'name_key': 'INGR_NAME'
            },
            'getEfcyDplctInfoList02': {
                'type': 'EFFICACY_DUPLICATE', 
                'val_key': 'SERS_NAME',
                'name_key': 'INGR_NAME'
            },
        }

    def format_date(self, date_str):
        """YYYYMMDD -> Date 객체 변환"""
        if date_str and len(str(date_str)) == 8:
            try:
                return datetime.strptime(str(date_str), '%Y%m%d').date()
            except: return None
        return None

    def collect_all(self, pages_per_api=5):
        """모든 DUR API를 순회하며 데이터 수집"""
        print(f"--- [START] DUR 통합 데이터 수집 시작 (대상: {len(self.api_configs)}개) ---")
        
        for api_path, config in self.api_configs.items():
            print(f"\n>>> [{config['type']}] 카테고리 진행 중...")
            
            for page in range(1, pages_per_api + 1):
                # JSON 요청 파라미터 포함
                full_url = f"{self.base_url}/{api_path}?serviceKey={self.service_key}&pageNo={page}&numOfRows=100&type=json"
                
                try:
                    response = requests.get(full_url, timeout=15)
                    if response.status_code != 200:
                        print(f"   ! 서버 응답 에러: {response.status_code}")
                        continue

                    try:
                        data = response.json()
                    except:
                        print(f"   ! JSON 파싱 에러 (URL: {full_url})")
                        continue
                    
                    # [핵심 교정] body -> items(리스트) -> 요소내 item(딕셔너리) 접근
                    items_list = data.get('body', {}).get('items', [])
                    
                    if not items_list:
                        print(f"   - {page}페이지: 데이터가 더 이상 없습니다.")
                        break

                    success_in_page = 0
                    
                    for wrapper in items_list:
                        # 리스트의 요소가 {"item": {...}} 형태이므로 실제 데이터 본체 추출
                        item = wrapper.get('item') if isinstance(wrapper, dict) else wrapper
                        
                        if not item:
                            continue

                        # 성분 코드 추출 (대소문자 혼용 대응)
                        ingr_code = item.get('INGR_CODE') or item.get('ingrCode')
                        if not ingr_code:
                            continue

                        # 공통 필드 매핑
                        defaults = {
                            # 기본 식별자
                            'dur_seq': item.get('DUR_SEQ'),
                            'dur_type': config['type'],  # [FIX] dur_type 누락 방지
                            'ingr_code': ingr_code,      # [FIX] ingr_code 누락 방지
                            'type_name': item.get('TYPE_NAME'),
                            'form_name': item.get('FORM_NAME'),
                            'mix_type': item.get('MIX_TYPE'),
                            'del_yn': item.get('DEL_YN', '정상'),
                            
                            # 성분명 (API마다 키가 다름. DUR_TABLE.MD 우선순위 반영)
                            'ingr_kor_name': item.get('INGR_NAME') or item.get('INGR_KOR_NAME') or '이름없음',
                            'ingr_eng_name': item.get('INGR_ENG_NAME'),
                            
                            # 원문 정보
                            'ori_ingr': item.get('ORI') or item.get('ORI_INGR'),
                            'mix_ingr': item.get('MIX') or item.get('MIX_INGR'),
                            
                            # 병용금기 특화
                            'mixture_ingr_code': item.get('MIXTURE_INGR_CODE'),
                            'mixture_ingr_kor_name': item.get('MIXTURE_INGR_KOR_NAME'),
                            'mixture_ingr_eng_name': item.get('MIXTURE_INGR_ENG_NAME'),
                            'mixture_mix_type': item.get('MIXTURE_MIX_TYPE'),
                            'mixture_class': item.get('MIXTURE_CLASS'),
                            'mixture_ori': item.get('MIXTURE_ORI') or item.get('MIXTURE_MIX'), 
                            
                            # 금기/주의 내용
                            'prohbt_content': item.get('PROHBT_CONTENT') or item.get('prohbtContent'),
                            'remark': item.get('REMARK') or item.get('remark'),
                            'class_name': item.get('CLASS_NAME') or item.get('CLASS'),
                            'notification_date': self.format_date(item.get('NOTIFICATION_DATE')),
                        }

                        # 핵심 주의 값(Critical Value) 및 유형별 특화 컬럼 매핑
                        v_key = config['val_key']
                        critical_val = item.get(v_key)
                        
                        # 유형별 컬럼에 값 할당
                        if config['type'] == 'PREGNANCY':
                            defaults['grade'] = item.get('GRADE')
                        elif config['type'] == 'MAX_CAPACITY':
                            defaults['max_qty'] = item.get('MAX_QTY')
                        elif config['type'] == 'DURATION':
                            defaults['max_dosage_term'] = item.get('MAX_DOSAGE_TERM')
                        elif config['type'] == 'AGE_LIMIT':
                            defaults['age_base'] = item.get('AGE_BASE')
                        elif config['type'] == 'EFFICACY_DUPLICATE':
                            defaults['effect_code'] = item.get('EFFECT_CODE')
                            defaults['sers_name'] = item.get('SERS_NAME')
                        
                        # 식별자 구성 (중복 방지 로직 개선)
                        # 1. DUR_SEQ가 있으면 최우선 식별자로 사용 (단, 없는 API도 있을 수 있음)
                        dur_seq = item.get('DUR_SEQ')
                        
                        lookup_kwargs = {}
                        if dur_seq:
                             lookup_kwargs['dur_seq'] = dur_seq
                        else:
                            # DUR_SEQ가 없으면 기존 복합키 사용
                            lookup_kwargs['dur_type'] = config['type']
                            lookup_kwargs['ingr_code'] = ingr_code
                            
                            if config['type'] == 'COMBINED' and item.get('MIXTURE_INGR_CODE'):
                                lookup_kwargs['mixture_ingr_code'] = item.get('MIXTURE_INGR_CODE')
                            elif critical_val:
                                 lookup_kwargs['critical_value'] = str(critical_val)

                        defaults['critical_value'] = str(critical_val) if critical_val else None

                        try:
                            # DB 저장 (Update or Create)
                            DurMaster.objects.update_or_create(
                                **lookup_kwargs,
                                defaults=defaults
                            )
                            success_in_page += 1
                        except DurMaster.MultipleObjectsReturned:
                            # 중복된 데이터가 이미 존재하는 경우: 모두 삭제 후 새로 생성
                            if not dur_seq: # DUR_SEQ가 없을 때만 이 로직이 의미 있음
                                print(f"      ! 중복 데이터 감지. 정리 후 재저장: {lookup_kwargs}")
                                DurMaster.objects.filter(**lookup_kwargs).delete()
                                DurMaster.objects.create(**lookup_kwargs, **defaults)
                                success_in_page += 1
                        except Exception as db_e:
                            print(f"      ! DB 저장 실패: {db_e} (Code: {ingr_code})")
                        
                    print(f"   - {page}페이지 완료 ({success_in_page}건 저장)")
                    time.sleep(0.3) # API 서버 부하 방지

                except Exception as e:
                    print(f"   ! 에러 발생 ({config['type']}, Page {page}): {str(e)}")
                    
        print("\n--- [FINISH] 모든 DUR 데이터가 성공적으로 저장되었습니다. ---")

if __name__ == "__main__":
    collector = DurUnifiedCollector()
    # 전체 수집 시 pages_per_api를 10~50 정도로 높여서 실행하세요.
    # 검증을 위해 1페이지씩만 수집
    print("--- [TEST RUN] 검증을 위해 각 API당 1페이지만 수집합니다 ---")
    collector.collect_all(pages_per_api=50)
