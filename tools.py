"""
Researcher agent tools — agent-specific research utilities.

LeftClaw and BGIPFS tools are provided by the shared dead-simple-agent library.
"""

import urllib.request

# ---------------------------------------------------------------------------
# Research tools
# ---------------------------------------------------------------------------

def _run_arxiv_search(args):
    """Search arXiv for academic papers."""
    query = args["query"].replace(" ", "+")
    url = f"http://export.arxiv.org/api/query?search_query=all:{query}&max_results=5"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode()[:4000]


def _run_deep_fetch(args):
    """Fetch a URL with a larger response limit (12k chars) for research."""
    try:
        import re
        import time
        time.sleep(1)
        url = args["url"]
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 researcher-agent/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        if args.get("raw", False):
            return raw[:12000]
        raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw[:12000] + ("..." if len(raw) > 12000 else "")
    except Exception as e:
        return f"ERROR: {e}"


# ---------------------------------------------------------------------------
# Tool registry (agent-specific only)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "spec": {"type": "function", "function": {
            "name": "arxiv_search",
            "description": "Search arXiv for academic papers on a topic.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string", "description": "Search query"},
            }, "required": ["query"]},
        }},
        "run": _run_arxiv_search,
    },
    {
        "spec": {"type": "function", "function": {
            "name": "deep_fetch",
            "description": "Fetch a URL with a 12k char limit (3x normal). Use for reading long articles, docs, or API responses during research.",
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "description": "The URL to fetch"},
                "raw": {"type": "boolean", "description": "Return raw response without HTML stripping (default: false). Use for JSON APIs."},
            }, "required": ["url"]},
        }},
        "run": _run_deep_fetch,
    },
]
