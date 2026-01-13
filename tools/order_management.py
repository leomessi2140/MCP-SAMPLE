# =============================================================================
# ORDER MANAGEMENT (Deterministic / Structured Commands)
# =============================================================================

from typing import Dict, List, Any
import logging
from ..utils import fetch_all_tenant_contexts

logger = logging.getLogger(__name__)

def execute_order_management(query: str, tenant_key: str, config: dict) -> str:
    """
    Since we removed internal LLM parsing, this tool now expects the MCP Client (ChatGPT)
    to decipher the intent and pass a structured command string in `query`.
    
    Expected `query` format (Stringified JSON or simple command):
    "ADD: <menu_id>:<qty>"
    "REMOVE: <menu_id>:<qty>"
    "CLEAR"
    
    *Note*: Ideally, we'd change the tool signature to accept separate arguments, 
    but to keep the wrapper consistent as requested:
    """
    
    # Simple formatting instruction for the LLM calling this tool
    # The LLM should have seen this instruction in the tool description or system prompt.
    # For now, we will try to parse a simple text protocol.
    
    if not config:
        return "Error: No session config provided."

    food_list = config.setdefault("food_list", {})
    command = query.strip()
    
    # Fetch menu for ID validation
    tenant_contexts = fetch_all_tenant_contexts()
    tenant_data = tenant_contexts.get(tenant_key, {})
    menu_data = tenant_data.get("menu", [])
    
    # Map Name -> ID (for robustness if LLM sends names)
    name_to_id = {
        (m.get("name") or m.get("item_name", "")).lower(): str(m.get("menu_id")) 
        for m in menu_data
    }
    id_to_item = {str(m.get("menu_id")): m for m in menu_data}

    # --- PARSING LOGIC (Simple Rule-Based) ---
    action = "none"
    target_id = None
    qty = 1
    
    # normalize
    cmd_upper = command.upper()
    
    if cmd_upper.startswith("CLEAR") or "CANCEL ORDER" in cmd_upper:
        config["food_list"] = {}
        return "Order cleared."
        
    parts = command.split(":") 
    # specific protocol: "ADD:101:2" or "REMOVE:Burger:1"
    
    if len(parts) >= 2:
        op = parts[0].strip().upper()
        item_ref = parts[1].strip()
        try:
            qty = int(parts[2].strip()) if len(parts) > 2 else 1
        except:
            qty = 1
            
        # Resolve Item ID
        if item_ref in id_to_item:
            target_id = item_ref
        elif item_ref.lower() in name_to_id:
            target_id = name_to_id[item_ref.lower()]
        
        if op == "ADD":
            action = "add"
        elif op == "REMOVE":
            action = "remove"
            
    # --- EXECUTION ---
    if action == "add" and target_id:
        food_list[target_id] = food_list.get(target_id, 0) + qty
        item_name = id_to_item[target_id].get("name")
        return f"Added {qty}x {item_name}. Current Cart: {get_readable_cart(food_list, id_to_item)}"

    elif action == "remove" and target_id:
        if target_id in food_list:
            current = food_list[target_id]
            new_qty = max(0, current - qty)
            if new_qty == 0:
                del food_list[target_id]
            else:
                food_list[target_id] = new_qty
            return f"Removed {qty}x. Current Cart: {get_readable_cart(food_list, id_to_item)}"
        return "Item not in cart."

    else:
        # Fallback: If we couldn't parse, return instruction
        return (
            "COMMAND_ERROR: Please send commands in format: 'ADD:ItemID:Qty' or 'REMOVE:ItemID:Qty'. "
            f"Available Item IDs: {', '.join([f'{m['name']}={m['menu_id']}' for m in menu_data[:5]])}..."
        )

def get_readable_cart(food_list, id_to_item):
    items = []
    for mid, q in food_list.items():
        name = id_to_item.get(mid, {}).get("name", mid)
        items.append(f"{q}x {name}")
    return ", ".join(items) if items else "Empty"
