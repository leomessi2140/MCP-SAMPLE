import logging
from typing import Dict, Any

# FastMCP imports
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Local tool imports
from tools.menu_guide_tool import execute_menu_guide
from tools.order_management import execute_order_management

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

# Load environment variables
load_dotenv()

# Initialize FastMCP Server
mcp = FastMCP("food-order-bot")

# In-memory session storage
SESSIONS: Dict[str, Dict[str, Any]] = {}

def get_session(session_id: str) -> Dict[str, Any]:
    """Retrieve or create a session config."""
    if session_id not in SESSIONS:
        logger.info(f"Creating new session: {session_id}")
        SESSIONS[session_id] = {
            "phase": "IDLE",
            "current_category": "",
            "food_list": {},
            "food_customization_details": ""
        }
    return SESSIONS[session_id]

@mcp.tool()
def menu_guide(query: str, tenant_key: str, session_id: str = "default") -> str:
    """
    RETURNS RAW MENU DATA. 
    Use this to "read" the menu. The output is a raw list of items.
    YOU (The AI) must parse this data to answer user questions or make recommendations
    based on the user's 'query'. 
    """
    config = get_session(session_id)
    # The 'query' here is mostly for logging context in the tool, 
    # since the tool just returns the whole menu for the AI to process.
    result = execute_menu_guide(query, tenant_key, config=config)
    return str(result)

@mcp.tool()
def order_management(query: str, tenant_key: str, session_id: str = "default") -> str:
    """
    MANAGES THE ORDER CART.
    Requires STRICT COMMAND FORMAT in the 'query' argument:
    - "ADD:MenuItemID:Quantity" (e.g., "ADD:101:2")
    - "REMOVE:MenuItemID:Quantity" (e.g., "REMOVE:Burger:1")
    - "CLEAR"
    
    YOU (The AI) must generate these commands based on user intent.
    DO NOT pass natural language like "I want a burger".
    """
    config = get_session(session_id)
    result = execute_order_management(query, tenant_key, config=config)
    return str(result)

if __name__ == "__main__":
    mcp.run()
