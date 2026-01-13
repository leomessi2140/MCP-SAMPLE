# Food Order Bot MCP Server

This directory contains a standalone MCP server that exposes the Food Order Bot's capabilities (Menu Guide & Order Management) to MCP clients (like Claude Desktop, Cursor, etc.).

## Setup

1.  **Navigate to this directory**:
    ```bash
    cd MCP
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Environment Variables**:
    - Ensure `.env` is present in this directory with the following keys:
        - `MONGO_URI`
        - `DATABASE_URL` (optional, for pool)
        - `GOOGLE_API_KEY`

## Running the Server

Run the server using the `mcp-cli` or python directly if using FastMCP's built-in runner:

```bash
python server.py
# MD: mcp run server.py
```

## Available Tools

- `menu_guide(query, tenant_key, session_id)`: Browse menu, ask for recommendations.
- `order_management(query, tenant_key, session_id)`: Add/Remove items from cart.

## Directory Structure

- `server.py`: Main entry point, defines MCP tools.
- `utils.py`: Minimal utilities for DB and LLM connection (stripped of heavy framework deps).
- `tools/`: Refactored tool logic (copied from main project but using local utils).
