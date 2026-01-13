import logging
from typing import Dict, Any

# FastMCP imports
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Local tool imports (Refactored to point to local tools folder)
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
    Search the menu, filter by category, or get food recommendations.
    """
    config = get_session(session_id)
    logger.info(f"Tool 'menu_guide' called for session {session_id}")
    result = execute_menu_guide(query, tenant_key, config=config)
    return str(result)

@mcp.tool()
def order_management(query: str, tenant_key: str, session_id: str = "default") -> str:
    """
    Add, remove, or modify items in the order.
    """
    config = get_session(session_id)
    logger.info(f"Tool 'order_management' called for session {session_id}")
    result = execute_order_management(query, tenant_key, config=config)
    return str(result)

if __name__ == "__main__":
    mcp.run()
