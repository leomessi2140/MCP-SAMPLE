import os
import logging
from typing import Dict, Any, List
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

# Load environment variables
load_dotenv()
logger = logging.getLogger("mcp_utils")

# =============================================================================
# CONSTANTS & CONFIG
# =============================================================================
MONGO_URI = os.getenv("MONGO_URI")
DATABASE_URL = os.getenv("DATABASE_URL")

# =============================================================================
# DATABASE
# =============================================================================
def establish_database_connection_pool():
    """Establish database connection pool with connection management"""
    if not DATABASE_URL:
        logger.warning("DATABASE_URL not set, skipping SQL pool creation")
        return None
        
    return create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600
    )

# =============================================================================
# MONGODB & TENANT CONTEXT
# =============================================================================
# Cache for tenant contexts
_TENANT_CONTEXTS_CACHE = None

def fetch_all_tenant_contexts():
    """
    Fetch all tenant contexts and menu data from MongoDB.
    Returns a dictionary mapping tenant keys to their configuration data.
    """
    global _TENANT_CONTEXTS_CACHE
    
    if _TENANT_CONTEXTS_CACHE is not None:
        return _TENANT_CONTEXTS_CACHE
    
    if not MONGO_URI:
        logger.error("MONGO_URI not set")
        return {}

    try:
        mongo_client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
        db = mongo_client["FOOD_ORDER_AI"]
        collection = db["TENANT_INFO"]
        
        all_tenants = collection.find({})
        tenant_contexts = {}
        
        for tenant_doc in all_tenants:
            if "tenant_key" in tenant_doc and "context" in tenant_doc:
                tenant_key = tenant_doc["tenant_key"]
                context_data = tenant_doc["context"]
                
                tenant_contexts[tenant_key] = {
                    "ai_name": context_data.get("meta_data", {}).get("ai_name", "Assistant"),
                    "outlet_name": context_data.get("meta_data", {}).get("outlet_name", "Our Outlet"),
                    "menu": context_data.get("menu", []),
                    "keyterms": context_data.get("keyterms", [])
                }
        
        _TENANT_CONTEXTS_CACHE = tenant_contexts
        logger.info(f"Loaded contexts for {len(tenant_contexts)} tenants")
        return tenant_contexts

    except Exception as e:
        logger.error(f"Error fetching tenant contexts: {e}")
        return {}
