import textwrap
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from zotero_mcp.client import get_attachment_details, get_zotero_client

# Create an MCP server
mcp = FastMCP("Zotero")


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


@mcp.tool(
    name="zotero_item_metadata",
    description="Get metadata information about a specific Zotero item, given the item key.",
)
def get_item_metadata(item_key: str) -> str:
    """Get metadata information about a specific Zotero item"""
    zot = get_zotero_client()

    try:
        item: Any = zot.item(item_key)
        if not item:
            return f"No item found with key: {item_key}"
        return format_item(item)
    except Exception as e:
        return f"Error retrieving item metadata: {str(e)}"


@mcp.tool(
    name="zotero_item_fulltext",
    description="Get the full text content of a Zotero item, given the item key of a parent item or specific attachment.",
)
def get_item_fulltext(item_key: str) -> str:
    """Get the full text content of a specific Zotero item"""
    zot = get_zotero_client()

    try:
        item: Any = zot.item(item_key)
        if not item:
            return f"No item found with key: {item_key}"

        # Fetch full-text content
        attachment = get_attachment_details(zot, item)

        if attachment is not None:
            full_text_data: Any = zot.fulltext_item(attachment.key)
            if full_text_data and "content" in full_text_data:
                item_text = full_text_data["content"]
            else:
                item_text = "[Attachment available but text extraction not possible]"
        else:
            item_text = "[No suitable attachment found for full text extraction]"

        return textwrap.dedent(
            f"""
            {format_item(item)}

            Attachment Item Key: {attachment.key if attachment else ""}

            Full Text:\n{item_text}""".strip()
        )
    except Exception as e:
        return f"Error retrieving item full text: {str(e)}"


@mcp.tool(
    name="zotero_search_items",
    # More detail can be added if useful: https://www.zotero.org/support/dev/web_api/v3/basics#searching
    description="Search for items in your Zotero library, given a query string, query mode (titleCreatorYear or everything), and optional tag search (supports boolean searches). Returned results can be looked up with zotero_get_fulltext or zotero_get_metadata.",
)
def search_items(
    query: str,
    qmode: Literal["titleCreatorYear", "everything"] | None = "titleCreatorYear",
    tag: str | None = None,
    limit: int | None = 10,
) -> str:
    """Search for items in your Zotero library"""
    zot = get_zotero_client()

    # Search using the q parameter
    zot.add_parameters(q=query, qmode=qmode, limit=limit)
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
        item_key = item.get("key", "")
        abstract = data.get("abstractNote", "")

        # Format creators
        creators = []
        for creator in data.get("creators", []):
            if "firstName" in creator and "lastName" in creator:
                creators.append(f"{creator['lastName']}, {creator['firstName']}")
            elif "name" in creator:
                creators.append(creator["name"])
        creator_str = "; ".join(creators) if creators else "No authors"

        # Build formatted entry
        entry = [
            f"- {title} ({item_type})",
            f"  Item Key: {item_key}",
            f"  Date: {date}",
            f"  Authors: {creator_str}",
            f"  Abstract: {abstract}\n",
        ]
        formatted_results.append("\n".join(entry))

    return "\n".join(formatted_results)
