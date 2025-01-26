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


def format_item(item: dict[str, Any]) -> str:
    """Format a Zotero item's metadata as a readable string"""
    data = item["data"]

    # Basic metadata
    formatted = [
        f"Title: {data.get('title', 'Untitled')}",
        f"Type: {data.get('itemType', 'unknown')}",
        f"Date: {data.get('date', 'No date')}",
    ]

    # Creators
    creators = []
    for creator in data.get("creators", []):
        if "firstName" in creator and "lastName" in creator:
            creators.append(f"{creator['lastName']}, {creator['firstName']}")
        elif "name" in creator:
            creators.append(creator["name"])
    if creators:
        formatted.append(f"Authors: {'; '.join(creators)}")

    # Abstract
    if abstract := data.get("abstractNote"):
        formatted.append(f"\nAbstract:\n{abstract}")

    # Tags
    if tags := data.get("tags"):
        tag_list = [tag["tag"] for tag in tags]
        formatted.append(f"\nTags: {', '.join(tag_list)}")

    # URLs and DOIs
    if url := data.get("url"):
        formatted.append(f"URL: {url}")
    if doi := data.get("DOI"):
        formatted.append(f"DOI: {doi}")

    # Notes
    if notes := item.get("meta", {}).get("numChildren", 0):
        formatted.append(f"Number of notes: {notes}")

    return "\n".join(formatted)


# Register the actual resource handlers
@mcp.resource("zotero://items/{item_key}")
def get_item(item_key: str) -> str:
    """Get detailed information about a specific Zotero item

    Args:
        item_key: The unique Zotero item key
    """
    zot = get_zotero_client()

    try:
        item: Any = zot.item(item_key)
        if not item:
            return f"No item found with key: {item_key}"
        return format_item(item)
    except Exception as e:
        return f"Error retrieving item: {str(e)}"


@mcp.tool()
def search_items(query: str, limit: int | None = 10) -> str:
    """Search for items in your Zotero library

    Args:
        query: Search query string
        limit: Maximum number of results to return (default: 10)

    Returns a formatted string containing search results, with each item including:
        - Title and type
        - Authors
        - Date
        - Resource ID (can be used with zotero://items/{key} to get full details)
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

        # Get item key for resource reference
        item_key = item.get("key", "")
        resource_uri = f"zotero://items/{item_key}"

        # Build formatted entry
        entry = [
            f"- {title} ({item_type})",
            f"  Authors: {creator_str}",
            f"  Date: {date}",
            f"  Resource ID: {resource_uri}\n",
        ]
        formatted_results.append("\n".join(entry))

    return "\n".join(formatted_results)
