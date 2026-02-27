import logging
import asyncio
from .state import AgentState
from services.ai_service_v2 import AIService
from services.drug_service import DrugService
from services.user_service import UserService

logger = logging.getLogger(__name__)


async def classify_node(state: AgentState) -> AgentState:
    """Classify user query and extract keywords"""
    query = state["query"]

    intent = await AIService.classify_intent(query)

    logger.info("Classifying query")

    category = intent.get("category", "invalid")
    keyword = intent.get("keyword", "")

    return {
        "category": category,
        "keyword": keyword,
        "symptom": query if category == "symptom_recommendation" else None,
        "cache_key": None,
        "is_cached": False,
    }


async def retrieve_data_node(state: AgentState) -> AgentState:
    """Retrieve FDA + DUR data in a single step (merged for latency optimization)"""
    category = state["category"]
    keyword = state["keyword"]
    query = state["query"]
    user_profile_data = state.get("user_profile")

    if category == "symptom_recommendation" and not user_profile_data:
        user_info = state.get("user_info")
        if user_info:
            try:
                profile = await UserService.get_profile(user_info)
                if profile:
                    user_profile_data = {
                        "current_medications": profile.current_medications,
                        "allergies": profile.allergies,
                        "chronic_diseases": profile.chronic_diseases,
                    }
            except Exception as e:
                logger.error(f"Error fetching user profile from Supabase: {e}")

    fda_data = None
    dur_data = []

    # ?? Step 1: FDA retrieval ??
    if category == "symptom_recommendation":
        eng_kw = [keyword] if keyword and keyword != "none" else ["pain"]
        fda_ingrs = await DrugService.get_ingrs_from_fda_by_symptoms(eng_kw)

        if not fda_ingrs:
            logger.info(
                f"FDA search failed for '{keyword}'. Requesting AI ingredient recommendation."
            )
            fda_ingrs = await AIService.recommend_ingredients_for_symptom(
                keyword or query
            )
            logger.info(f"AI recommended ingredients: {fda_ingrs}")

        fda_data = fda_ingrs

    elif category == "product_request":
        target = keyword if keyword and keyword != "none" else query
        fda_data = await DrugService.search_fda(target)

    # ?? Step 2: DUR retrieval (depends on FDA results) ??
    if fda_data:
        if category == "symptom_recommendation" and isinstance(fda_data, list):
            dur_data = await DrugService.get_enriched_dur_info(fda_data)
        elif category == "product_request" and isinstance(fda_data, dict):
            ingrs = fda_data.get("active_ingredients", "")
            dur_data = await DrugService.get_dur_by_ingr(ingrs)

    return {
        "fda_data": fda_data,
        "dur_data": dur_data,
        "user_profile": user_profile_data,
    }


