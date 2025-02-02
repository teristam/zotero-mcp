# server.py
import os
import textwrap
from typing import Any, Literal

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
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
    local = os.getenv("ZOTERO_LOCAL", "").lower() in ["true", "yes", "1"]
    if local and not library_id:
        # Indicates "current user" for the local API
        library_id = "0"

    if not local or all([library_id, api_key]):
        raise ValueError(
            "Missing required environment variables. Please set ZOTERO_LIBRARY_ID and ZOTERO_API_KEY"
        )

    return zotero.Zotero(
        library_id=library_id,
        library_type=library_type,
        api_key=api_key,
        local=local,
    )


class AttachmentDetails(BaseModel):
    key: str
    content_type: str


def get_attachment_details(
    zot: Any,
    item: dict[str, Any],
) -> AttachmentDetails | None:
    """Get attachment ID and content type for a Zotero item"""
    data = item.get("data", {})
    item_type = data.get("itemType")

    # Direct attachment - check if it's a PDF or other supported type
    if item_type == "attachment":
        content_type = data.get("contentType")
        return AttachmentDetails(
            key=data.get("key"),
            content_type=content_type,
        )

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
            return AttachmentDetails(
                key=pdfs[0][0],
                content_type=pdfs[0][1],
            )
        if htmls:
            htmls.sort(key=lambda x: x[2], reverse=True)
            return AttachmentDetails(
                key=htmls[0][0],
                content_type=htmls[0][1],
            )
        if others:
            others.sort(key=lambda x: x[2], reverse=True)
            return AttachmentDetails(
                key=others[0][0],
                content_type=others[0][1],
            )
    except Exception:
        pass

    return None


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

            Attachment Item Key: {attachment.key if attachment else ''}

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
