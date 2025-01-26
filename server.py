# server.py
import os
from dotenv import load_dotenv
from typing import Any
from mcp.server.fastmcp import FastMCP
from pyzotero import zotero

# Load environment variables
load_dotenv()

# Create an MCP server
mcp = FastMCP("Zotero")


# Initialize Zotero client
def get_zotero_client():
    """Get authenticated Zotero client using environment variables"""
    library_id = os.getenv("ZOTERO_LIBRARY_ID")
    library_type = os.getenv("ZOTERO_LIBRARY_TYPE", "user")
    api_key = os.getenv("ZOTERO_API_KEY")

    if not all([library_id, api_key]):
        raise ValueError(
            "Missing required environment variables. Please set ZOTERO_LIBRARY_ID and ZOTERO_API_KEY"
        )

    return zotero.Zotero(library_id, library_type, api_key)


@mcp.tool()
def search_items(query: str, limit: int | None = 10) -> str:
    """Search for items in your Zotero library

    Args:
        query: Search query string
        limit: Maximum number of results to return (default: 10)
    """
    zot = get_zotero_client()

    # Search using the q parameter
    zot.add_parameters(q=query, limit=limit)
    # n.b. types for this return do not work, it's a parsed JSON object
    results: Any = zot.items()

    if not results:
        return "No items found matching your query."

    # Format results
    formatted_results = []
    for item in results:
        data = item["data"]
        # Get basic metadata
        title = data.get("title", "Untitled")
        item_type = data.get("itemType", "unknown")
        date = data.get("date", "")

        # Format creators
        creators = []
        for creator in data.get("creators", []):
            if "firstName" in creator and "lastName" in creator:
                creators.append(f"{creator['lastName']}, {creator['firstName']}")
            elif "name" in creator:
                creators.append(creator["name"])
        creator_str = "; ".join(creators) if creators else "No authors"

        # Build formatted entry
        entry = f"- {title} ({item_type})\n  Authors: {creator_str}\n  Date: {date}\n"
        formatted_results.append(entry)

    return "\n".join(formatted_results)
