"""
LLM tools for web content extraction using Trafilatura.

Provides a web_fetch tool that extracts clean, readable content from web pages,
returning markdown-formatted text with metadata suitable for LLM processing.
"""
import json
import re
from urllib.parse import urljoin

import llm
import trafilatura
from lxml import html as lxml_html
from trafilatura.settings import use_config

# Configure trafilatura with a browser-like user agent
_config = use_config()
_config.set("DEFAULT", "USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def fetch_url(
    url: str,
    include_links: bool = True,
    include_images: bool = False,
    include_metadata: bool = True,
    extract_links: bool = False
) -> str:
    """
    Fetch and extract main content from a web page.

    Use this tool to retrieve clean, readable content from any web URL.
    Returns markdown-formatted text extracted from the page, excluding
    navigation, ads, and other boilerplate content.

    Args:
        url: The URL to fetch content from (must be a valid HTTP/HTTPS URL)
        include_links: Include hyperlinks in the output (default: True)
        include_images: Include image descriptions with alt text (default: False)
        include_metadata: Include page metadata like title, author, date (default: True)
        extract_links: Extract ALL links from page including navigation/sidebars (default: False).
            When True, bypasses content extraction and returns a list of all links found on the page.
            Useful for finding download links, PDF links, or navigation that would otherwise be filtered.

    Returns:
        JSON with extracted content, metadata, and any errors.
        When extract_links=True, returns JSON with links array instead of content.
    """
    # Validate URL
    if not url:
        return json.dumps({
            "error": "URL is required",
            "url": url,
            "metadata": {},
            "content": ""
        }, indent=2)

    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        return json.dumps({
            "error": "Invalid URL: must start with http:// or https://",
            "url": url,
            "metadata": {},
            "content": ""
        }, indent=2)

    try:
        # Fetch the page content
        downloaded = trafilatura.fetch_url(url, config=_config)

        if downloaded is None:
            return json.dumps({
                "error": "Failed to fetch URL: page not accessible or returned empty content",
                "url": url,
                "metadata": {},
                "content": ""
            }, indent=2)

        # Extract ALL links if requested (bypasses content filtering)
        if extract_links:
            tree = lxml_html.fromstring(downloaded)
            seen = set()
            links = []
            for a in tree.xpath('//a[@href]'):
                href = (a.get('href') or '').strip()
                # Skip empty, anchor-only, javascript, mailto, tel, data links
                if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:', 'data:')):
                    continue
                absolute_url = urljoin(url, href)
                # Deduplicate by URL
                if absolute_url in seen:
                    continue
                seen.add(absolute_url)
                text = (a.text_content() or '').strip()
                links.append({'url': absolute_url, 'text': text})

            return json.dumps({
                "url": url,
                "links": links,
                "link_count": len(links),
                "error": None
            }, indent=2)

        # Extract content with specified options
        content = trafilatura.extract(
            downloaded,
            output_format="markdown",
            include_links=include_links,
            include_images=include_images,
            include_tables=True,
            include_formatting=True,
            favor_recall=True,
            url=url
        )

        if content is None or content.strip() == "":
            return json.dumps({
                "error": "No extractable content found on page",
                "url": url,
                "metadata": {},
                "content": ""
            }, indent=2)

        # Clean up excessive newlines (like llm-fragments-site-text does)
        content = re.sub(r"\n{3,}", "\n\n", content)

        # Extract metadata if requested
        metadata = {}
        if include_metadata:
            meta = trafilatura.extract_metadata(downloaded)
            if meta:
                if meta.sitename:
                    metadata["sitename"] = meta.sitename
                if meta.title:
                    metadata["title"] = meta.title
                if meta.author:
                    metadata["author"] = meta.author
                if meta.date:
                    metadata["date"] = meta.date
                if meta.description:
                    metadata["description"] = meta.description

        return json.dumps({
            "url": url,
            "metadata": metadata,
            "content": content,
            "error": None
        }, indent=2)

    except Exception as e:
        error_msg = str(e)

        # Provide more helpful error messages for common issues
        if "ConnectionError" in error_msg or "connection" in error_msg.lower():
            error_msg = f"Connection error: unable to reach {url}"
        elif "Timeout" in error_msg or "timeout" in error_msg.lower():
            error_msg = f"Request timed out for {url}"
        elif "SSL" in error_msg or "certificate" in error_msg.lower():
            error_msg = f"SSL/TLS certificate error for {url}"
        elif "404" in error_msg:
            error_msg = f"Page not found (404) at {url}"
        elif "403" in error_msg:
            error_msg = f"Access forbidden (403) at {url}"
        elif "500" in error_msg or "502" in error_msg or "503" in error_msg:
            error_msg = f"Server error at {url}"

        return json.dumps({
            "error": error_msg,
            "url": url,
            "metadata": {},
            "content": ""
        }, indent=2)


@llm.hookimpl
def register_tools(register):
    """Register web fetch tool."""
    register(fetch_url)
