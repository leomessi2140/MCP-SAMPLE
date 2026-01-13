# =============================================================================
# MENU GUIDE TOOL (Combined Recommendation & Category Filter)
# =============================================================================

from typing import List, Optional, Dict, Union
import json
import logging
import random
from decimal import Decimal

# LangChain imports
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

# Pydantic models
from pydantic import BaseModel, Field

# Core application imports
# REFACTORED: Use local utils
from ..utils import GLOBAL_LLM_FLASH, fetch_all_tenant_contexts
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class MenuGuideResponse(BaseModel):
    """Unified response for menu navigation and item recommendations"""
    intent: str = Field(description="User intent: 'category_filter', 'recommendation', 'availability', 'other'")
    category_match: Optional[str] = Field(description="Exact category name if intent is category_filter, else empty")
    items: List[Dict] = Field(default_factory=list, description="List of matching menu items (name, price, menu_id)")
    response_text: str = Field(description="Natural language response for the user")

# =============================================================================
# TOOL EXECUTION
# =============================================================================

def execute_menu_guide(query: str, tenant_key: str, config: dict = None) -> str:
    """
    Unified tool handling both category navigation ("Show me burgers") 
    and item recommendations ("What's good?").
    """
    if config is not None:
        config["phase"] = "MENU_BROWSING"
    
    # 1. Fetch Data (using local utils)
    tenant_contexts = fetch_all_tenant_contexts()
    tenant_data = tenant_contexts.get(tenant_key, {})
    menu_data = tenant_data.get("menu", [])
    
    if not menu_data:
        return json.dumps({
            "intent": "other",
            "response_text": "I'm sorry, I couldn't find any menu data for this restaurant.",
            "items": []
        })

    # 2. Process Categories (for Filter Logic)
    unique_categories = []
    seen_cats = set()
    for entry in menu_data:
        cat = entry.get("category", "").strip()
        if cat and cat.upper() not in seen_cats:
            unique_categories.append(cat)
            seen_cats.add(cat.upper())
    unique_categories.sort()
    categories_str = ", ".join(unique_categories)

    # 3. Process Menu Summary (for Recommendation Logic)
    menu_data_shuffled = menu_data.copy()
    random.shuffle(menu_data_shuffled)
    
    menu_summary = "\n".join(
        f"{m.get('name') or m.get('item_name', 'Unknown')} (ID: {m.get('menu_id')}) - ₹{m.get('price', 0)} - {'(Veg)' if m.get('is_veg') else '(Non-Veg)'} - Category: {m.get('category', 'Unknown')}"
        for m in menu_data_shuffled[:80] # Increased context slightly
    )

    # 4. Context Building
    current_category = config.get("current_category", "") if config else ""
    context_instruction = ""
    if current_category:
        context_instruction = f"""
CURRENT CONTEXT: User is browsing the "{current_category}" category.
- If user asks for recommendations WITHOUT specifying a different category → Recommend items from "{current_category}" ONLY
- If user asks "what do you recommend" or "suggest something" → Prioritize items from "{current_category}"
- If user explicitly mentions a different category → Ask if they want recommendations from that category or continue with "{current_category}"
- If user switches context (e.g., "show me beverages" after browsing desserts) → Clear this context
"""

    cart_items = []
    if config:
        food_list = config.get("food_list", {})
        if isinstance(food_list, dict):
            cart_items = list(food_list.keys())
        elif isinstance(food_list, list):
            cart_items = food_list
            
    cart_context = ""
    if cart_items:
        cart_context = f"""
CURRENT CART: User has the following items in their cart: {', '.join(str(item) for item in cart_items)}.

CART-AWARE BEHAVIOR (Prioritize this for recommendations):
- Analyze the "vibe" or cuisine of the current cart items.
- Recommend COMPLEMENTARY items that pair well with what is already in the cart.
- **Meal Completion Check (STRICT PRIORITY)**: 
  1. **PRIORITY 1**: If user has ONLY Starters or Soups -> You MUST suggest a **MAIN COURSE** (Biryani, Rice, Noodles, or Gravy/Bread).
  2. **PRIORITY 2**: If user has a Main Course but no Side/Drink -> Suggest a Side Dish or Drink.
  3. **PRIORITY 3**: If user has Main Course + Side/Drink -> Suggest a Dessert to finish the meal.
- **Flavor Balancing**:
  - If cart has Spicy items -> Suggest Cooling drinks or Sweet desserts.
  - If cart has Dry items -> Suggest Gravies.
- Explicitly mention WHY you are recommending the item based on their cart (e.g., "Since you have the Burger...").
"""

    # 5. LLM Prompting
    parser = PydanticOutputParser(pydantic_object=MenuGuideResponse)
    format_instructions = parser.get_format_instructions()
    format_instructions = format_instructions.replace("{", "{{").replace("}", "}}")

    system_prompt = """You are an intelligent Menu Guide. Your job is to understand if the user wants to NAVIGATE to a category or Find specific ITEMS.

AVAILABLE CATEGORIES: {categories_str}

MENU SNAPSHOT (Sample items for recommendation): 
{menu_summary}

{context_instruction}
{cart_context}

IMPORTANT: Classify the user's intent into ONE of the following types:

---
### 1. CATEGORY NAVIGATION (Intent: 'category_filter')
**Trigger**: User wants to see/browse a whole section of the menu.
- Keywords: "show me", "go to", "open", "browse", "list", "menu for..."
- Examples: "Show me burgers", "Do you have desserts?", "I want beverages", "Back to start", "Vegetarian options" (if Vegetarian is a category).

**Rules**:
1. Match user query to a category from the **AVAILABLE CATEGORIES** list above.
2. Return category name **EXACTLY** as it appears in the list (preserve casing).
3. If no exact category match is found, but the intent is clearly navigation, return empty category_match.

---
### 2. RECOMMENDATION / SEARCH (Intent: 'recommendation', 'availability')
**Trigger**: User wants specific item suggestions or checks specific item availability.
- Keywords: "recommend", "suggest", "best", "do you have [item name]?"

**CRITICAL RULE - SINGLE CATEGORY ONLY**: 
- All recommended items MUST come from the SAME category.
- If items span multiple categories, pick the MOST RELEVANT category and recommend 2-3 items from ONLY that category.
- Example: "I want grilled chicken" → Pick ONLY from "GRILLS & BARBEQUE" category.
- Example: "Suggest ice cream" → Pick ONLY from "ICE CREAMS" category.

**Strict Dietary Rules**:
- If user mentions "Veg" or "Vegetarian": **ONLY** recommend items marked as (Veg).
- If user mentions "Non-Veg": **ONLY** recommend items marked as (Non-Veg).
- If user does NOT mention dietary preference: You can recommend both.
- If user asks for "Veg" and NO Veg items are found: say "I couldn't find any Vegetarian options for that."

**Sub-Types**:
- **'availability'**: Queries like "do you have pasta?", "is x available?".
- **'recommendation'**: Queries like "what's good?", "suggest something". (Apply Cart-Aware behavior if Cart exists).

**Rules**:
1. Use **ONLY** items from the Menu Snapshot. Do not hallucinate items.
2. For 'availability', if item is found, return it. If not, say we don't have it.
3. ALWAYS identify and return the category that ALL recommended items belong to.

**BROAD GROUPS RULE (CRITICAL)**:
- If user asks for a BROAD group that contains multiple categories (e.g., "Desserts", "Starters", "Main Course", "Drinks") AND has not specified a sub-category:
  - Do **NOT** return a list of items.
  - Instead, list the AVAILABLE CATEGORIES that fit that group.
  - Example: User "Recommend desserts" -> Bot "We have Kunafa, Faloodas, and Ice Creams. Which would you like?"
  - Return `items: []` (Empty list).

---

**OUTPUT RULES**:
1. **intent**: Must be one of valid strings.
2. **category_match**: 
   - For 'category_filter': exact string from Available Categories
   - For 'recommendation'/'availability': The category that ALL items belong to (REQUIRED if items are returned)
3. **items**: List of {{"name": "...", "price": "...", "menu_id": "..."}} for recommendations.
   - ALL items must be from the SAME category
4. **response_text**:
   - MUST be provided.
   - Natural, conversational, suitable for voice output.
   - NO symbols (*, -), bullets, or markdown formatting.
   - For recommendations, do NOT mention price in the text unless asked. Just mention the names and why they are good.

""" + format_instructions

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{query}"),
    ]).partial(
        categories_str=categories_str,
        menu_summary=menu_summary,
        context_instruction=context_instruction,
        cart_context=cart_context
    )

    model = GLOBAL_LLM_FLASH
    chain = prompt | model | parser

    try:
        result = chain.invoke({"query": query})
        
        # 6. Post-Processing & Response Formatting
        
        # CASE A: Category Navigation
        if result.intent == 'category_filter':
            if result.category_match:
                # Update Session State
                if config is not None:
                    config["current_category"] = result.category_match
                    
                return {
                    "type": "menu",
                    "sub_type": "category",
                    "data": result.category_match,
                    "transcript": result.response_text or f"Here is our {result.category_match} menu."
                }
            else:
                return {
                    "type": "menu",
                    "sub_type": "category",
                    "data": "",
                    "transcript": "I couldn't find that category. Please allow me to show you the main menu."
                }

        # CASE B: Recommendation / Other
        else:
            category_for_items = ""
            if result.items:
                first_id = result.items[0].get("menu_id")
                if first_id:
                    for m in menu_data:
                        if str(m.get("menu_id")) == str(first_id):
                            category_for_items = m.get("category", "")
                            break
                
                if category_for_items:
                    for item in result.items:
                        item_id = item.get("menu_id")
                        if item_id:
                            for m in menu_data:
                                if str(m.get("menu_id")) == str(item_id):
                                    item_cat = m.get("category", "")
                                    if item_cat and item_cat != category_for_items:
                                        logger.warning(f"Mixed categories detected: {category_for_items} vs {item_cat}")
                                    break
            
            final_category = result.category_match or category_for_items
            if final_category and config is not None:
                config["current_category"] = final_category
            
            formatted_response = {
                "query_type": result.intent,
                "items": result.items,
                "category": final_category,
                "response_text": result.response_text
            }
            
            if not result.response_text:
                if result.items:
                    names = [i.get('name', 'item') for i in result.items[:2]]
                    formatted_response["response_text"] = f"I found {', '.join(names)}. Would you like to try them?"
                else:
                    formatted_response["response_text"] = "I couldn't find anything matching that request."
            
            return formatted_response

    except Exception as e:
        logger.error(f"Error in menu_guide_tool: {e}")
        return {
            "intent": "other",
            "items": [],
            "response_text": "I'm having trouble understanding the menu right now. Could you ask again?"
        }
