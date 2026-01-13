# =============================================================================
# MENU GUIDE TOOL (Deterministic / Data-Only)
# =============================================================================

from typing import List, Dict, Any
import json
import logging
from ..utils import fetch_all_tenant_contexts

logger = logging.getLogger(__name__)

def execute_menu_guide(query: str, tenant_key: str, config: dict = None) -> str:
    """
    Returns the full menu context for the given tenant.
    The calling AI (MCP Client) is responsible for filtering/finding items based on the user's query.
    """
    if config is not None:
        config["phase"] = "MENU_BROWSING"
    
    # 1. Fetch Data
    tenant_contexts = fetch_all_tenant_contexts()
    tenant_data = tenant_contexts.get(tenant_key, {})
    menu_data = tenant_data.get("menu", [])
    
    if not menu_data:
        return "No menu data available for this restaurant."

    # 2. Format Menu for Raw Output
    # We provide a clean list of items so the LLM can "read" the menu.
    menu_summary = []
    for m in menu_data:
        name = m.get('name') or m.get('item_name', 'Unknown')
        price = m.get('price', 0)
        is_veg = m.get('is_veg', False)
        category = m.get('category', 'General')
        menu_id = m.get('menu_id')
        
        menu_summary.append(f"- [{category}] {name} (₹{price}) {'(Veg)' if is_veg else '(Non-Veg)'} [ID: {menu_id}]")
    
    # 3. Contextual Data
    current_category = config.get("current_category", "None") if config else "None"
    
    # Return raw text block
    response = [
        f"CONTEXT: User is strictly browsing. Current Category focus: {current_category}",
        "--- MENU DATA START ---",
        "\n".join(menu_summary),
        "--- MENU DATA END ---",
        "INSTRUCTION: You are the intelligent assistant. Use the above menu to answer the user's request."
    ]
    
    return "\n".join(response)
