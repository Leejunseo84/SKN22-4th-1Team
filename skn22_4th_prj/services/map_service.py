import asyncio
import logging
import re

import httpx

from services.ai_service_v2 import AIService
from services.ingredient_utils import canonicalize_ingredient_name

logger = logging.getLogger(__name__)


class MapService:
    _FDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
    _OTC_FILTER = 'openfda.product_type:"HUMAN OTC DRUG"'
    _SYMPTOM_TO_FDA_TERM = {
        "두통": "headache",
        "편두통": "migraine",
        "소화불량": "indigestion",
        "기침": "cough",
        "감기": "cold",
        "발열": "fever",
        "통증": "pain",
        "염좌": "sprain",
        "찰과상": "wound",
        "상처": "wound",
        "화상": "burn",
        "곤충교상": "insect bite",
    }
    _DEFAULT_KR_SUMMARY = (
        "증상 완화를 위한 일반의약품으로 안내됩니다. "
        "복용 전 용법·용량과 주의사항을 확인하세요."
    )
    _BENEFIT_RULES = [
        ("진통", "통증 완화"),
        ("해열", "발열 완화"),
        ("소염", "염증 완화"),
        ("기침", "기침 완화"),
        ("콧물", "콧물 완화"),
        ("비염", "비염 증상 완화"),
        ("알레르기", "알레르기 증상 완화"),
        ("속쓰림", "위산/속쓰림 완화"),
        ("소화", "소화 불편 완화"),
        ("복통", "복부 통증 완화"),
        ("설사", "설사 증상 완화"),
        ("감기", "감기 증상 완화"),
        ("수면", "수면 보조"),
        ("pain", "통증 완화"),
        ("analgesic", "통증 완화"),
        ("fever", "발열 완화"),
        ("antipyretic", "발열 완화"),
        ("anti-inflammatory", "염증 완화"),
        ("inflammation", "염증 완화"),
        ("cough", "기침 완화"),
        ("allergy", "알레르기 증상 완화"),
        ("rhinitis", "비염 증상 완화"),
        ("cold", "감기 증상 완화"),
        ("indigestion", "소화 불편 완화"),
        ("heartburn", "위산/속쓰림 완화"),
        ("diarrhea", "설사 증상 완화"),
        ("sleep", "수면 보조"),
    ]

    @classmethod
    async def find_nearby_pharmacies(cls, lat: float, lng: float):
        return []

    @classmethod
    def _normalize_ingredient(cls, raw_value: str) -> str:
        value = str(raw_value or "").strip().upper()
        if not value:
            return ""

        value = re.sub(r"\([^)]*\)", " ", value)
        value = re.sub(
            r"\b\d+(?:\.\d+)?\s*(MG|MCG|G|ML|%)\b",
            " ",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(r"[^A-Z0-9\s\-]", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        if not value:
            return ""
        return canonicalize_ingredient_name(value)

    @classmethod
    def _normalize_ingredient_list(cls, ingredients: list) -> list:
        normalized = []
        seen = set()
        for raw in ingredients or []:
            token = cls._normalize_ingredient(raw)
            if not token or token in seen:
                continue
            seen.add(token)
            normalized.append(token)
        return normalized

    @classmethod
    def _extract_active_ingredient_text(cls, item: dict) -> str:
        active_values = item.get("active_ingredient") or []
        if isinstance(active_values, list):
            parts = [str(v).strip() for v in active_values if str(v).strip()]
            if parts:
                return " | ".join(parts)
        elif isinstance(active_values, str) and active_values.strip():
            return active_values.strip()

        generic_values = (item.get("openfda") or {}).get("generic_name") or []
        if isinstance(generic_values, list):
            parts = [str(v).strip() for v in generic_values if str(v).strip()]
            if parts:
                return ", ".join(parts)

        return "Unknown"

    @classmethod
    def _split_ingredient_tokens_from_text(cls, text: str) -> list:
        raw = str(text or "").strip()
        if not raw:
            return []

        parts = re.split(r"\||/|,|;|\bAND\b|\bWITH\b|\+", raw, flags=re.IGNORECASE)
        tokens = []
        seen = set()
        for part in parts:
            token = cls._normalize_ingredient(part)
            if not token or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
        return tokens

    @classmethod
    def _split_ingredient_tokens_from_values(cls, values) -> list:
        tokens = []
        seen = set()
        for raw in values or []:
            parts = re.split(r"\||/|,|;|\bAND\b|\bWITH\b|\+", str(raw), flags=re.IGNORECASE)
            for part in parts:
                token = cls._normalize_ingredient(part)
                if not token or token in seen:
                    continue
                seen.add(token)
                tokens.append(token)
        return tokens

    @classmethod
    def _extract_product_ingredient_tokens(cls, item: dict) -> list:
        openfda = item.get("openfda") or {}
        tokens = cls._split_ingredient_tokens_from_values(openfda.get("substance_name") or [])
        if not tokens:
            tokens = cls._split_ingredient_tokens_from_values(openfda.get("generic_name") or [])
        if tokens:
            return tokens

        active_values = item.get("active_ingredient") or []
        if isinstance(active_values, str):
            active_values = [active_values]
        return cls._split_ingredient_tokens_from_values(active_values)

    @classmethod
    def _infer_benefit_brief_kr(cls, text: str) -> str:
        raw = str(text or "").strip().lower()
        if not raw:
            return "증상 완화 보조"
        for needle, benefit in cls._BENEFIT_RULES:
            if needle in raw:
                return benefit
        return "증상 완화 보조"

    @classmethod
    def _to_product_payload(cls, item: dict) -> dict:
        openfda = item.get("openfda") or {}
        brand_name = (openfda.get("brand_name") or ["Unknown"])[0]
        manufacturer_name = (openfda.get("manufacturer_name") or ["Unknown Manufacturer"])[0]
        purpose = (item.get("purpose") or ["No purpose specified."])[0]

        return {
            "brand_name": brand_name,
            "manufacturer_name": manufacturer_name,
            "purpose": purpose,
            "summary_kr": "",
            "active_ingredient": cls._extract_active_ingredient_text(item),
        }

    @staticmethod
    def _contains_hangul(text: str) -> bool:
        return bool(re.search(r"[가-힣]", str(text or "")))

    @classmethod
    def _fallback_korean_summary(cls, original_text: str = "") -> str:
        if cls._contains_hangul(original_text):
            summary = str(original_text).strip()
        else:
            summary = cls._DEFAULT_KR_SUMMARY
        if len(summary) <= 150:
            return summary
        return summary[:147].rstrip() + "..."

    @classmethod
    async def _attach_korean_summaries(cls, products: list) -> list:
        if not isinstance(products, list) or not products:
            return products

        purposes = [str((p or {}).get("purpose") or "").strip() for p in products]
        translated = []
        try:
            translated = await AIService.translate_purposes(purposes)
        except Exception as e:
            logger.warning(f"Purpose summarization failed: {e}")
            translated = []

        for i, product in enumerate(products):
            summary = ""
            if i < len(translated):
                summary = str(translated[i] or "").strip()
            if not summary or not cls._contains_hangul(summary):
                src = purposes[i] if i < len(purposes) else ""
                summary = cls._fallback_korean_summary(src)
            product["summary_kr"] = summary
        return products

    @classmethod
    async def ensure_mapping_result_summaries(cls, mapping_result: dict) -> dict:
        if not isinstance(mapping_result, dict):
            return mapping_result

        match_type = str(mapping_result.get("match_type") or "").upper()
        if match_type == "FULL_MATCH":
            products = mapping_result.get("recommendations")
            if isinstance(products, list):
                needs = any(not str((p or {}).get("summary_kr") or "").strip() for p in products)
                if needs:
                    await cls._attach_korean_summaries(products)
            return mapping_result

        if match_type == "COMPONENT_MATCH":
            rec_groups = mapping_result.get("recommendations")
            if isinstance(rec_groups, list):
                for group in rec_groups:
                    products = (group or {}).get("products")
                    if not isinstance(products, list):
                        continue
                    needs = any(not str((p or {}).get("summary_kr") or "").strip() for p in products)
                    if needs:
                        await cls._attach_korean_summaries(products)

            cross = mapping_result.get("cross_ingredient_recommendations")
            if isinstance(cross, list):
                needs = any(not str((p or {}).get("summary_kr") or "").strip() for p in cross)
                if needs:
                    await cls._attach_korean_summaries(cross)

        return mapping_result

    @classmethod
    def _contains_ingredient(cls, text: str, ingredient: str) -> bool:
        if not text or not ingredient:
            return False
        return ingredient.upper() in text.upper()

    @classmethod
    def _ingredient_search_variants(cls, ingredient: str) -> list:
        """Build search variants to improve openFDA hit rate (e.g., NAPROXEN SODIUM)."""
        base = cls._normalize_ingredient(ingredient)
        if not base:
            return []

        variants = [base, f"{base} SODIUM", f"{base} POTASSIUM"]
        seen = set()
        ordered = []
        for token in variants:
            key = token.strip().upper()
            if not key or key in seen:
                continue
            seen.add(key)
            ordered.append(key)
        return ordered

    @classmethod
    def _normalize_symptom_for_fda(cls, symptom: str) -> str:
        token = str(symptom or "").strip().lower()
        if not token:
            return ""
        mapped = cls._SYMPTOM_TO_FDA_TERM.get(token)
        if mapped:
            return mapped
        return token

    @classmethod
    def _build_otc_search_query(cls, ingredient_variants: list, symptom: str = "") -> str:
        symptom_term = cls._normalize_symptom_for_fda(symptom)

        ingredient_clauses = []
        for var in ingredient_variants:
            ingredient_clauses.append(f'openfda.substance_name:"{var}"')
            ingredient_clauses.append(f'openfda.generic_name:"{var}"')
            ingredient_clauses.append(f'active_ingredient:"{var}"')

        ingredient_query = f"({' +OR+ '.join(ingredient_clauses)})"
        if symptom_term:
            symptom_query = f'(indications_and_usage:"{symptom_term}")'
            return f"{symptom_query}+AND+{ingredient_query}+AND+{cls._OTC_FILTER}"
        return f"{ingredient_query}+AND+{cls._OTC_FILTER}"

    @classmethod
    async def get_us_otc_products_by_ingredient(
        cls, ingredient: str, limit: int = 5, symptom: str = ""
    ):
        """Fetch OTC products containing the given ingredient from openFDA."""
        normalized_ingredient = cls._normalize_ingredient(ingredient)
        if not normalized_ingredient:
            return {"ingredient": ingredient, "products": [], "count": 0}

        variants = cls._ingredient_search_variants(normalized_ingredient)
        primary_query = cls._build_otc_search_query(variants, symptom=symptom)
        fallback_query = cls._build_otc_search_query([normalized_ingredient], symptom="")

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                primary_url = f"{cls._FDA_LABEL_URL}?search={primary_query}&limit=100"
                response = await client.get(primary_url)
                if response.status_code != 200:
                    data = []
                else:
                    data = response.json().get("results", [])

                # Fallback for ingredients whose OTC labels are indexed under active_ingredient text.
                if not data:
                    fallback_url = f"{cls._FDA_LABEL_URL}?search={fallback_query}&limit=100"
                    fallback_res = await client.get(fallback_url)
                    if fallback_res.status_code == 200:
                        data = fallback_res.json().get("results", [])

                products_info = []
                for item in data:
                    openfda = item.get("openfda") or {}
                    if not openfda.get("brand_name"):
                        continue
                    ingredient_text = cls._extract_active_ingredient_text(item)
                    generic_text = " ".join(openfda.get("generic_name") or [])
                    substance_text = " ".join(openfda.get("substance_name") or [])
                    searchable = f"{ingredient_text} {generic_text} {substance_text}".upper()
                    if not any(
                        cls._contains_ingredient(searchable, var) for var in variants
                    ):
                        continue
                    payload = cls._to_product_payload(item)
                    payload["_all_ingredient_tokens"] = cls._extract_product_ingredient_tokens(
                        item
                    )
                    products_info.append(payload)

                unique_products = {
                    (
                        (prod.get("brand_name") or "").strip().upper(),
                        (prod.get("active_ingredient") or "").strip().upper(),
                    ): prod
                    for prod in products_info
                }.values()

                sorted_products = sorted(
                    list(unique_products), key=lambda x: x.get("brand_name", "")
                )[: max(limit, 1)]
                sorted_products = await cls._attach_korean_summaries(sorted_products)
                for product in sorted_products:
                    all_tokens = product.get("_all_ingredient_tokens") or []
                    if not all_tokens:
                        all_tokens = cls._split_ingredient_tokens_from_text(
                            product.get("active_ingredient")
                        )

                    extras = [token for token in all_tokens if token != normalized_ingredient]
                    benefit = cls._infer_benefit_brief_kr(
                        product.get("summary_kr") or product.get("purpose")
                    )
                    product["other_active_ingredients"] = extras
                    product["other_active_components"] = [
                        {"name": token, "benefit": benefit} for token in extras
                    ]
                    product.pop("_all_ingredient_tokens", None)

                return {
                    "ingredient": normalized_ingredient,
                    "products": sorted_products,
                    "count": len(sorted_products),
                }
            except Exception as e:
                logger.error(
                    f"Error fetching FDA products for '{normalized_ingredient}': {e}"
                )
                return {
                    "ingredient": normalized_ingredient,
                    "products": [],
                    "error": str(e),
                }

    @classmethod
    async def find_optimal_us_products(cls, ingredients: list):
        normalized_ingredients = cls._normalize_ingredient_list(ingredients)
        if not normalized_ingredients:
            return {"match_type": "NONE", "recommendations": []}

        search_query = "+AND+".join(
            [
                f'(openfda.substance_name:"{ingr}"+OR+openfda.generic_name:"{ingr}")'
                for ingr in normalized_ingredients
            ]
        )
        url = (
            f"{cls._FDA_LABEL_URL}"
            f"?search={search_query}+AND+{cls._OTC_FILTER}"
            f"&limit=20"
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.get(url)
                if res.status_code == 200 and res.json().get("results"):
                    results = res.json().get("results", [])
                    products = [cls._to_product_payload(item) for item in results]
                    products = list(
                        {
                            (
                                (p.get("brand_name") or "").strip().upper(),
                                (p.get("active_ingredient") or "").strip().upper(),
                            ): p
                            for p in products
                        }.values()
                    )[:10]

                    if products:
                        products = await cls._attach_korean_summaries(products)

                    return {
                        "match_type": "FULL_MATCH",
                        "description": "요청한 모든 성분이 포함된 OTC 제품을 찾았습니다.",
                        "recommendations": products,
                    }
            except Exception as e:
                logger.error(f"Full match search error: {e}")

        component_recommendations = await asyncio.gather(
            *[
                cls.get_us_otc_products_by_ingredient(ingr, limit=20)
                for ingr in normalized_ingredients
            ]
        )

        candidate_map = {}
        for rec in component_recommendations:
            for prod in rec.get("products", []):
                key = (
                    (prod.get("brand_name") or "").strip().upper(),
                    (prod.get("active_ingredient") or "").strip().upper(),
                )
                if key not in candidate_map:
                    candidate_map[key] = prod

        cross_ingredient_recommendations = []
        for product in candidate_map.values():
            combined_text = (
                f"{product.get('brand_name', '')} "
                f"{product.get('active_ingredient', '')}"
            )
            matched_ingredients = [
                ingr
                for ingr in normalized_ingredients
                if cls._contains_ingredient(combined_text, ingr)
            ]
            if len(matched_ingredients) >= 2:
                cross_ingredient_recommendations.append(
                    {
                        **product,
                        "matched_ingredients": matched_ingredients,
                        "match_count": len(matched_ingredients),
                    }
                )

        cross_ingredient_recommendations.sort(
            key=lambda x: (-x.get("match_count", 0), x.get("brand_name", ""))
        )

        for rec in component_recommendations:
            rec["products"] = rec.get("products", [])[:5]

        return {
            "match_type": "COMPONENT_MATCH",
            "description": "완전 일치 제품이 없어 성분별 대체 후보를 제공합니다.",
            "recommendations": component_recommendations,
            "cross_ingredient_recommendations": cross_ingredient_recommendations[:10],
        }

    @classmethod
    def generate_pharmacist_card(
        cls, ingredients: list, dosage_form: str = "Tablet/Capsule"
    ):
        ingr_str = ", ".join(ingredients)
        card = {
            "title": "약사 상담 카드",
            "active_ingredients": ingredients,
            "desired_dosage_form": dosage_form,
            "english_guide": [
                f"다음 성분이 포함된 OTC 제품을 찾고 있습니다: {ingr_str}",
                f"가능하면 '{dosage_form}' 제형을 선호합니다.",
                "재고 중 가장 가까운 제품을 추천해 주세요.",
            ],
        }
        return card
