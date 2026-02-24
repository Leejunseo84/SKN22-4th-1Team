import os
import django
import requests
import time
from datetime import datetime
from urllib.parse import unquote

import sys

# 1. Django 환경 설정 (상위 디렉토리의 backend_django 추가)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend_django')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from drugs.models import EYakInfo

class EYakInfoCollector:
    def __init__(self):
        raw_key = os.getenv('KR_API_KEY')
        self.service_key = unquote(raw_key) if raw_key else ""
        # [확정] e약은요 서비스 URL
        self.base_url = "https://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList"

    def format_date(self, date_str):
        """다양한 날짜 형식(2024-05-09 또는 20210129)을 Date 객체로 변환"""
        if not date_str:
            return None
        # '-' 제거 후 숫자만 추출
        clean_date = str(date_str).replace('-', '')[:8]
        try:
            return datetime.strptime(clean_date, '%Y%m%d').date()
        except:
            return None

    def collect_all(self, pages=10):
        print(f"--- [START] e약은요 대량 수집 시작 (목표: {pages}페이지) ---")
        
        for page in range(1, pages + 1):
            params = {
                'serviceKey': self.service_key,
                'pageNo': page,
                'numOfRows': 100, # 대량 수집을 위해 100건씩 요청
                'type': 'json'
            }
            
            try:
                response = requests.get(self.base_url, params=params, timeout=20)
                if response.status_code != 200:
                    print(f"   ! 서버 응답 에러 ({response.status_code})")
                    continue

                data = response.json()
                body = data.get('body', {})
                items_list = body.get('items', [])

                if not items_list:
                    print(f"   - {page}페이지: 더 이상 가져올 데이터가 없습니다.")
                    break

                success_count = 0
                for item in items_list:
                    # [로그 분석 반영] item이 바로 데이터 딕셔너리임
                    item_seq = item.get('itemSeq')
                    if not item_seq:
                        continue

                    # 주의사항 필드 통합 (경고 + 일반주의)
                    warn_text = item.get('atpnWarnQesitm') or ""
                    atpn_text = item.get('atpnQesitm') or ""
                    combined_precautions = f"{warn_text}\n{atpn_text}".strip()

                    # DB 저장 (Update or Create)
                    EYakInfo.objects.update_or_create(
                        item_seq=item_seq,
                        defaults={
                            'item_name': item.get('itemName'),
                            'entp_name': item.get('entpName'),
                            'efficacy': item.get('efcyQesitm'),
                            'use_method': item.get('useMethodQesitm'),
                            'precautions': combined_precautions,
                            'interaction': item.get('intrcQesitm'),
                            'side_effects': item.get('seQesitm'),
                            'item_image': item.get('itemImage'),
                            'source_updated_at': self.format_date(item.get('updateDe'))
                        }
                    )
                    success_count += 1

                print(f"   - {page}페이지 완료 ({success_count}건 저장/업데이트)")
                
                # API 서버 부하 방지를 위한 미세 지연
                time.sleep(0.2)

            except Exception as e:
                print(f"   ! {page}페이지 실행 중 예외 발생: {str(e)}")
                
        print("\n--- [FINISH] e약은요 데이터 수집 프로세스 종료 ---")

if __name__ == "__main__":
    collector = EYakInfoCollector()
    # 전체 약물이 약 4,500개 이상이므로, 넉넉하게 50페이지(100건씩) 설정 시 전체 수집 가능
    collector.collect_all(pages=50)