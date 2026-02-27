import os
import sys
import django

# 1. Django 환경 설정
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend_django')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from drugs.models import DurMaster, UnifiedDrugInfo, DrugPermitInfo
from supabase import create_client, Client

# 2. Supabase 연결 설정
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

def sync_data():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Error: SUPABASE_URL 또는 SUPABASE_KEY 환경변수가 설정되지 않았습니다.")
        return

    print("--- [START] Supabase 데이터 동기화 시작 ---")

    # 3. 로컬 데이터 조회 (DUR 마스터)
    print("1. 로컬 DB에서 DUR 데이터 조회 중...")
    local_data = list(DurMaster.objects.all().values())
    total_count = len(local_data)
    print(f"   - 총 {total_count}건의 DUR 데이터를 발견했습니다.")

    # 4. Supabase 클라이언트 연결
    print("2. Supabase 연결 설정...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 5. DUR 데이터 배치 처리 (한 번에 500건씩)
    if total_count > 0:
        print("   - DUR 데이터 Supabase 삽입 시작...")
        batch_size = 500
        for i in range(0, total_count, batch_size):
            batch = local_data[i:i + batch_size]

            rows = []
            for item in batch:
                rows.append({
                    'dur_seq':                item.get('dur_seq'),
                    'dur_type':               item.get('dur_type'),
                    'type_name':              item.get('type_name'),
                    'ingr_code':              item.get('ingr_code'),
                    'ingr_kor_name':          item.get('ingr_kor_name'),
                    'ingr_eng_name':          item.get('ingr_eng_name'),
                    'form_name':              item.get('form_name'),
                    'mix_type':               item.get('mix_type'),
                    'mix_ingr':               item.get('mix_ingr'),
                    'ori_ingr':               item.get('ori_ingr'),
                    'mixture_ingr_code':      item.get('mixture_ingr_code'),
                    'mixture_ingr_kor_name':  item.get('mixture_ingr_kor_name'),
                    'mixture_ingr_eng_name':  item.get('mixture_ingr_eng_name'),
                    'mixture_mix_type':       item.get('mixture_mix_type'),
                    'mixture_class':          item.get('mixture_class'),
                    'mixture_ori':            item.get('mixture_ori'),
                    'grade':                  item.get('grade'),
                    'max_qty':                item.get('max_qty'),
                    'max_dosage_term':        item.get('max_dosage_term'),
                    'age_base':               item.get('age_base'),
                    'effect_code':            item.get('effect_code'),
                    'sers_name':              item.get('sers_name'),
                    'critical_value':         item.get('critical_value'),
                    'prohbt_content':         item.get('prohbt_content'),
                    'remark':                 item.get('remark'),
                    'class_name':             item.get('class_name'),
                    'notification_date':      str(item.get('notification_date')) if item.get('notification_date') else None,
                    'del_yn':                 item.get('del_yn'),
                })

            try:
                supabase.table('dur_master').upsert(rows).execute()
                print(f"   - DUR: {min(i + batch_size, total_count)}/{total_count}건 저장 완료...")
            except Exception as e:
                print(f"   ! DUR 배치 저장 실패 ({i}~{i+batch_size}): {e}")

    # 6. UnifiedDrugInfo 데이터 배치 처리
    print("\n3. 로컬 DB에서 통합 의약품 정보 조회 중...")
    unified_data = list(UnifiedDrugInfo.objects.all().values())
    unified_count = len(unified_data)
    print(f"   - 총 {unified_count}건의 통합 의약품 데이터를 발견했습니다.")

    if unified_count > 0:
        print("4. Supabase 통합 의약품 데이터 삽입 시작...")
        batch_size = 500
        for i in range(0, unified_count, batch_size):
            batch = unified_data[i:i + batch_size]
            
            rows = []
            for item in batch:
                rows.append({
                    'item_seq': item.get('item_seq'),
                    'item_name': item.get('item_name'),
                    'entp_name': item.get('entp_name'),
                    'etc_otcc_name': item.get('etc_otcc_name'),
                    'main_ingr_eng': item.get('main_ingr_eng'),
                    'main_ingr_kor': item.get('main_ingr_kor'),
                    'efficacy': item.get('efficacy'),
                    'use_method': item.get('use_method'),
                    'precautions': item.get('precautions'),
                    'interaction': item.get('interaction'),
                    'side_effects': item.get('side_effects'),
                    'item_image': item.get('item_image'),
                    'source_updated_at': str(item.get('source_updated_at')) if item.get('source_updated_at') else None,
                })
                
            try:
                supabase.table('unified_drug_info').upsert(rows).execute()
                print(f"   - 의약품: {min(i + batch_size, unified_count)}/{unified_count}건 저장 완료...")
            except Exception as e:
                print(f"   ! 의약품 배치 저장 실패 ({i}~{i+batch_size}): {e}")

    # 7. DrugPermitInfo (원본 허가 정보) 데이터 배치 처리
    print("\n5. 로컬 DB에서 원본 허가 정보(DrugPermitInfo) 조회 중...")
    permit_data = list(DrugPermitInfo.objects.all().values())
    permit_count = len(permit_data)
    print(f"   - 총 {permit_count}건의 원본 허가 정보 데이터를 발견했습니다.")

    if permit_count > 0:
        print("6. Supabase 원본 허가 정보 데이터 삽입 시작...")
        batch_size = 500
        for i in range(0, permit_count, batch_size):
            batch = permit_data[i:i + batch_size]
            
            rows = []
            for item in batch:
                rows.append({
                    'item_seq': item.get('item_seq'),
                    'item_name': item.get('item_name'),
                    'item_eng_name': item.get('item_eng_name'),
                    'entp_name': item.get('entp_name'),
                    'main_ingr_eng': item.get('main_ingr_eng'),
                    'main_ingr_kor': item.get('main_ingr_kor'),
                    'etc_otcc_name': item.get('etc_otcc_name'),
                    'source_updated_at': str(item.get('source_updated_at')) if item.get('source_updated_at') else None,
                })
                
            try:
                supabase.table('drug_permit_info').upsert(rows).execute()
                print(f"   - 원본 허가: {min(i + batch_size, permit_count)}/{permit_count}건 저장 완료...")
            except Exception as e:
                print(f"   ! 원본 허가 배치 저장 실패 ({i}~{i+batch_size}): {e}")

    print("\n--- [FINISH] 전체 동기화 완료 ---")

if __name__ == "__main__":
    sync_data()