async def generate_symptom_answer_node(state: AgentState) -> AgentState:
    """Generate per-ingredient safety guidance and fetch OTC product names"""
    symptom = state["symptom"]
    dur_data = state["dur_data"]
    fda_data = state.get("fda_data", [])

    if state.get("is_cached", False):
        return {
            "final_answer": state.get("final_answer", ""),
            "dur_data": dur_data,
            "fda_data": fda_data,
            "ingredients_data": state.get("ingredients_data", []),
        }

    # DUR ?곗씠?곌? ?놁쑝硫??쇰컲 AI ?듬??쇰줈 ?대갚
    if not dur_data:
        fallback_query = (
            f"The user asked about '{symptom}' but I couldn't find specific drugs in the FDA/DUR database. "
            f"Please provide general medical advice or common over-the-counter ingredients for this symptom. "
            f"(User query: {state['query']})"
        )
        answer = await AIService.generate_general_answer(fallback_query)
        prefix = "?대떦 利앹긽?????FDA/DUR 湲곕컲???뺥솗???섏빟???뺣낫??李얠쓣 ???놁뿀吏留? ?쇰컲?곸씤 ?뺣낫瑜??덈궡???쒕┰?덈떎.\n\n"
        return {"final_answer": prefix + answer, "ingredients_data": []}

    # Generate AI judgment first, then fetch products only for safe ingredients.

    async def fetch_products(ingr_name: str):
        from services.map_service import MapService
        try:
            result = await MapService.get_us_otc_products_by_ingredient(ingr_name)
            return ingr_name, result.get("products", [])
        except Exception as e:
            logger.warning(f"Failed to fetch products for '{ingr_name}': {e}")
            return ingr_name, []

    # AI result is required to determine which ingredients are safe to fetch.
    ai_result = await AIService.generate_symptom_answer(
        symptom, dur_data, state.get("user_profile")
    )

    if not isinstance(ai_result, dict):
        # ?덉쇅???대갚
        return {
            "final_answer": str(ai_result),
            "dur_data": dur_data,
            "ingredients_data": [],
        }

    summary = ai_result.get("summary", "")
    ai_ingredients = ai_result.get("ingredients", [])

    logger.info(
        f"AI classified {len(ai_ingredients)} ingredients for symptom '{symptom}'"
    )

    safe_name_set = {
        ing.get("name", "").upper()
        for ing in ai_ingredients
        if ing.get("can_take", False) and ing.get("name")
    }
    all_ingredient_names = [item["ingredient"].upper() for item in dur_data]
    target_product_names = [name for name in all_ingredient_names if name in safe_name_set]
    product_tasks = [fetch_products(name) for name in target_product_names]
    product_results = await asyncio.gather(*product_tasks) if product_tasks else []
    products_map = dict(product_results)

    # DUR ?곸꽭 ?곗씠?곕? ?깅텇紐?湲곗??쇰줈 ?몃뜳??
    dur_map = {item["ingredient"].upper(): item for item in dur_data}

    # 理쒖쥌 ingredients_data 議곕┰ (safe ?깅텇留?products ?ы븿)
    ingredients_data = []
    for ing in ai_ingredients:
        name = ing.get("name", "").upper()
        dur_item = dur_map.get(name, {})

        entry = {
            "name": name,
            "can_take": ing.get("can_take", True),
            "reason": ing.get("reason", ""),
            "dur_warning_types": ing.get("dur_warning_types", []),
            "kr_durs": dur_item.get("kr_durs", []),
            "fda_warning": dur_item.get("fda_warning", None),
            "products": (
                products_map.get(name, []) if ing.get("can_take", False) else []
            ),
        }
        ingredients_data.append(entry)

    return {
        "final_answer": summary,
        "dur_data": dur_data,
        "fda_data": fda_data,
        "ingredients_data": ingredients_data,
    }


async def generate_product_answer_node(state: AgentState) -> AgentState:
    """Generate answer for product queries"""
    fda_data = state["fda_data"]
    dur_data = state["dur_data"]

    if not fda_data:
        return {"final_answer": "?대떦 ?섏빟???뺣낫瑜?李얠쓣 ???놁뒿?덈떎."}

    brand_name = fda_data.get("brand_name")
    indications = fda_data.get("indications")

    answer = f"**{brand_name}** ?뺣낫?낅땲??\n\n**?⑤뒫/?④낵**:\n{indications}\n\n**DUR/二쇱쓽?ы빆**:\n"
    for d in dur_data:
        answer += f"- {d['ingr_name']} ({d['type']}): {d['warning_msg']}\n"

    return {"final_answer": answer}


async def generate_general_answer_node(state: AgentState) -> AgentState:
    """Generate answer for general medical queries"""
    answer = await AIService.generate_general_answer(state["query"])
    return {"final_answer": answer}


async def generate_error_node(state: AgentState) -> AgentState:
    """Handle invalid queries"""
    return {
        "final_answer": "二꾩넚?⑸땲?? 吏덈Ц???댄빐?섏? 紐삵븯嫄곕굹 ?섏빟?덇낵 愿?⑥씠 ?녿뒗 吏덈Ц?낅땲??"
    }

