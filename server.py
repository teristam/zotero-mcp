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


def get_attachment_details(
    zot: Any, item: dict[str, Any]
) -> tuple[str | None, str | None]:
    """Get attachment ID and content type for a Zotero item

    Args:
        zot: Zotero client instance
        item: Zotero item dictionary

    Returns:
        Tuple of (attachment_key, content_type)
        Returns (None, None) if no suitable attachment is found
    """
    data = item.get("data", {})
    item_type = data.get("itemType")

    # Direct attachment - check if it's a PDF or other supported type
    if item_type == "attachment":
        content_type = data.get("contentType")
        return data.get("key"), content_type

    # For regular items, look for child attachments
    try:
        children = zot.children(data.get("key", ""))
        # Group attachments by content type and size
        pdfs = []
        htmls = []
        others = []

        for child in children:
            child_data = child.get("data", {})
            if child_data.get("itemType") == "attachment":
                content_type = child_data.get("contentType")
                file_size = child_data.get("md5", "")  # Use md5 as proxy for size

                if content_type == "application/pdf":
                    pdfs.append((child_data.get("key"), content_type, file_size))
                elif content_type == "text/html":
                    htmls.append((child_data.get("key"), content_type, file_size))
                else:
                    others.append((child_data.get("key"), content_type, file_size))

        # Return first match in priority order
        if pdfs:
            pdfs.sort(key=lambda x: x[2], reverse=True)
            return pdfs[0][0], pdfs[0][1]
        if htmls:
            htmls.sort(key=lambda x: x[2], reverse=True)
            return htmls[0][0], htmls[0][1]
        if others:
            others.sort(key=lambda x: x[2], reverse=True)
            return others[0][0], others[0][1]
    except Exception:
        pass

    return None, None


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
@mcp.resource("zotero://items/{item_key}/metadata")
def get_item_metadata(item_key: str) -> str:
    """Get metadata information about a specific Zotero item

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


# Register the actual resource handlers
@mcp.resource("zotero://items/{item_key}/fulltext")
def get_item_fulltext(item_key: str) -> str:
    """Get the full text content of a specific Zotero item

    Args:
        item_key: The unique Zotero item key
    """
    zot = get_zotero_client()

    try:
        item: Any = zot.item(item_key)
        if not item:
            return f"No item found with key: {item_key}"

            # Fetch full-text content
        attachment_key, content_type = get_attachment_details(zot, item)

        if attachment_key:
            full_text_data: Any = zot.fulltext_item(attachment_key)
            if full_text_data and "content" in full_text_data:
                item_text = full_text_data["content"]
            else:
                item_text = "[Attachment available but text extraction not possible]"
        else:
            item_text = "[No suitable attachment found for full text extraction]"

        return f"{format_item(item)}\nAttachment ID: {attachment_key or ''}\n\nFull Text:\n{item_text}"
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
        - Resource ID (can be used with zotero://items/{key}/... to get full details)
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
