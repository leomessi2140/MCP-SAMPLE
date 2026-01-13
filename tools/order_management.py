# =============================================================================
# ORDER MANAGEMENT (Unified for Pre + Post Placement)
# =============================================================================

from typing import Dict, List
from decimal import Decimal
from sqlalchemy import text
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
import logging

# Core application imports
# REFACTORED: Use local utils
from ..utils import GLOBAL_LLM_FLASH, establish_database_connection_pool, fetch_all_tenant_contexts
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# =============================================================================
# MODELS
# =============================================================================

class FoodItem(BaseModel):
    name: str
    quantity: int

class FoodListUpdate(BaseModel):
    items: List[FoodItem]
    action: str
    should_update: bool
    has_customization: bool
    customization_text: str

# =============================================================================
# POST-PLACEMENT DETECTION
# =============================================================================

def is_post_placement(config: dict) -> bool:
    if not config:
        return False
    return config.get("phase", "") == "ORDER_PLACED"

# =============================================================================
# LLM EXTRACTION
# =============================================================================

def extract_order_items_from_query(query: str, tenant_key: str, config: dict):
    parser = PydanticOutputParser(pydantic_object=FoodListUpdate)
    
    tenant_contexts = fetch_all_tenant_contexts()
    tenant_data = tenant_contexts.get(tenant_key, {})
    menu_data = tenant_data.get("menu", [])
    
    menu_summary = "\n".join(
        f"{m.get('name') or m.get('item_name', 'Unknown')} (menu_id {m.get('menu_id')}) - ₹{m.get('price', 0)}" 
        for m in menu_data
    ) or "No menu available."

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are a **food order assistant** responsible for managing and correcting food orders.
Analyze the user's message carefully and determine their exact intent.

You must handle **ALL** of the following operations:
1. **ADD** — Add new food items with specified quantities.
2. **REMOVE** — Remove specific food items or portions.
3. **MODIFY** — Change item quantities (increase or decrease).
4. **CLEAR** — Clear the entire order or cancel all items.
5. **CANCELLATION** — Detect whether the user means FULL or PARTIAL cancellation.
6. **CUSTOMIZATION** — Identify customization requests (spice level, portion size, toppings, etc.).

Use the following tenant menu for grounding:
{menu_summary}

==================== RULES ====================
- Always map user mentions to existing menu items (no invention).
- FULL Cancellation ("cancel order") -> action="clear", should_update=true
- PARTIAL Cancellation ("remove burger") -> action="remove", should_update=true
- Customization: "spicy", "no onions" -> has_customization=true

{format_instructions}
"""
        ),
        ("human", "{message}"),
    ]).partial(
        format_instructions=parser.get_format_instructions(),
        menu_summary=menu_summary
    )

    model = GLOBAL_LLM_FLASH
    chain = prompt | model | parser
    try:
        result = chain.invoke({"message": query})
    except Exception as e:
        logger.error(f"❌ JSON parsing failed in extract_order_items_from_query: {e}")
        result = FoodListUpdate(
            items=[],
            action="none",
            should_update=False,
            has_customization=False,
            customization_text=""
        )

    if result.has_customization and config is not None:
        existing = config.get("food_customization_details", "")
        text = result.customization_text.strip()
        config["food_customization_details"] = f"{existing}; {text}" if existing else text
        logger.info(f"🧂 Stored customization details: {config['food_customization_details']}")

    return result

# =============================================================================
# MAIN EXECUTION
# =============================================================================

def execute_order_management(query: str, tenant_key: str, config: dict) -> str:
    """
    Execute order management operations (add/remove/modify/clear).
    """
    current_phase = config.get("phase", "IDLE")
    post_placement = is_post_placement(config)

    result = extract_order_items_from_query(query, tenant_key, config)
    food_list = config.setdefault("food_list", {})

    tenant_contexts = fetch_all_tenant_contexts()
    tenant_data = tenant_contexts.get(tenant_key, {})
    menu_data = tenant_data.get("menu", [])
    
    name_to_id = {
        (m.get("name") or m.get("item_name", "")).lower(): str(m.get("menu_id")) 
        for m in menu_data
    }
    id_to_item = {str(m.get("menu_id")): m for m in menu_data}

    if result.action == "clear":
        config["food_list"] = {}
        if post_placement:
            return "FULL_CANCELLATION_CONFIRMED"
        else:
            return "Order cleared! Ready to start fresh?"

    # --- Apply Changes ---
    actually_added = []
    actually_removed = []
    actually_modified = []
    not_found_items = []
    
    for item in result.items:
        name = item.name.lower()
        qty = item.quantity
        menu_id = name_to_id.get(name)
        if not menu_id:
            not_found_items.append(item.name)
            continue

        if result.action == "add":
            food_list[menu_id] = food_list.get(menu_id, 0) + qty
            actually_added.append(item)
        elif result.action == "remove":
            if menu_id in food_list:
                current_qty = food_list[menu_id]
                new_qty = max(0, current_qty - qty)
                if new_qty == 0:
                    del food_list[menu_id]
                else:
                    food_list[menu_id] = new_qty
                actually_removed.append(item)
            else:
                not_found_items.append(item.name)
        elif result.action == "modify":
            if qty == 0:
                if menu_id in food_list:
                    food_list.pop(menu_id, None)
                    actually_removed.append(item)
                else:
                    not_found_items.append(item.name)
            else:
                food_list[menu_id] = qty
                actually_modified.append(item)

    food_list = {k: v for k, v in food_list.items() if v > 0}
    config["food_list"] = food_list

    if current_phase != "ORDER_PLACED":
        config["phase"] = "ORDERING"

    # --- Responses ---
    if result.action == "remove" and post_placement and not food_list:
        return "FULL_CANCELLATION_CONFIRMED"

    if result.action == "add":
        if actually_added:
            added = [f"{i.quantity}x {i.name}" for i in actually_added]
            return f"Added {', '.join(added)} to your order!"
        return "I couldn't find those items in our menu."
            
    elif result.action == "remove":
        if actually_removed:
            removed = [f"{i.quantity}x {i.name}" for i in actually_removed]
            return f"Removed {', '.join(removed)} from your order!"
        return f"Couldn't process removal. {', '.join(not_found_items)} not in order." if not_found_items else "Nothing removed."
            
    elif result.action == "modify":
        if actually_modified:
            modified = [f"{i.quantity}x {i.name}" for i in actually_modified]
            return f"Updated your order: {', '.join(modified)}"
        return "I couldn't find those items to modify."

    else:
        return "Sorry, I couldn't process that order request."
