"""
Researcher agent tools — LeftClaw Services + BGIPFS + research utilities.
"""

import os
import json
import subprocess
import urllib.request
import urllib.parse

# ---------------------------------------------------------------------------
# Config from env
# ---------------------------------------------------------------------------

_CONTRACT = "0x103c5FAfd8734AE9Ec4Cc2f116eD03Ff6cc2Ca5F"
_LEFTCLAW_BASE = "https://leftclaw.services"
_CAST = os.path.expanduser("~/.foundry/bin/cast")


def _rpc():
    return os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")


def _privkey():
    return os.environ.get("ETH_PRIVATE_KEY", "")


def _bgipfs_key():
    return os.environ.get("BGIPFS_API_KEY", "")


# ---------------------------------------------------------------------------
# LeftClaw API tools
# ---------------------------------------------------------------------------

def _run_leftclaw_check_jobs(args):
    """Fetch open research jobs from LeftClaw."""
    try:
        url = f"{_LEFTCLAW_BASE}/api/job/ready"
        req = urllib.request.Request(url, headers={"User-Agent": "researcher-agent/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        if isinstance(data, dict):
            jobs = data.get("jobs", data.get("data", []))
        elif isinstance(data, list):
            jobs = data
        else:
            return json.dumps(data, indent=2)[:8000]

        research_jobs = [j for j in jobs if j.get("serviceTypeId") == 7 or str(j.get("serviceTypeId")) == "7"]

        if not research_jobs:
            return "No open research jobs right now."

        lines = []
        for j in research_jobs:
            lines.append(f"Job #{j.get('id')} — {j.get('description', '(no description)')[:200]}")
            lines.append(f"  client: {j.get('client', '?')}  status: {j.get('status', '?')}  stage: {j.get('currentStage', '?')}")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"


def _run_leftclaw_get_job(args):
    """Get full details for a specific job by reading on-chain data."""
    try:
        job_id = str(args["job_id"])
        cmd = [_CAST, "call", _CONTRACT, "getJob(uint256)", job_id, "--rpc-url", _rpc()]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return f"ERROR: {result.stderr.strip()}"

        raw = result.stdout.strip()
        h = raw[2:] if raw.startswith("0x") else raw
        words = [h[i:i+64] for i in range(0, len(h), 64)]

        def addr(w):
            return "0x" + w[24:]
        def uint(w):
            return int(w, 16)
        def text_at(words, offset_word_idx):
            offset = uint(words[offset_word_idx]) // 32
            length = uint(words[offset + 1]) if offset + 1 < len(words) else 0
            data_start = (offset + 2) * 64
            raw_hex = h[data_start:data_start + length * 2]
            try:
                return bytes.fromhex(raw_hex).decode("utf-8", errors="replace")
            except:
                return ""

        client = addr(words[2])
        service_type = uint(words[3])
        price_usd = uint(words[5])
        status_int = uint(words[14])
        status_map = {0: "OPEN", 1: "IN_PROGRESS", 2: "COMPLETE", 3: "CANCELLED"}
        worker = addr(words[12])
        created = uint(words[8])

        # Decode strings from dynamic offsets
        desc = text_at(words, 6)
        stage = ""
        for i, w in enumerate(words):
            try:
                t = bytes.fromhex(w).decode("utf-8", errors="ignore").strip("\x00")
                if t in ("accepted", "research", "create_repo", "prototype", "ready"):
                    stage = t
            except:
                pass

        return (
            f"Job #{job_id}\n"
            f"description: {desc}\n"
            f"client: {client}\n"
            f"worker: {worker}\n"
            f"serviceTypeId: {service_type}\n"
            f"status: {status_map.get(status_int, status_int)}\n"
            f"currentStage: {stage}\n"
            f"priceUsd: ${price_usd / 10000:.2f}\n"
            f"createdAt: {created}"
        )
    except Exception as e:
        return f"ERROR: {e}"


def _run_leftclaw_get_messages(args):
    """Get all messages for a job."""
    try:
        job_id = args["job_id"]
        url = f"{_LEFTCLAW_BASE}/api/job/{job_id}/messages"
        req = urllib.request.Request(url, headers={"User-Agent": "researcher-agent/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return json.dumps(data, indent=2)[:8000]
    except Exception as e:
        return f"ERROR: {e}"


def _run_leftclaw_post_message(args):
    """Post a message to a job (escalation or bot response)."""
    try:
        job_id = args["job_id"]
        msg_type = args.get("type", "bot_message")
        content = args["content"]
        metadata = args.get("metadata", {})

        url = f"{_LEFTCLAW_BASE}/api/job/{job_id}/messages"
        body = json.dumps({"type": msg_type, "from": "bot", "content": content, "metadata": metadata}).encode()
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "User-Agent": "researcher-agent/1.0",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode()[:4000]
    except Exception as e:
        return f"ERROR: {e}"


# ---------------------------------------------------------------------------
# On-chain tools (via cast)
# ---------------------------------------------------------------------------

def _cast_send(func_sig, *call_args):
    """Send a transaction to the LeftClaw contract via cast."""
    pk = _privkey()
    if not pk:
        return "ERROR: ETH_PRIVATE_KEY not set in .env"

    cmd = [
        _CAST, "send", _CONTRACT, func_sig, *[str(a) for a in call_args],
        "--rpc-url", _rpc(),
        "--private-key", pk,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        output = result.stdout.strip()
        if result.returncode != 0:
            return f"ERROR: {result.stderr.strip() or output}"
        return output or "(transaction sent)"
    except subprocess.TimeoutExpired:
        return "ERROR: transaction timed out (60s)"
    except Exception as e:
        return f"ERROR: {e}"


def _cast_call(func_sig, *call_args):
    """Read from the LeftClaw contract via cast."""
    cmd = [
        _CAST, "call", _CONTRACT, func_sig, *[str(a) for a in call_args],
        "--rpc-url", _rpc(),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout.strip()
        if result.returncode != 0:
            return f"ERROR: {result.stderr.strip() or output}"
        return output
    except Exception as e:
        return f"ERROR: {e}"


def _run_leftclaw_accept_job(args):
    """Accept a job on-chain."""
    return _cast_send("acceptJob(uint256)", args["job_id"])


def _run_leftclaw_log_work(args):
    """Log work progress on-chain."""
    return _cast_send("logWork(uint256,string,string)", args["job_id"], args["note"], args["stage"])


def _run_leftclaw_complete_job(args):
    """Complete a job on-chain with the IPFS result URL."""
    return _cast_send("completeJob(uint256,string)", args["job_id"], args["result_url"])


def _run_leftclaw_get_job_onchain(args):
    """Read a job from the contract."""
    return _cast_call("getJob(uint256)", args["job_id"])


# ---------------------------------------------------------------------------
# BGIPFS upload tool
# ---------------------------------------------------------------------------

def _run_bgipfs_upload(args):
    """Upload a file to BGIPFS and return the gateway URL."""
    key = _bgipfs_key()
    if not key:
        return "ERROR: BGIPFS_API_KEY not set in .env"

    filepath = os.path.expanduser(args["filepath"])
    if not os.path.exists(filepath):
        return f"ERROR: file not found: {filepath}"

    try:
        cmd = [
            "curl", "-s", "-X", "POST",
            "https://upload.bgipfs.com/api/v0/add",
            "-H", f"X-API-Key: {key}",
            "-F", f"file=@{filepath}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return f"ERROR: {result.stderr.strip()}"

        data = json.loads(result.stdout)
        cid_v0 = data.get("Hash", "")
        if not cid_v0:
            return f"ERROR: no Hash in response: {result.stdout}"

        # Convert CIDv0 to CIDv1 for subdomain gateway
        conv = subprocess.run(
            ["npx", "cid-tool", "base32", cid_v0],
            capture_output=True, text=True, timeout=30,
        )
        if conv.returncode == 0 and conv.stdout.strip():
            cid = conv.stdout.strip()
        else:
            cid = cid_v0

        gateway_url = f"https://{cid}.ipfs.community.bgipfs.com/"
        return f"Uploaded successfully.\nCID: {cid}\nGateway URL: {gateway_url}"
    except Exception as e:
        return f"ERROR: {e}"


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


def _run_web_search(args):
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
# Tool registry
# ---------------------------------------------------------------------------

TOOLS = [
    # --- LeftClaw API ---
    {
        "spec": {"type": "function", "function": {
            "name": "leftclaw_check_jobs",
            "description": "Check LeftClaw Services for open research jobs (Service Type 7 only). Call this first to find work.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }},
        "run": _run_leftclaw_check_jobs,
    },
    {
        "spec": {"type": "function", "function": {
            "name": "leftclaw_get_job",
            "description": "Get full details for a specific LeftClaw job by ID.",
            "parameters": {"type": "object", "properties": {
                "job_id": {"type": "integer", "description": "The job ID"},
            }, "required": ["job_id"]},
        }},
        "run": _run_leftclaw_get_job,
    },
    {
        "spec": {"type": "function", "function": {
            "name": "leftclaw_get_messages",
            "description": "Get all messages for a LeftClaw job. Check this before starting work — client messages may contain scope changes.",
            "parameters": {"type": "object", "properties": {
                "job_id": {"type": "integer", "description": "The job ID"},
            }, "required": ["job_id"]},
        }},
        "run": _run_leftclaw_get_messages,
    },
    {
        "spec": {"type": "function", "function": {
            "name": "leftclaw_post_message",
            "description": "Post a message to a LeftClaw job (escalation or bot response).",
            "parameters": {"type": "object", "properties": {
                "job_id": {"type": "integer", "description": "The job ID"},
                "content": {"type": "string", "description": "Message content"},
                "type": {"type": "string", "description": "Message type: bot_message or escalation (default: bot_message)"},
            }, "required": ["job_id", "content"]},
        }},
        "run": _run_leftclaw_post_message,
    },
    # --- On-chain actions ---
    {
        "spec": {"type": "function", "function": {
            "name": "leftclaw_accept_job",
            "description": "Accept a LeftClaw job on-chain. This claims the job — you must complete it.",
            "parameters": {"type": "object", "properties": {
                "job_id": {"type": "integer", "description": "The job ID to accept"},
            }, "required": ["job_id"]},
        }},
        "run": _run_leftclaw_accept_job,
    },
    {
        "spec": {"type": "function", "function": {
            "name": "leftclaw_log_work",
            "description": "Log work progress on-chain for a LeftClaw job. Sets the job's current stage.",
            "parameters": {"type": "object", "properties": {
                "job_id": {"type": "integer", "description": "The job ID"},
                "note": {"type": "string", "description": "Work note (max 500 chars)"},
                "stage": {"type": "string", "description": "Stage name (e.g. 'research')"},
            }, "required": ["job_id", "note", "stage"]},
        }},
        "run": _run_leftclaw_log_work,
    },
    {
        "spec": {"type": "function", "function": {
            "name": "leftclaw_complete_job",
            "description": "Complete a LeftClaw job on-chain. Pass the FULL BGIPFS gateway URL as result_url.",
            "parameters": {"type": "object", "properties": {
                "job_id": {"type": "integer", "description": "The job ID"},
                "result_url": {"type": "string", "description": "Full IPFS gateway URL: https://{CID}.ipfs.community.bgipfs.com/"},
            }, "required": ["job_id", "result_url"]},
        }},
        "run": _run_leftclaw_complete_job,
    },
    # --- BGIPFS ---
    {
        "spec": {"type": "function", "function": {
            "name": "bgipfs_upload",
            "description": "Upload a file to BGIPFS and get back the gateway URL. Use this to upload finished research reports.",
            "parameters": {"type": "object", "properties": {
                "filepath": {"type": "string", "description": "Path to the file to upload"},
            }, "required": ["filepath"]},
        }},
        "run": _run_bgipfs_upload,
    },
    # --- Research ---
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
        "run": _run_web_search,
    },
]
