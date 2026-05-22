"""
SEO Outline Generator v6
New features:
  #1  Jina Reader fallback  — r.jina.ai/URL khi crawl thường bị block (Cloudflare)
  #2  Editable outline      — st.data_editor cho phép sửa H1/H2/H3 trực tiếp trước export
  #3  Target H2 count       — competitor_avg H2 → constraint trong prompt
"""

import streamlit as st
import httpx
import json
import re
import time
import os
import io
import csv
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import median
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
import pandas as pd

# ── Page config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="SEO Outline Generator",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.main .block-container { padding-top:1.2rem; max-width:1100px; }
h1 { font-size:1.6rem !important; margin-bottom:0 !important; }

.sec { border-radius:8px; border:1px solid #e2e8f0; margin:5px 0; overflow:hidden; }
.sec-comp { border-left:4px solid #3b82f6; }
.sec-ai   { border-left:4px solid #10b981; }
.sec-hyb  { border-left:4px solid #8b5cf6; }
.sec-faq  { border-left:4px solid #f59e0b; }
.sec-head {
    display:flex; align-items:center; gap:8px; padding:9px 14px;
    background:#fff; font-weight:600; font-size:0.93rem; color:#0f172a;
}
.sec-body { background:#f8fafc; padding:4px 14px 8px; border-top:1px solid #f1f5f9; }
.h3-row   { display:flex; align-items:flex-start; gap:6px; padding:4px 0;
            font-size:0.86rem; color:#374151; }
.h3-arrow { color:#94a3b8; flex-shrink:0; margin-top:1px; }

.badge { font-size:0.6rem; font-weight:700; padding:2px 7px;
         border-radius:10px; white-space:nowrap; flex-shrink:0; }
.b-comp { background:#dbeafe; color:#1e40af; }
.b-ai   { background:#dcfce7; color:#166534; }
.b-hyb  { background:#ede9fe; color:#5b21b6; }
.b-faq  { background:#fef3c7; color:#92400e; }
.b-num  { background:#f1f5f9; color:#475569; }
.b-lang { background:#f0fdf4; color:#166534; border:1px solid #bbf7d0; }
.b-warn { background:#fef9c3; color:#713f12; }
.b-jina { background:#fdf4ff; color:#7e22ce; border:1px solid #e9d5ff; }

.h1-card {
    background:linear-gradient(135deg,#eff6ff 0%,#f0fdf4 100%);
    border:1px solid #bfdbfe; border-radius:10px;
    padding:1rem 1.25rem; margin-bottom:0.75rem;
}
.h1-label { font-size:0.65rem; font-weight:700; text-transform:uppercase;
            letter-spacing:.8px; color:#3b82f6; margin-bottom:4px; }
.h1-text  { font-size:1.1rem; font-weight:700; color:#0f172a; margin-bottom:6px; }
.meta-text { font-size:0.82rem; color:#64748b; }

.pills { display:flex; gap:8px; flex-wrap:wrap; margin:10px 0 14px; }
.pill { background:#f8fafc; border:1px solid #e2e8f0; border-radius:20px;
        padding:3px 11px; font-size:0.78rem; color:#475569; }
.pill b { color:#0f172a; }
.pill.words { background:#f0fdf4; border-color:#bbf7d0; color:#166534; }

.angles-card { background:#fefce8; border:1px solid #fde68a;
               border-radius:8px; padding:10px 14px; margin-bottom:10px; }
.angles-title { font-size:0.65rem; font-weight:700; text-transform:uppercase;
                letter-spacing:.7px; color:#92400e; margin-bottom:6px; }
.angle-tag { display:inline-block; background:#fff7ed; border:1px solid #fed7aa;
             color:#92400e; border-radius:4px; padding:2px 8px;
             font-size:0.78rem; margin:3px 3px 3px 0; }

.intent-banner { background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px;
                 padding:8px 14px; margin-bottom:10px; font-size:0.85rem; color:#1e40af; }

.wc-bar-wrap { background:#f1f5f9; border-radius:4px; height:6px; margin:4px 0 8px; overflow:hidden; }
.wc-bar { background:#10b981; height:6px; border-radius:4px; }

.dom-card { background:#fff; border:1px solid #e2e8f0; border-radius:7px;
            padding:8px 12px; margin-bottom:6px; font-size:0.85rem; }
.dom-card a { color:#2563eb; text-decoration:none; }

.hp { display:inline-block; padding:1px 6px; border-radius:3px;
      font-size:0.65rem; font-weight:700; margin-right:5px; vertical-align:middle; }
.hp-h1{background:#dbeafe;color:#1e40af} .hp-h2{background:#dcfce7;color:#166534}
.hp-h3{background:#fef9c3;color:#713f12} .hp-h4{background:#ffe4e6;color:#9f1239}

.sec-label { font-size:0.75rem; font-weight:700; color:#64748b;
             text-transform:uppercase; letter-spacing:.5px; margin:18px 0 6px; }

.stream-box { background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px;
              padding:1rem; font-family:monospace; font-size:0.8rem;
              color:#374151; white-space:pre-wrap; min-height:60px;
              max-height:200px; overflow-y:auto; }

.val-err { background:#fef2f2; border:1px solid #fca5a5; border-radius:8px;
           padding:10px 14px; font-size:0.85rem; color:#991b1b; margin:8px 0; }

/* edit mode toggle */
.edit-banner { background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px;
               padding:8px 14px; font-size:0.84rem; color:#1e40af; margin-bottom:12px; }

div[data-testid="stExpander"] { border:1px solid #e2e8f0 !important;
                                 border-radius:8px !important; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════
SOCIAL_DOMAINS = {
    "facebook.com","twitter.com","x.com","instagram.com","tiktok.com",
    "youtube.com","linkedin.com","pinterest.com","reddit.com","quora.com",
    "tumblr.com","snapchat.com","threads.net","vk.com","weibo.com",
    "t.me","telegram.org","wikipedia.org","wikimedia.org",
    "amazon.com","amazon.co.uk","ebay.com","aliexpress.com",
    "shopee.vn","lazada.vn","tiki.vn","sendo.vn",
}

BOILERPLATE_PATTERNS = re.compile(
    r"^(related (posts?|articles?|content)|you (may|might) (also )?(like|enjoy)|"
    r"share (this|article|post)|leave a (comment|reply)|subscribe|newsletter|"
    r"bài viết liên quan|có thể bạn thích|chia sẻ bài viết|"
    r"tags?:|category:|categories:|author:|about (the )?author|"
    r"table of contents?|mục lục|contents?|navigation|"
    r"advertisement|sponsored|quảng cáo|"
    r"comments?|bình luận|phản hồi|"
    r"search|tìm kiếm|menu|home|trang chủ)$",
    re.IGNORECASE,
)

CRAWL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}

# Feature #1: Jina Reader
JINA_BASE    = "https://r.jina.ai/"
JINA_HEADERS = {
    "Accept": "text/markdown",
    "X-Return-Format": "markdown",
}

MAX_WORKERS  = 6
CRAWL_MAX_MB = 3

def _bs4_parser() -> str:
    try:
        import lxml  # noqa
        return "lxml"
    except ImportError:
        return "html.parser"

BS4_PARSER = _bs4_parser()

INTENT_MODIFIERS = [
    (r"\blà gì\b","informational",2),(r"\bcách\b","how-to",2),
    (r"\bhướng dẫn\b","how-to",2),(r"\bso sánh\b","comparison",2),
    (r"\bnên mua\b","commercial",2),(r"\bgiá\b","commercial",1),
    (r"\btốt nhất\b","commercial",2),(r"\bđánh giá\b","review",2),
    (r"\breview\b","review",2),(r"\btop \d+\b","listicle",2),
    (r"\b\d+ cách\b","listicle",2),(r"\bkinh nghiệm\b","informational",1),
    (r"\blợi ích\b","informational",1),
    (r"\bwhat is\b","informational",2),(r"\bhow to\b","how-to",2),
    (r"\bguide\b","how-to",1),(r"\btutorial\b","how-to",2),
    (r"\bbest\b","commercial",2),(r"\btop \d+\b","listicle",2),
    (r"\b\d+ ways\b","listicle",2),(r"\b\d+ tips\b","listicle",2),
    (r"\bvs\.?\b","comparison",2),(r"\bcompare\b","comparison",2),
    (r"\bprice\b","commercial",1),(r"\bbuy\b","transactional",2),
    (r"\bcheap\b","transactional",1),(r"\bdiscount\b","transactional",1),
    (r"\bwhy\b","informational",1),(r"\bbenefits\b","informational",1),
    (r"\bexamples\b","informational",1),
]

INTENT_LABELS = {
    "informational": ("📚 Informational","#dbeafe","#1e40af"),
    "how-to":        ("🔧 How-to","#dcfce7","#166534"),
    "listicle":      ("📋 Listicle","#fef9c3","#713f12"),
    "commercial":    ("🛒 Commercial","#ede9fe","#5b21b6"),
    "transactional": ("💳 Transactional","#fee2e2","#991b1b"),
    "review":        ("⭐ Review","#fff7ed","#92400e"),
    "comparison":    ("⚖️ Comparison","#f0fdf4","#166534"),
    "mixed":         ("🔀 Mixed","#f1f5f9","#475569"),
}

# ═══════════════════════════════════════════════════════════════════
# LANGUAGE + INTENT
# ═══════════════════════════════════════════════════════════════════
VI_MARKERS = re.compile(
    r"[àáảãạăắặẵẳặâấầẫẩậèéẻẽẹêếềễểệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ"
    r"ÀÁẢÃẠĂẮẶẴẲẶÂẤẦẪẨẬÈÉẺẼẸÊẾỀỄỂỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ]"
)
VI_WORDS = re.compile(
    r"\b(là|gì|cách|hướng|dẫn|tốt|nhất|giá|nên|mua|và|của|cho|với|"
    r"bạn|tôi|khi|hoặc|những|các|một|được|có|không|theo|từ|về|"
    r"trong|ngoài|trên|dưới|sau|trước|đến|đi|làm|tìm|xem|học|biết)\b",
    re.IGNORECASE,
)

def detect_language(kw: str) -> str:
    k = kw.lower()
    score = 3 if VI_MARKERS.search(k) else 0
    score += len(VI_WORDS.findall(k))
    return "vi" if score >= 2 else "en"

def detect_intent_from_modifier(kw: str) -> dict:
    scores: dict[str,int] = {}
    signals: list[str] = []
    k = kw.lower()
    for pat, intent, boost in INTENT_MODIFIERS:
        if re.search(pat, k):
            scores[intent] = scores.get(intent,0) + boost
            signals.append(re.sub(r"\\b|\(|\)|\?|\.", "", pat).strip())
    if not scores:
        return {"intent":"informational","confidence":"low","signals":[]}
    top  = max(scores, key=scores.get)
    conf = "high" if scores[top]>=3 else "medium" if scores[top]>=2 else "low"
    return {"intent":top,"confidence":conf,"signals":signals}

# ═══════════════════════════════════════════════════════════════════
# SERP
# ═══════════════════════════════════════════════════════════════════
def is_blocked(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().replace("www.","")
        return any(host==d or host.endswith("."+d) for d in SOCIAL_DOMAINS)
    except Exception:
        return False

def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.","")
    except Exception:
        return url

def _raise_dfs_error(resp: httpx.Response) -> None:
    if resp.status_code == 401:
        raise ValueError("❌ DataForSEO: Invalid credentials (401).")
    if resp.status_code == 402:
        raise ValueError("❌ DataForSEO: Insufficient balance (402). Top up at app.dataforseo.com.")
    if resp.status_code == 429:
        raise ValueError("❌ DataForSEO: Rate limit (429). Wait and retry.")
    if resp.status_code >= 500:
        raise ValueError(f"❌ DataForSEO: Server error ({resp.status_code}).")
    resp.raise_for_status()
    try:
        task = resp.json()["tasks"][0]
        if task.get("status_code") not in (20000,20100):
            raise ValueError(f"❌ DataForSEO task error: {task.get('status_message','unknown')}")
    except (KeyError,IndexError,json.JSONDecodeError):
        pass

def fetch_serp(keyword: str, login: str, password: str,
               location_code: int, language_code: str) -> list[dict]:
    resp = httpx.post(
        "https://api.dataforseo.com/v3/serp/google/organic/live/advanced",
        auth=(login,password),
        json=[{"keyword":keyword,"location_code":location_code,
               "language_code":language_code,"depth":30}],
        timeout=30,
    )
    _raise_dfs_error(resp)
    results = []
    try:
        for item in resp.json()["tasks"][0]["result"][0]["items"]:
            if item.get("type") != "organic":
                continue
            url = item.get("url","")
            if not url or is_blocked(url):
                continue
            results.append({
                "rank":        item.get("rank_absolute",99),
                "url":         url,
                "title":       item.get("title",""),
                "description": item.get("description",""),
            })
            if len(results) >= 10:
                break
    except (KeyError,IndexError,TypeError):
        pass
    return results

def intent_from_serp_titles(serp_results: list[dict]) -> dict:
    scores: dict[str,int] = {}
    for r in serp_results:
        title = (r.get("title") or "").lower()
        for pat, intent, _ in INTENT_MODIFIERS:
            if re.search(pat, title):
                scores[intent] = scores.get(intent,0) + 1
    if not scores:
        return {}
    return {"intent": max(scores,key=scores.get), "counts": scores}

# ═══════════════════════════════════════════════════════════════════
# CRAWL
# Strategy (in order):
#   1. DataForSEO On-Page instant_pages  — JS rendering, reliable, $0.00025/URL
#   2. DataForSEO content_parsing/live   — fallback if htags empty, $0.000125/URL
#   3. Direct HTTP + BeautifulSoup       — free, fast, blocked by Cloudflare
#   4. Jina Reader (r.jina.ai)           — last resort, free, handles Cloudflare
# ═══════════════════════════════════════════════════════════════════

# ── DFS On-Page helpers ───────────────────────────────────────────
def _dfs_instant_pages(url: str, login: str, password: str,
                       enable_js: bool = True) -> dict:
    """
    DataForSEO On-Page instant_pages — sync, returns htags + word_count.
    Supports JS rendering via enable_javascript=True (handles lazy-load headings).
    Cost: $0.00025/call.
    """
    resp = httpx.post(
        "https://api.dataforseo.com/v3/on_page/instant_pages",
        auth=(login, password),
        json=[{
            "url": url,
            "enable_javascript": enable_js,
            "load_resources": False,          # skip images/css — faster + cheaper
            "custom_js": "",
        }],
        timeout=45,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        item = data["tasks"][0]["result"][0]["items"][0]
        meta = item.get("meta", {}) or {}
        htags = meta.get("htags", {}) or {}
        # htags format: {"h1": ["text1"], "h2": ["text1","text2"], ...}
        headings: list[dict] = []
        for level in ("h1", "h2", "h3", "h4"):
            for text in (htags.get(level) or []):
                text = (text or "").strip()
                if not text or not (3 <= len(text) <= 250):
                    continue
                if BOILERPLATE_PATTERNS.match(text):
                    continue
                headings.append({"tag": level, "text": text})
        content_meta = meta.get("content", {}) or {}
        wc = content_meta.get("plain_text_word_count", 0) or 0
        body_text = (content_meta.get("plain_text") or "").strip()
        return {"headings": headings, "word_count": wc, "body_text": body_text,
                "status_code": item.get("status_code", 0)}
    except (KeyError, IndexError, TypeError):
        return {"headings": [], "word_count": 0, "status_code": 0}

def _dfs_content_parsing(url: str, login: str, password: str) -> dict:
    """
    DataForSEO content_parsing/live — structured content fallback.
    Useful when instant_pages returns empty htags on complex pages.
    Cost: $0.000125/call.
    """
    resp = httpx.post(
        "https://api.dataforseo.com/v3/on_page/content_parsing/live",
        auth=(login, password),
        json=[{"url": url, "markdown_view": False}],
        timeout=40,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        item      = data["tasks"][0]["result"][0]["items"][0]
        pc        = item.get("page_content", {}) or {}
        # Extract headings from content blocks
        headings: list[dict] = []
        for section in (pc.get("main_columns") or []):
            for block in (section.get("content") or []):
                btype = block.get("type", "")
                if btype in ("header", "title"):
                    text = (block.get("text") or block.get("content") or "").strip()
                    level_raw = block.get("level", 2)
                    try:
                        level = int(level_raw)
                    except (TypeError, ValueError):
                        level = 2
                    level = max(1, min(level, 4))
                    if text and 3 <= len(text) <= 250 and not BOILERPLATE_PATTERNS.match(text):
                        headings.append({"tag": f"h{level}", "text": text})
        paragraphs = []
        for section in (pc.get("main_columns") or []):
            for block in (section.get("content") or []):
                if block.get("type") == "paragraph":
                    text = (block.get("text") or block.get("content") or "").strip()
                    if len(text) > 40:
                        paragraphs.append(text)
        body_text = " ".join(paragraphs)
        wc = pc.get("text_word_count", 0) or 0
        return {"headings": headings, "word_count": wc, "body_text": body_text}
    except (KeyError, IndexError, TypeError):
        return {"headings": [], "word_count": 0, "body_text": ""}

# ── Direct HTTP helpers (free, no API) ───────────────────────────
def _fetch_html(url: str, timeout: int) -> str:
    with httpx.Client(headers=CRAWL_HEADERS, timeout=timeout,
                      follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        raw = resp.content[:CRAWL_MAX_MB * 1024 * 1024]
        return raw.decode(resp.encoding or "utf-8", errors="replace")

def extract_headings_from_html(html: str) -> tuple[list[dict], int]:
    soup = BeautifulSoup(html, BS4_PARSER)
    for tag in soup(["script","style","nav","footer","header",
                     "aside","noscript","iframe","form"]):
        tag.decompose()
    headings = []
    for tag in soup.find_all(["h1","h2","h3","h4"]):
        text = tag.get_text(separator=" ", strip=True)
        if not text or not (3 <= len(text) <= 250):
            continue
        if BOILERPLATE_PATTERNS.match(text):
            continue
        headings.append({"tag": tag.name.lower(), "text": text})
    content_el = (
        soup.find("article") or soup.find("main") or
        soup.find(id=re.compile(r"content|main|post|article", re.I)) or
        soup.find(class_=re.compile(r"content|main|post|article|entry", re.I)) or
        soup.body
    )
    wc = len((content_el or soup).get_text(separator=" ", strip=True).split())
    return headings, wc

# ── Jina Reader (last resort) ─────────────────────────────────────
JINA_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)

def _fetch_via_jina(url: str, timeout: int = 22) -> str:
    jina_url = JINA_BASE + url
    with httpx.Client(headers=JINA_HEADERS, timeout=timeout,
                      follow_redirects=True) as client:
        resp = client.get(jina_url)
        resp.raise_for_status()
        return resp.text

def extract_headings_from_markdown(md: str) -> tuple[list[dict], int]:
    headings = []
    for m in JINA_HEADING_RE.finditer(md):
        level = len(m.group(1))
        text  = m.group(2).strip()
        text  = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        text  = re.sub(r"\*\*?([^*]+)\*\*?", r"\1", text)
        text  = text.strip()
        if not text or not (3 <= len(text) <= 250):
            continue
        if BOILERPLATE_PATTERNS.match(text):
            continue
        headings.append({"tag": f"h{level}", "text": text})
    body_lines = [l for l in md.splitlines() if not l.startswith("#")]
    wc = len(" ".join(body_lines).split())
    return headings, wc

def _extract_body_from_html(html: str, max_chars: int = 0) -> str:
    """Extract paragraph text from HTML — used for layer 3 body_text."""
    soup = BeautifulSoup(html, BS4_PARSER)
    for tag in soup(["script","style","nav","footer","header","aside","noscript","iframe","form"]):
        tag.decompose()
    content_el = (
        soup.find("article") or soup.find("main") or
        soup.find(id=re.compile(r"content|main|post|article", re.I)) or
        soup.find(class_=re.compile(r"content|main|post|article|entry", re.I)) or
        soup.body
    )
    paras = [p.get_text(separator=" ", strip=True)
             for p in (content_el or soup).find_all("p")
             if len(p.get_text(strip=True)) > 40]
    text = " ".join(paras)
    return text[:max_chars] if max_chars else text

def _extract_body_from_jina(md: str, max_chars: int = 0) -> str:
    """Extract non-heading lines from Jina markdown — used for layer 4 body_text."""
    lines = [l.strip() for l in md.splitlines()
             if l.strip() and not l.strip().startswith("#") and len(l.strip()) > 40]
    text = " ".join(lines)
    return text[:max_chars] if max_chars else text

# ── Main crawl_one — 4-layer strategy ────────────────────────────
def crawl_one(url: str, t1: int, t2: int, use_jina_fallback: bool,
              dfs_login: str = "", dfs_password: str = "") -> dict:
    """
    4-layer crawl with fallback chain.
    Each layer records its method for display in UI.
    """
    base  = {"url": url, "headings": [], "word_count": 0,
             "body_text": "", "error": None, "method": "direct"}
    errors: list[str] = []

    # ── Layer 1: DataForSEO instant_pages (JS rendering) ─────────
    if dfs_login and dfs_password:
        try:
            result = _dfs_instant_pages(url, dfs_login, dfs_password, enable_js=True)
            if result["headings"]:
                return {**base, **result, "status": "dfs", "method": "dfs"}
            errors.append(f"dfs_instant: empty htags (status={result['status_code']})")
        except Exception as e:
            errors.append(f"dfs_instant: {str(e)[:60]}")

        # ── Layer 2: DataForSEO content_parsing (fallback) ───────
        try:
            result2 = _dfs_content_parsing(url, dfs_login, dfs_password)
            if result2["headings"]:
                return {**base, **result2, "status": "dfs", "method": "dfs_content"}
            errors.append("dfs_content: no headings parsed")
        except Exception as e:
            errors.append(f"dfs_content: {str(e)[:60]}")

    # ── Layer 3: Direct HTTP ──────────────────────────────────────
    try:
        html = _fetch_html(url, t1)
        headings, wc = extract_headings_from_html(html)
        if headings:
            return {**base, "headings": headings, "word_count": wc,
                    "body_text": _extract_body_from_html(html),
                    "status": "ok", "method": "direct"}
    except Exception as e:
        errors.append(f"direct1: {str(e)[:60]}")

    time.sleep(0.3)
    try:
        html = _fetch_html(url, t2)
        headings, wc = extract_headings_from_html(html)
        if headings:
            return {**base, "headings": headings, "word_count": wc,
                    "body_text": _extract_body_from_html(html),
                    "status": "retry_ok", "method": "direct"}
        errors.append("direct2: empty headings")
    except Exception as e:
        errors.append(f"direct2: {str(e)[:60]}")

    # ── Layer 4: Jina Reader ──────────────────────────────────────
    if use_jina_fallback:
        try:
            md = _fetch_via_jina(url)
            headings, wc = extract_headings_from_markdown(md)
            if not headings:
                headings, wc = extract_headings_from_html(md)
            if headings:
                return {**base, "headings": headings, "word_count": wc,
                        "body_text": _extract_body_from_jina(md),
                        "status": "jina", "method": "jina"}
            errors.append("jina: no headings")
        except Exception as e:
            errors.append(f"jina: {str(e)[:60]}")

    return {**base, "status": "fail", "error": " | ".join(errors[-3:])}

def crawl_all(serp_results, t1, t2, use_jina,
              dfs_login="", dfs_password="", on_done=None) -> list[dict]:
    out = [None]*len(serp_results)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fmap = {
            ex.submit(crawl_one, r["url"], t1, t2, use_jina,
                      dfs_login, dfs_password): i
            for i, r in enumerate(serp_results)
        }
        for f in as_completed(fmap):
            i = fmap[f]
            out[i] = {**serp_results[i], **f.result()}
            if on_done:
                on_done(sum(1 for x in out if x), len(serp_results), out[i])
    return out

def competitor_word_count_stats(crawl_results: list[dict]) -> dict:
    counts = [r["word_count"] for r in crawl_results if r.get("word_count",0)>200]
    if not counts:
        return {}
    med = int(median(counts))
    return {"median":med,"min":min(counts),"max":max(counts),
            "target":int(med*1.15),"count":len(counts)}

# Feature #3: H2 count stats
def competitor_h2_stats(crawl_results: list[dict]) -> dict:
    """Compute average + median H2 count across successfully crawled pages."""
    h2_counts = [
        sum(1 for h in (r.get("headings") or []) if h["tag"]=="h2")
        for r in crawl_results if r.get("headings")
    ]
    if not h2_counts:
        return {}
    avg = round(sum(h2_counts)/len(h2_counts))
    med = int(median(h2_counts))
    return {
        "avg": avg,
        "median": med,
        "min": min(h2_counts),
        "max": max(h2_counts),
        "target": max(avg, med, 5),  # use higher of avg/median, minimum 5
        "counts": h2_counts,
    }

# ═══════════════════════════════════════════════════════════════════
# HEADING DEDUP + FREQUENCY
# ═══════════════════════════════════════════════════════════════════
def _similar(a: str, b: str, threshold: float=0.72) -> bool:
    a,b = a.lower().strip(), b.lower().strip()
    return a==b or SequenceMatcher(None,a,b).ratio()>=threshold

def dedup_and_weight_headings(crawl_results: list[dict]) -> list[dict]:
    all_h: list[tuple] = []
    for r in crawl_results:
        for h in (r.get("headings") or []):
            all_h.append((h["tag"], h["text"], domain_of(r["url"])))
    clusters: list[dict] = []
    for tag,text,domain in all_h:
        matched = False
        for c in clusters:
            if c["tag"]==tag and _similar(c["canonical"],text):
                if domain not in c["domains"]:
                    c["domains"].append(domain)
                matched = True; break
        if not matched:
            clusters.append({"tag":tag,"canonical":text,"domains":[domain]})
    tag_order = {"h1":0,"h2":1,"h3":2,"h4":3}
    return [
        {"tag":c["tag"],"text":c["canonical"],"freq":len(c["domains"]),"domains":c["domains"]}
        for c in sorted(clusters,key=lambda x:(tag_order.get(x["tag"],9),-len(x["domains"])))
    ]

def format_headings_for_prompt(deduped: list[dict], total_crawled: int) -> str:
    return "\n".join(
        f"  [{h['tag'].upper()}] [{h['freq']}/{total_crawled}] {h['text']}"
        for h in deduped
    )

# ═══════════════════════════════════════════════════════════════════
# JSON VALIDATION
# ═══════════════════════════════════════════════════════════════════
REQUIRED_FIELDS    = {"h1":str,"meta_description":str,"article_type":str,"outline":list}
VALID_SOURCES      = {"competitor","ai","hybrid"}
VALID_ARTICLE_TYPES= {"informational","listicle","how-to","comparison","review","commercial","transactional"}

def validate_outline(data: dict) -> list[str]:
    errors = []
    if not isinstance(data,dict):
        return ["Response is not a JSON object"]
    for field,ftype in REQUIRED_FIELDS.items():
        if field not in data:
            errors.append(f"Missing required field: '{field}'")
        elif not isinstance(data[field],ftype):
            errors.append(f"Field '{field}' wrong type")
    if "article_type" in data and data["article_type"] not in VALID_ARTICLE_TYPES:
        errors.append(f"Unknown article_type '{data['article_type']}'")
    if "outline" in data and isinstance(data["outline"],list):
        if len(data["outline"])==0:
            errors.append("'outline' is empty")
        for i,item in enumerate(data["outline"]):
            if not isinstance(item,dict):
                errors.append(f"outline[{i}] not an object"); continue
            if "h2" not in item or not isinstance(item.get("h2"),str) or not item["h2"].strip():
                errors.append(f"outline[{i}] missing/empty 'h2'")
            if item.get("source") not in VALID_SOURCES:
                item["source"]="ai"
            if not isinstance(item.get("h3s"),list):
                item["h3s"]=[]
            if not isinstance(item.get("bullets"),list):
                item["bullets"]=[]
    return errors

def fix_outline_data(data: dict) -> dict:
    # Always clear FAQ
    data["faq"] = []
    if not isinstance(data.get("unique_angles"),list): data["unique_angles"]=[]
    if data.get("article_type") not in VALID_ARTICLE_TYPES:
        data["article_type"]="informational"
    for item in data.get("outline",[]):
        if isinstance(item,dict):
            if item.get("source") not in VALID_SOURCES: item["source"]="ai"
            if not isinstance(item.get("h3s"),list):    item["h3s"]=[]
            if not isinstance(item.get("bullets"),list): item["bullets"]=[]
            # If both h3s and bullets present, keep h3s and clear bullets
            # (competitor had real H3s, bullets redundant)
            if item.get("h3s") and item.get("bullets"):
                item["bullets"]=[]
    return data

# ═══════════════════════════════════════════════════════════════════
# CLAUDE STREAMING
# ═══════════════════════════════════════════════════════════════════
def call_claude_stream(system: str, user: str, key: str,
                       on_chunk=None, max_tokens: int=4096) -> str:
    full = ""; buf = b""; last_call = 0.0
    with httpx.Client(timeout=httpx.Timeout(connect=10,read=120,write=30,pool=5)) as client:
        with client.stream("POST","https://api.anthropic.com/v1/messages",
            headers={"x-api-key":key,"anthropic-version":"2023-06-01",
                     "content-type":"application/json"},
            json={"model":"claude-sonnet-4-6","max_tokens":max_tokens,
                  "stream":True,"system":system,
                  "messages":[{"role":"user","content":user}]},
        ) as resp:
            if resp.status_code==401: raise ValueError("❌ Anthropic: Invalid API key (401).")
            if resp.status_code==429: raise ValueError("❌ Anthropic: Rate limit (429). Check plan.")
            if resp.status_code>=500: raise ValueError(f"❌ Anthropic: Server error ({resp.status_code}).")
            resp.raise_for_status()
            for raw_bytes in resp.iter_bytes(chunk_size=512):
                buf += raw_bytes
                while b"\n" in buf:
                    line_bytes,buf = buf.split(b"\n",1)
                    line = line_bytes.decode("utf-8",errors="replace").strip()
                    if not line.startswith("data: "): continue
                    payload = line[6:]
                    if payload=="[DONE]": break
                    try:
                        evt = json.loads(payload)
                        if evt.get("type")=="content_block_delta":
                            full += evt["delta"].get("text","")
                            now  = time.monotonic()
                            if on_chunk and (now-last_call)>=0.25:
                                on_chunk(full); last_call=now
                    except (json.JSONDecodeError,KeyError):
                        continue
    if on_chunk and full: on_chunk(full)
    return full

def call_claude_simple(system: str, user: str, key: str,
                       model: str = "claude-haiku-4-5-20251001",
                       max_tokens: int = 800) -> str:
    """Non-streaming Claude call for short tasks (background generation, etc.)."""
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": model, "max_tokens": max_tokens,
              "system": system,
              "messages": [{"role": "user", "content": user}]},
        timeout=30,
    )
    if resp.status_code == 401: raise ValueError("❌ Anthropic: Invalid API key (401).")
    if resp.status_code == 429: raise ValueError("❌ Anthropic: Rate limit (429).")
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


def generate_background_text(keyword: str, lang: str, crawl_results: list,
                              anthropic_key: str, serp_results: list = None) -> str:
    """Distill ONLY real facts from competitor body text + SERP snippets using Claude Haiku.
    Never invents content — if no data at all, returns a note instead."""
    if not anthropic_key:
        return ""

    # Collect full body_text from top 3 successfully crawled pages
    snippets: list[str] = []
    for r in (crawl_results or []):
        bt = (r.get("body_text") or "").strip()
        if len(bt) > 100:
            snippets.append(f"[{domain_of(r.get('url', ''))}]\n{bt}")
        if len(snippets) >= 3:
            break

    # SERP descriptions — Google-curated summaries, already fetched for free
    serp_descs: list[str] = []
    for r in (serp_results or []):
        desc = (r.get("description") or "").strip()
        if len(desc) > 30:
            serp_descs.append(f"- [{domain_of(r.get('url',''))}] {desc}")

    if not snippets and not serp_descs:
        return ("[Không có dữ liệu body text — các trang competitor không crawl được nội dung]"
                if lang == "vi" else
                "[No background data available — competitor pages returned no body text]")

    lang_name    = "Vietnamese" if lang == "vi" else "English"
    body_section = ("\n\n---\n\n".join(snippets)
                    if snippets else "(No full body text crawled)")
    serp_section = ("\n".join(serp_descs)
                    if serp_descs else "(No SERP descriptions available)")

    prompt = f"""Below is real data crawled from top competitor pages for the topic: "{keyword}"

== GOOGLE SEARCH SNIPPETS (Google-curated summaries) ==
{serp_section}

== FULL BODY TEXT FROM TOP COMPETITOR PAGES ==
{body_section}

---

Task: Extract and condense ONLY the factual information present in the source data above.

Rules (strictly enforced):
- Write in {lang_name}
- 400–900 words
- Include ONLY: facts, statistics, definitions, causes/effects, recommendations — explicitly stated in the source
- Do NOT add any information not present in the sources above
- Do NOT write creative intro/outro — keep it dense with concrete facts
- Plain text only, no markdown headers or bullet points
- If source data is thin, write only what is there and append: "(Limited data from crawl)"
"""
    system = ("Bạn là research assistant. Chỉ trích xuất và cô đọng thông tin thực tế từ "
              "văn bản nguồn được cung cấp. Tuyệt đối không thêm thông tin ngoài nguồn."
              if lang == "vi" else
              "You are a research assistant. Extract and condense factual information "
              "from provided source text only. Never invent or add anything not in the source.")
    try:
        raw = call_claude_simple(system, prompt, anthropic_key, max_tokens=1200)
        # Strip markdown formatting Haiku adds despite instructions
        clean = re.sub(r'^#{1,6}\s+.*$', '', raw, flags=re.MULTILINE)  # # headers
        clean = re.sub(r'^\*\*[^*]+\*\*\s*$', '', clean, flags=re.MULTILINE)  # **bold-only lines**
        clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean)  # inline **bold** → plain
        clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
        return clean
    except Exception:
        return ""

def parse_json_response(raw: str) -> dict:
    clean = re.sub(r"^```[a-z]*\n?","",raw.strip())
    clean = re.sub(r"\n?```$","",clean)
    return json.loads(clean)

# ═══════════════════════════════════════════════════════════════════
# PROMPTS  — Feature #3: H2 count constraint
# ═══════════════════════════════════════════════════════════════════
CURRENT_YEAR = 2026  # Update annually

SYSTEM_PROMPT = """Bạn là chuyên gia SEO content strategist. Tạo outline bài viết SEO tốt nhất.

QUY TẮC QUAN TRỌNG:

1. H2 TEXT:
   - Heading [5+/N competitors]: GIỮ NGUYÊN text từ đối thủ (không rewrite, không paraphrase).
     Lý do: nếu nhiều trang top rank cùng dùng 1 heading → đó là heading tốt nhất cho SEO.
   - Heading [3-4/N]: có thể paraphrase nhẹ
   - Heading [1-2/N] hoặc AI-generated: viết mới hoàn toàn
   - source="competitor" khi lấy từ đối thủ, source="ai" khi tự tạo, source="hybrid" khi kết hợp
   - LUÔN xóa số thứ tự/prefix của competitor trước khi dùng heading:
     Ví dụ: "2. Deep Dive: Tub Types" → "Deep Dive: Tub Types"
             "4 factors that affect..." → "Factors That Affect..."
             "Step 1: Clean the surface" → giữ nguyên nếu đó là H3 trong how-to, xóa nếu là H2

2. H3:
   - CHỈ đưa vào h3s[] nếu đối thủ thực sự có H3 dưới H2 đó trong data crawl
   - Nếu đối thủ KHÔNG có H3 → để h3s=[] và dùng "bullets" để gợi ý nội dung viết gì
   - bullets là gợi ý ngắn (3-6 từ) về điểm cần cover trong section đó
   - Không được bịa H3 khi đối thủ không có

3. TRÙNG NGHĨA — kiểm tra trước khi finalize:
   - H2 vs H2: nếu 2 H2 cùng chủ đề/ý nghĩa dù khác chữ → merge thành 1, bỏ cái trùng
   - H3 vs H2 cha: H3 KHÔNG được lặp lại ý của H2 ngay trên nó
     Ví dụ sai: H2 "Water Resistance" → H3 "Waterproof Properties" (cùng nghĩa → bỏ H3)
     Ví dụ đúng: H2 "Water Resistance" → H3 "Tile vs Vinyl Waterproofing" (khác góc nhìn → giữ)
   - H3 vs H3 trong cùng H2: mỗi H3 phải cover 1 khía cạnh khác nhau, không trùng nhau
   - Nguyên tắc: mỗi heading = 1 góc nhìn/khía cạnh độc lập, không overlap với heading khác

4. FAQ: KHÔNG tạo FAQ. Để faq=[] rỗng.

5. NĂM THÁNG: Nếu keyword có năm cũ hoặc không có năm → dùng năm hiện tại trong H1/headings.
   Không được dùng năm < {CURRENT_YEAR}.

6. SỐ H2: generate đúng target_h2_count (±1).

7. NGÔN NGỮ: output = ngôn ngữ của keyword.

JSON schema (tất cả field bắt buộc):
{{
  "h1": "string",
  "meta_description": "string 150-160 chars",
  "article_type": "informational|listicle|how-to|comparison|review|commercial|transactional",
  "search_intent_confirmed": "string",
  "unique_angles": ["string"],
  "outline": [
    {{
      "h2": "string — giữ nguyên nếu [5+/N], paraphrase nếu [3-4/N], viết mới nếu AI",
      "source": "competitor|ai|hybrid",
      "h3s": ["string — CHỈ có nếu đối thủ crawl được có H3 thực sự"],
      "bullets": ["gợi ý nội dung ngắn nếu không có H3"],
      "note": "string — ghi [X/N competitors] để biết tần suất"
    }}
  ],
  "faq": []
}}"""

def build_prompt(keyword, lang, mod_intent, serp_intent, serp_results,
                 deduped, crawl_results, wc_stats, h2_stats) -> str:

    mod_str  = (f"{mod_intent['intent']} ({mod_intent['confidence']}, "
                f"signals: {', '.join(mod_intent['signals'][:4]) or 'none'})")
    serp_str = (f"{serp_intent.get('intent','?')} (from SERP titles)"
                if serp_intent else "unclear")

    titles_block = "\n".join(
        f"  #{r['rank']} {r['title']}" for r in serp_results if r.get("title")
    )

    total_crawled = sum(1 for r in crawl_results if r.get("headings"))
    headings_block = format_headings_for_prompt(deduped, total_crawled)

    # Build H3 context: which H2s actually have H3s from competitors
    h2_h3_map: dict[str, list[str]] = {}
    for r in crawl_results:
        hs = r.get("headings") or []
        cur_h2 = None
        for h in hs:
            if h["tag"] == "h2":
                cur_h2 = h["text"]
                if cur_h2 not in h2_h3_map:
                    h2_h3_map[cur_h2] = []
            elif h["tag"] == "h3" and cur_h2:
                if h["text"] not in h2_h3_map[cur_h2]:
                    h2_h3_map[cur_h2].append(h["text"])

    h3_context = ""
    if h2_h3_map:
        h3_lines = []
        for h2_text, h3_list in list(h2_h3_map.items())[:20]:  # cap at 20 H2s
            if h3_list:
                h3_lines.append(f"  H2: {h2_text}")
                for h3 in h3_list[:6]:  # cap H3s per H2
                    h3_lines.append(f"    → H3: {h3}")
        if h3_lines:
            h3_context = "\nH3 THỰC TẾ TỪ COMPETITORS (chỉ những H2 có H3):\n" + "\n".join(h3_lines) + "\n"

    wc_block = ""
    if wc_stats:
        wc_block = (f"Word count: competitor median={wc_stats['median']:,}, "
                    f"target=~{wc_stats['target']:,} words\n")

    h2_block = ""
    if h2_stats:
        h2_block = (
            f"Competitor H2 count: avg={h2_stats['avg']}, "
            f"median={h2_stats['median']}, range={h2_stats['min']}–{h2_stats['max']}\n"
            f"TARGET H2 COUNT = {h2_stats['target']} (±1)\n"
        )

    return f"""Keyword: "{keyword}"
Language: {lang}
Current year: {CURRENT_YEAR} — dùng năm này trong H1 nếu keyword có năm hoặc cần cập nhật

SEARCH INTENT (2-layer):
- Modifier: {mod_str}
- SERP titles: {serp_str}

SERP TITLES:
{titles_block}

{wc_block}{h2_block}
COMPETITOR HEADINGS (deduplicated, {total_crawled} pages crawled):
{headings_block}
{h3_context}
Instructions:
1. intent → search_intent_confirmed
2. [5+/{total_crawled}] H2 headings: COPY NGUYÊN TEXT, source="competitor"
3. [3-4/{total_crawled}] H2: paraphrase nhẹ, source="competitor"
4. [1-2/{total_crawled}] H2: rewrite hoặc AI gap, source="hybrid"/"ai"
5. H3: CHỈ điền nếu competitor thực sự có H3 đó (xem H3 THỰC TẾ bên trên)
6. Nếu không có H3 từ competitor → dùng bullets (3-6 từ/bullet, 3-5 bullets)
7. faq = [] (bỏ trống hoàn toàn)
8. Generate EXACTLY {h2_stats.get('target', 7) if h2_stats else 7} H2 sections (±1)
9. All text in {'Vietnamese' if lang=='vi' else 'English'}
10. note = ghi "[X/{total_crawled} competitors]" cho mỗi H2
11. TRÙNG NGHĨA: trước khi output, rà soát toàn bộ outline — mỗi heading (H2 hoặc H3) phải cover 1 góc nhìn độc lập, không trùng nghĩa với bất kỳ heading nào khác dù khác level

Return pure JSON only."""

# ═══════════════════════════════════════════════════════════════════
# RENDER (read-only view)
# ═══════════════════════════════════════════════════════════════════
def render_outline_view(data: dict, wc_stats: dict):
    h1     = data.get("h1","")
    meta   = data.get("meta_description","")
    atype  = data.get("article_type","")
    intent = data.get("search_intent_confirmed","")
    angles = data.get("unique_angles",[])
    outline= data.get("outline",[])
    faq    = data.get("faq",[])

    st.markdown(f"""
    <div class="h1-card">
      <div class="h1-label">H1 — Article Title</div>
      <div class="h1-text">{h1}</div>
      <div class="meta-text"><b>Meta:</b> {meta}</div>
    </div>""", unsafe_allow_html=True)

    comp_n = sum(1 for b in outline if b.get("source")=="competitor")
    ai_n   = sum(1 for b in outline if b.get("source") in ("ai","hybrid"))
    il,ibg,icolor = INTENT_LABELS.get(atype,INTENT_LABELS["mixed"])
    wc_pill = (f'<span class="pill words">📝 ~<b>{wc_stats["target"]:,}</b> words</span>'
               if wc_stats else "")
    st.markdown(f"""
    <div class="pills">
      <span class="pill" style="background:{ibg};color:{icolor};border-color:{ibg}">{il}</span>
      {wc_pill}
      <span class="pill">📊 <b>{len(outline)}</b> H2</span>
      <span class="pill">🔵 <b>{comp_n}</b> competitor</span>
      <span class="pill">🟢 <b>{ai_n}</b> AI</span>
    </div>""", unsafe_allow_html=True)

    if intent:
        st.markdown(f'<div class="intent-banner">🎯 <b>Search intent:</b> {intent}</div>',
                    unsafe_allow_html=True)
    if angles:
        tags = "".join(f'<span class="angle-tag">✦ {a}</span>' for a in angles)
        st.markdown(f"""<div class="angles-card">
          <div class="angles-title">💡 Unique angles</div>{tags}</div>""",
          unsafe_allow_html=True)

    if wc_stats:
        pct = min(int(wc_stats["target"]/(wc_stats["max"] or 1)*100),100)
        st.markdown(f"""
        <div style="font-size:0.75rem;color:#64748b;margin-bottom:2px">
          WC target vs max ({wc_stats['min']:,}–{wc_stats['max']:,})</div>
        <div class="wc-bar-wrap"><div class="wc-bar" style="width:{pct}%"></div></div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="sec-label">📑 Outline</div>', unsafe_allow_html=True)
    for idx,block in enumerate(outline):
        src = block.get("source","ai")
        if src=="competitor":  sc,bc,bt = "sec-comp","b-comp","Competitor"
        elif src=="hybrid":    sc,bc,bt = "sec-hyb","b-hyb","Hybrid"
        else:                  sc,bc,bt = "sec-ai","b-ai","AI ✦"
        note = block.get("note","")
        nh   = (f'<span style="font-size:0.75rem;color:#94a3b8;font-weight:400"> — {note}</span>'
                if note else "")

        h3s     = block.get("h3s",[])
        bullets = block.get("bullets",[])

        # H3 rows — with frequency note if present in note field
        h3_html = ""
        if h3s:
            h3_html = "".join(
                f'<div class="h3-row">'
                f'<span class="h3-arrow">↳</span>'
                f'<span class="badge b-num" style="font-size:0.55rem;margin-right:4px">H3</span>'
                f'{h}</div>'
                for h in h3s
            )

        # Bullet rows — content guidance when no real H3s
        bullet_html = ""
        if bullets and not h3s:
            bullet_html = (
                '<div style="padding:4px 0 2px;font-size:0.72rem;color:#94a3b8;'
                'font-weight:600;text-transform:uppercase;letter-spacing:.4px">'
                '💡 Nội dung gợi ý</div>' +
                "".join(
                    f'<div class="h3-row" style="color:#64748b">'
                    f'<span style="color:#cbd5e1;margin-right:6px;flex-shrink:0">•</span>'
                    f'{b}</div>'
                    for b in bullets
                )
            )

        body_content = h3_html + bullet_html
        body = f'<div class="sec-body">{body_content}</div>' if body_content else ""

        col_m, col_c = st.columns([11,1])
        with col_m:
            st.markdown(f"""<div class="sec {sc}">
              <div class="sec-head">
                <span class="badge b-num">H2 {idx+1}</span>{block['h2']}
                <span class="badge {bc}">{bt}</span>{nh}
              </div>{body}</div>""", unsafe_allow_html=True)
        with col_c:
            lines = [f"H2: {block['h2']}"]
            for h in h3s:   lines.append(f"  H3: {h}")
            for b in bullets: lines.append(f"  • {b}")
            st.download_button("📋", data="\n".join(lines),
                               file_name=f"h2_{idx+1}.txt",
                               mime="text/plain", key=f"dl_h2_{idx}", help=f"H2 {idx+1}")

# ═══════════════════════════════════════════════════════════════════
# Feature #2: EDITABLE OUTLINE
# ═══════════════════════════════════════════════════════════════════
def outline_to_df(data: dict) -> pd.DataFrame:
    """Convert outline JSON → flat DataFrame for st.data_editor."""
    rows = []
    rows.append({"Level":"H1","Text":data.get("h1",""),"Source":"—","Note":""})
    for block in data.get("outline",[]):
        src = block.get("source","ai").capitalize()
        rows.append({"Level":"H2","Text":block.get("h2",""),"Source":src,
                     "Note":block.get("note","")})
        for h3 in block.get("h3s",[]):
            rows.append({"Level":"H3","Text":h3,"Source":"","Note":""})
        for b in block.get("bullets",[]):
            rows.append({"Level":"Bullet","Text":b,"Source":"","Note":""})
    return pd.DataFrame(rows)

def df_to_outline(df: pd.DataFrame, original: dict) -> dict:
    """Reconstruct outline JSON from edited DataFrame."""
    result = dict(original)
    result["faq"] = []  # always empty
    h2_blocks: list[dict] = []
    current_h2: dict | None = None

    for _, row in df.iterrows():
        lvl  = (row.get("Level") or "").strip()
        text = (row.get("Text")  or "").strip()
        if not text:
            continue
        if lvl == "H1":
            result["h1"] = text
        elif lvl == "H2":
            if current_h2: h2_blocks.append(current_h2)
            src = (row.get("Source") or "ai").lower()
            if src not in VALID_SOURCES: src = "ai"
            current_h2 = {"h2":text,"source":src,"h3s":[],"bullets":[],
                          "note":(row.get("Note") or "").strip()}
        elif lvl == "H3":
            if current_h2 is None:
                current_h2 = {"h2":"(untitled)","source":"ai","h3s":[],"bullets":[],"note":""}
            current_h2["h3s"].append(text)
        elif lvl == "Bullet":
            if current_h2 is None:
                current_h2 = {"h2":"(untitled)","source":"ai","h3s":[],"bullets":[],"note":""}
            current_h2["bullets"].append(text)

    if current_h2: h2_blocks.append(current_h2)
    result["outline"] = h2_blocks
    return result

def render_editor(data: dict, wc_stats: dict) -> dict:
    """
    Feature #2: Editable outline using st.data_editor.
    Returns possibly-modified outline dict.
    """
    st.markdown('<div class="edit-banner">✏️ <b>Edit mode</b> — click any cell to edit. '
                'Add/delete rows. Level: H1 / H2 / H3 / Bullet</div>',
                unsafe_allow_html=True)

    df = outline_to_df(data)

    edited_df = st.data_editor(
        df,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Level": st.column_config.SelectboxColumn(
                "Level", options=["H1","H2","H3","Bullet"], width="small"
            ),
            "Text":   st.column_config.TextColumn("Text",   width="large"),
            "Source": st.column_config.SelectboxColumn(
                "Source", options=["Competitor","Ai","Hybrid","—",""], width="small"
            ),
            "Note":   st.column_config.TextColumn("Note",   width="medium"),
        },
        key="outline_editor",
        height=min(60 + len(df)*35, 600),
    )

    return df_to_outline(edited_df, data)

# ═══════════════════════════════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════════════════════════════
def outline_to_text(keyword: str, data: dict, wc_stats: dict) -> str:
    lines = [f"OUTLINE: {keyword}", ""]
    if data.get("h1"):               lines.append(f"H1: {data['h1']}")
    if data.get("meta_description"): lines.append(f"Meta: {data['meta_description']}")
    if data.get("search_intent_confirmed"): lines.append(f"Intent: {data['search_intent_confirmed']}")
    if wc_stats:
        lines.append(f"Target: ~{wc_stats['target']:,} words (median {wc_stats['median']:,})")
    lines.append("")
    for i,b in enumerate(data.get("outline",[]),1):
        lines.append(f"H2 {i}: {b['h2']}  [{b.get('source','ai')}]")
        for h in b.get("h3s",[]):      lines.append(f"   H3: {h}")
        for pt in b.get("bullets",[]): lines.append(f"   • {pt}")
        lines.append("")
    return "\n".join(lines)

def _kw_to_slug(kw: str) -> str:
    slug = re.sub(r"[^a-z0-9\s-]", "", kw.lower())
    return re.sub(r"\s+", "-", slug.strip())[:60]

ZIMM_HEADERS = [
    "ARTICLE TITLE", "OUTLINE FOCUS", "BACKGROUND",
    "OUTLINE", "SEO KEYWORDS", "ONE WORDPRESS CATEGORY", "SLUG",
]

def _outline_to_zimmwriter_row(keyword: str, data: dict, serp_results: list,
                               background_text: str = "") -> list:
    """Build one CSV data row from outline data."""
    title = data.get("h1") or keyword
    intent = data.get("search_intent_confirmed", "")
    angles = data.get("unique_angles", [])
    focus_parts = [p for p in [intent] + angles[:3] if p]
    outline_focus = ". ".join(focus_parts)
    if background_text:
        background = background_text
    else:
        urls = [r["url"] for r in (serp_results or []) if r.get("url")][:3]
        background = "\n".join(urls)
    lines = []
    for block in data.get("outline", []):
        h2 = (block.get("h2") or "").strip()
        if h2:
            lines.append(h2)
        for h3 in (block.get("h3s") or []):
            if h3.strip():
                lines.append(f"- {h3.strip()}")
    outline_text = "\n".join(lines)
    slug = _kw_to_slug(keyword)
    return [title, outline_focus, background, outline_text, "", "", slug]

def outline_to_zimmwriter_csv(keyword: str, data: dict, serp_results: list,
                               background_text: str = "") -> str:
    """Single-keyword ZimmWriter CSV."""
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(ZIMM_HEADERS)
    w.writerow(_outline_to_zimmwriter_row(keyword, data, serp_results, background_text))
    return buf.getvalue()

def bulk_to_zimmwriter_csv(results: list) -> str:
    """Multi-keyword ZimmWriter CSV — one row per successful keyword."""
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(ZIMM_HEADERS)
    for r in results:
        if r.get("status") != "done" or not r.get("outline"):
            continue
        w.writerow(_outline_to_zimmwriter_row(
            r["keyword"], r["outline"], r.get("serp", []), r.get("background", "")
        ))
    return buf.getvalue()

def save_zimmwriter_to_disk(keyword: str, csv_content: str) -> str:
    """Save CSV to output/ folder next to app.py. Returns filepath."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir  = os.path.join(base_dir, "output")
    os.makedirs(out_dir, exist_ok=True)
    filename = f"zimmwriter_{_kw_to_slug(keyword)}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = os.path.join(out_dir, filename)
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        f.write(csv_content)
    return filepath

def run_single_for_bulk(kw: str, dfs_login: str, dfs_password: str,
                        anthropic_key: str, location_code: int, serp_lang: str,
                        use_jina: bool, t1: int, t2: int,
                        on_status=None) -> dict:
    """Run full pipeline for one keyword. on_status(msg) called at each step."""
    def _s(msg):
        if on_status: on_status(msg)

    result = {"keyword": kw, "status": "error", "outline": None,
              "serp": [], "wc_stats": {}, "h2_stats": {}}
    try:
        _s("🔍 Fetching SERP...")
        serp = fetch_serp(kw, dfs_login, dfs_password, location_code, serp_lang)
        if not serp:
            result["status"] = "no_serp"
            return result
        result["serp"] = serp
        _s(f"🕷️ Crawling top {len(serp)} pages...")

        # Auto-detect language giống single mode
        detected_lang = detect_language(kw)
        lang = detected_lang if detected_lang else serp_lang

        intent_hint  = detect_intent_from_modifier(kw)
        serp_intent  = intent_from_serp_titles(serp)

        def _on_crawl(done, total, r):
            _s(f"🕷️ Crawling {done}/{total} pages...")

        crawl    = crawl_all(serp, t1, t2, use_jina, dfs_login, dfs_password, _on_crawl)
        wc_stats = competitor_word_count_stats(crawl)
        h2_stats = competitor_h2_stats(crawl)
        deduped  = dedup_and_weight_headings(crawl)
        result["wc_stats"] = wc_stats
        result["h2_stats"] = h2_stats

        _s("🤖 AI generating outline + background in parallel...")
        prompt = build_prompt(kw, lang, intent_hint, serp_intent,
                              serp, deduped, crawl, wc_stats, h2_stats)
        with ThreadPoolExecutor(max_workers=2) as ex:
            bg_future  = ex.submit(generate_background_text, kw, lang, crawl, anthropic_key, serp)
            raw_future = ex.submit(call_claude_stream, SYSTEM_PROMPT, prompt, anthropic_key, None, 6000)
            raw = raw_future.result()
            bg  = bg_future.result(timeout=30)
        data   = parse_json_response(raw)
        errors = validate_outline(data)
        fatal  = [e for e in errors if "Missing" in e or "empty" in e]
        if fatal:
            result["status"] = "ai_error: " + "; ".join(fatal[:2])
            return result
        result["outline"]    = fix_outline_data(data)
        result["background"] = bg
        result["status"]     = "done"
        _s("✅ Done")
    except Exception as e:
        result["status"] = f"error: {str(e)[:100]}"
    return result

def run_batch_parallel(kws_batch: list, dfs_login: str, dfs_password: str,
                       anthropic_key: str, location_code: int, serp_lang: str,
                       use_jina: bool, t1: int, t2: int) -> list:
    """Run a batch of keywords in parallel threads. Returns results in original order."""
    results = [None] * len(kws_batch)
    with ThreadPoolExecutor(max_workers=len(kws_batch)) as ex:
        fmap = {
            ex.submit(
                run_single_for_bulk, kw, dfs_login, dfs_password,
                anthropic_key, location_code, serp_lang, use_jina, t1, t2,
            ): i
            for i, kw in enumerate(kws_batch)
        }
        for f in as_completed(fmap):
            i = fmap[f]
            try:
                results[i] = f.result()
            except Exception as e:
                results[i] = {
                    "keyword": kws_batch[i], "status": f"error: {str(e)[:80]}",
                    "outline": None, "serp": [], "wc_stats": {}, "h2_stats": {},
                }
    return results

def run_ai_and_validate(system, prompt, key, stream_slot):
    raw = ""
    try:
        def on_chunk(t):
            prev = t[-500:].replace("<","&lt;").replace(">","&gt;")
            stream_slot.markdown(f'<div class="stream-box">{prev}</div>',
                                 unsafe_allow_html=True)
        raw = call_claude_stream(system, prompt, key, on_chunk=on_chunk, max_tokens=6000)
        stream_slot.empty()
    except ValueError as e:
        stream_slot.empty(); st.error(str(e)); return None, raw
    except Exception as e:
        stream_slot.empty(); st.error(f"Streaming error: {e}"); return None, raw

    try:
        data = parse_json_response(raw)
    except json.JSONDecodeError as e:
        st.error(f"AI returned invalid JSON: {e}")
        with st.expander("Raw response"): st.code(raw[:3000])
        return None, raw

    errors = validate_outline(data)
    fatal  = [e for e in errors if "Missing" in e or "empty" in e]
    warns  = [e for e in errors if e not in fatal]
    for w in warns: st.warning(f"⚠️ {w}")
    if fatal:
        st.markdown('<div class="val-err">❌ <b>Validation failed:</b><br>'
                    + "<br>".join(fatal)+"</div>", unsafe_allow_html=True)
        with st.expander("Raw response"): st.code(raw[:3000])
        return None, raw
    return fix_outline_data(data), raw

# ═══════════════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════════════
SESS_DEFAULTS = {
    "serp":None,"crawl":None,"outline":None,"edited_outline":None,
    "wc_stats":None,"h2_stats":None,"last_kw":None,
    "detected_lang":None,"intent_hint":None,"deduped":None,"serp_intent":None,
    "kw_history":[],"running":False,"edit_mode":False,"background_text":"",
    # bulk
    "bulk_running":False,"bulk_keywords":[],"bulk_results":[],"bulk_batch_size":3,
}
for k,v in SESS_DEFAULTS.items():
    if k not in st.session_state: st.session_state[k]=v

# ═══════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ Settings")

    with st.expander("🔑 API Keys", expanded=True):
        dfs_login     = st.text_input("DataForSEO Login",    placeholder="email@example.com")
        dfs_password  = st.text_input("DataForSEO Password", type="password")
        anthropic_key = st.text_input("Anthropic API Key",   type="password", placeholder="sk-ant-...")

    with st.expander("🌐 SERP / Market"):
        loc_opts = {
            "🇻🇳 Việt Nam":(2704,"vi"),"🇺🇸 United States":(2840,"en"),
            "🇬🇧 United Kingdom":(2826,"en"),"🇦🇺 Australia":(2036,"en"),
            "🇸🇬 Singapore":(2702,"en"),
        }
        loc_choice = st.selectbox("Market", list(loc_opts.keys()))
        location_code, serp_lang = loc_opts[loc_choice]

    with st.expander("🌏 Language Override"):
        lang_override = st.selectbox("Keyword language",
            ["Auto detect","Vietnamese (vi)","English (en)"],
            help="Auto detect works well.")

    with st.expander("🕷️ Crawl"):
        t1 = st.slider("Timeout attempt 1 (s)", 5, 15, 8)
        t2 = st.slider("Timeout retry (s)", 10, 30, 18)
        # Feature #1: Jina toggle
        use_jina = st.toggle("Jina Reader fallback",value=True,
            help="Falls back to r.jina.ai when direct crawl fails (Cloudflare, etc.)")

    st.divider()
    st.caption("🔒 Keys live in session only.")
    st.caption(f"🔧 BS4 parser: **{BS4_PARSER}**")

    if st.session_state.kw_history:
        st.divider()
        st.markdown("**🕐 Recent keywords**")
        for kh in reversed(st.session_state.kw_history[-8:]):
            st.caption(f"• {kh}")

    if st.session_state.wc_stats:
        st.divider()
        wc = st.session_state.wc_stats
        st.caption(f"**WC:** {wc['min']:,}–{wc['max']:,} · target ~{wc['target']:,}")
    if st.session_state.h2_stats:
        h2 = st.session_state.h2_stats
        st.caption(f"**H2:** avg={h2['avg']} median={h2['median']} range={h2['min']}–{h2['max']}")

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
st.title("🧭 SEO Outline Generator")

tab_single, tab_bulk = st.tabs(["🔍 Single Keyword", "📋 Bulk"])

# ── Tab Single ────────────────────────────────────────────────────
with tab_single:
    kw_col,btn_col,reg_col = st.columns([5,1.5,1.8])
    with kw_col:
        keyword = st.text_input("kw", placeholder="e.g.  cách học tiếng anh  /  best project management tools",
                                label_visibility="collapsed", disabled=st.session_state.running)
    with btn_col:
        run_btn = st.button("🚀 Generate", type="primary", use_container_width=True,
                            disabled=st.session_state.running)
    with reg_col:
        regen_btn = st.button("🔄 New Outline", use_container_width=True,
                              disabled=(not st.session_state.crawl) or st.session_state.running,
                              help="Re-run AI — skips crawl")

    if keyword and not st.session_state.running:
        auto_lang   = detect_language(keyword)
        eff_lang    = (auto_lang if lang_override=="Auto detect"
                       else "vi" if "Vietnamese" in lang_override else "en")
        lang_src    = "auto" if lang_override=="Auto detect" else "manual"
        intent_hint = detect_intent_from_modifier(keyword)
        il,ibg,icolor = INTENT_LABELS.get(intent_hint["intent"],INTENT_LABELS["mixed"])
        flag = "🇻🇳" if eff_lang=="vi" else "🇬🇧"
        cc   = {"high":"#16a34a","medium":"#d97706","low":"#94a3b8"}.get(intent_hint["confidence"],"#94a3b8")
        sig  = ", ".join(intent_hint["signals"][:4]) or "—"
        st.markdown(f"""
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;
                    margin:6px 0 14px;font-size:0.82rem;">
          <span class="badge b-lang">{flag} {eff_lang.upper()} · {lang_src}</span>
          <span class="badge" style="background:{ibg};color:{icolor}">{il}</span>
          <span style="color:{cc};font-weight:600">{intent_hint['confidence']} confidence</span>
          <span style="color:#94a3b8">signals: {sig}</span>
        </div>""", unsafe_allow_html=True)
    else:
        eff_lang    = serp_lang
        intent_hint = {"intent":"informational","confidence":"low","signals":[]}
# ═══════════════════════════════════════════════════════════════════
# PIPELINE: Full run
# ═══════════════════════════════════════════════════════════════════
if run_btn and not st.session_state.running:
    errs=[]
    if not keyword.strip(): errs.append("Please enter a keyword.")
    if not dfs_login:       errs.append("DataForSEO login required.")
    if not dfs_password:    errs.append("DataForSEO password required.")
    if not anthropic_key:   errs.append("Anthropic API key required.")
    if errs:
        for e in errs: st.error(e)
        st.stop()
    st.session_state.running    = True
    st.session_state.edit_mode  = False
    st.session_state.edited_outline = None
    st.rerun()

if st.session_state.running and not regen_btn:
    kw = (keyword.strip() if keyword.strip()
          else st.session_state.get("last_kw",""))
    if not kw:
        st.session_state.running = False; st.stop()

    st.session_state.last_kw       = kw
    st.session_state.detected_lang  = eff_lang
    st.session_state.intent_hint    = intent_hint
    hist = st.session_state.kw_history or []
    if kw not in hist: hist.append(kw)
    st.session_state.kw_history = hist[-20:]

    try:
        # Step 1: SERP
        with st.status("🔍 Fetching SERP...", expanded=False) as s:
            try:
                serp = fetch_serp(kw, dfs_login, dfs_password, location_code, serp_lang)
                st.session_state.serp = serp
                si = intent_from_serp_titles(serp)
                st.session_state.serp_intent = si
                s.update(label=f"✅ SERP — {len(serp)} URLs · intent: {si.get('intent','?')}",
                         state="complete")
            except ValueError as e:
                s.update(label="❌ SERP failed", state="error"); st.error(str(e))
                st.session_state.running=False; st.stop()
            except Exception as e:
                s.update(label="❌ SERP failed", state="error"); st.error(f"Unexpected: {e}")
                st.session_state.running=False; st.stop()

        if not serp:
            st.error("No valid SERP results."); st.session_state.running=False; st.stop()

        with st.expander(f"📋 Google Top {len(serp)} — {kw}", expanded=False):
            for r in serp:
                st.markdown(f"""<div class="dom-card">
                  <b>#{r['rank']}</b> {r['title']}<br>
                  <a href="{r['url']}" target="_blank">🔗 {domain_of(r['url'])}</a>
                </div>""", unsafe_allow_html=True)

        # Step 2: Parallel crawl
        crawl_hdr = st.empty()
        prog      = st.progress(0)
        log_slot  = st.empty()
        log: list[str] = []
        crawl_hdr.markdown("**🕷️ Crawling pages in parallel...**")
        t0 = time.time()

        def on_crawl(done, total, r):
            d   = domain_of(r["url"])
            wc  = r.get("word_count",0)
            sts = r.get("status","fail")
            mtd = r.get("method","direct")
            method_tag = (
                " 🟢dfs"   if mtd in ("dfs","dfs_content") else
                " 🟣jina"  if mtd == "jina" else ""
            )
            icon = "✅" if sts in ("ok","dfs","jina") else ("🔁" if sts=="retry_ok" else "❌")
            log.append(f"{icon} {d}{f' · {wc:,}w' if wc else ''}{method_tag}")
            prog.progress(done/total)
            log_slot.markdown("  \n".join(log[-8:]))

        crawl = crawl_all(serp, t1, t2, use_jina,
                          dfs_login, dfs_password, on_crawl)
        elapsed = time.time()-t0
        st.session_state.crawl = crawl

        wc_stats = competitor_word_count_stats(crawl)
        st.session_state.wc_stats = wc_stats
        h2_stats = competitor_h2_stats(crawl)   # Feature #3
        st.session_state.h2_stats = h2_stats
        deduped  = dedup_and_weight_headings(crawl)
        st.session_state.deduped = deduped

        prog.empty(); log_slot.empty(); crawl_hdr.empty()

        ok_n    = sum(1 for r in crawl if r.get("headings"))
        dfs_n   = sum(1 for r in crawl if r.get("method") in ("dfs","dfs_content"))
        jina_n  = sum(1 for r in crawl if r.get("method")=="jina")
        retry_n = sum(1 for r in crawl if r.get("status")=="retry_ok")
        fail_n  = sum(1 for r in crawl if r.get("status")=="fail")
        method_parts = []
        if dfs_n:   method_parts.append(f"🟢 {dfs_n} via DFS On-Page")
        if jina_n:  method_parts.append(f"🟣 {jina_n} via Jina")
        if retry_n: method_parts.append(f"{retry_n} retried")
        if fail_n:  method_parts.append(f"{fail_n} failed")
        method_str = " · " + " · ".join(method_parts) if method_parts else ""
        st.success(
            f"✅ Crawled {ok_n}/{len(crawl)} in **{elapsed:.1f}s**"
            f"{method_str}"
            f" · {len(deduped)} unique headings"
        )
        if h2_stats:
            st.info(f"📊 Competitor H2 count: avg={h2_stats['avg']} · "
                    f"median={h2_stats['median']} · range {h2_stats['min']}–{h2_stats['max']} "
                    f"→ **target: {h2_stats['target']} H2 sections**")

        with st.expander("🕷️ Crawl details", expanded=False):
            tab1,tab2 = st.tabs(["Per-page","Deduplicated (freq)"])
            with tab1:
                for r in crawl:
                    d  = domain_of(r["url"])
                    hs = r.get("headings") or []
                    wc = r.get("word_count",0)
                    sts= r.get("status","fail")
                    mtd= r.get("method","direct")
                    if not hs:
                        err=(r.get("error") or "")[:120]
                        st.markdown(f'<div class="dom-card">❌ <b>{d}</b><br>'
                                    f'<small style="color:#94a3b8">{err}</small></div>',
                                    unsafe_allow_html=True); continue
                    h2c=sum(1 for h in hs if h["tag"]=="h2")
                    h3c=sum(1 for h in hs if h["tag"]=="h3")
                    if mtd in ("dfs","dfs_content"):
                        rb = ' <span class="badge b-comp">🟢 DFS</span>'
                    elif mtd=="jina":
                        rb = ' <span class="badge b-jina">🟣 Jina</span>'
                    elif sts=="retry_ok":
                        rb = ' <span class="badge b-warn">retry</span>'
                    else:
                        rb = ""
                    rows="".join(f'<span class="hp hp-{h["tag"]}">{h["tag"].upper()}</span>{h["text"]}<br>'
                                 for h in hs)
                    st.markdown(f"""<div class="dom-card">
                      <b>{d}</b>{rb}
                      <span class="badge b-comp">{len(hs)}·{h2c}H2·{h3c}H3</span>
                      {f'· <b>{wc:,}</b>w' if wc else ''}
                      <a href="{r['url']}" target="_blank" style="float:right">🔗</a><br>
                      <div style="margin-top:6px;font-size:0.82rem;color:#374151">{rows}</div>
                    </div>""", unsafe_allow_html=True)
            with tab2:
                tok = sum(1 for r in crawl if r.get("headings"))
                for h in deduped:
                    f_ = h["freq"]
                    c_ = "#166534" if f_>=tok*0.6 else "#92400e" if f_>=tok*0.3 else "#64748b"
                    st.markdown(f'<span class="hp hp-{h["tag"]}">{h["tag"].upper()}</span>'
                                f'<span style="color:{c_};font-weight:600;font-size:0.75rem">'
                                f'[{f_}/{tok}]</span> {h["text"]}',
                                unsafe_allow_html=True)

        # Step 3: AI outline (Sonnet) + background (Haiku) chạy song song
        # Haiku submit trước, Sonnet stream trên main thread, join sau khi Sonnet xong
        _bg_future = ThreadPoolExecutor(max_workers=1).submit(
            generate_background_text, kw, eff_lang, crawl, anthropic_key, serp
        )

        st.markdown("**🤖 Generating outline...**")
        ss = st.empty()
        ss.markdown('<div class="stream-box">Connecting to Claude...</div>',
                    unsafe_allow_html=True)
        prompt = build_prompt(kw, eff_lang, intent_hint,
                              st.session_state.serp_intent or {},
                              serp, deduped, crawl, wc_stats, h2_stats)
        od, _ = run_ai_and_validate(SYSTEM_PROMPT, prompt, anthropic_key, ss)
        if od:
            st.session_state.outline = od
            st.success("✅ Outline ready!")

        # Thu kết quả Haiku (chắc chắn xong rồi vì Sonnet lâu hơn nhiều)
        try:
            bg_text = _bg_future.result(timeout=30)
        except Exception:
            bg_text = ""
        st.session_state.background_text = bg_text
        label = "✅ Background context ready" if bg_text else "⚠️ Background skipped (no data)"
        st.caption(f"✍️ {label}")

    finally:
        st.session_state.running = False

# PIPELINE: Regenerate
elif regen_btn and not st.session_state.running:
    if not anthropic_key:
        st.error("Anthropic API key required."); st.stop()
    st.session_state.running    = True
    st.session_state.edit_mode  = False
    st.session_state.edited_outline = None
    try:
        kw      = st.session_state.last_kw or keyword
        lang    = st.session_state.detected_lang or eff_lang
        hint    = st.session_state.intent_hint or intent_hint
        wc      = st.session_state.wc_stats or {}
        h2      = st.session_state.h2_stats or {}
        deduped = st.session_state.deduped or []
        si      = st.session_state.serp_intent or {}
        serp_r  = st.session_state.serp or []
        crawl_r = st.session_state.crawl or []
        st.markdown("**🔄 Regenerating outline...**")
        ss = st.empty()
        ss.markdown('<div class="stream-box">Connecting...</div>', unsafe_allow_html=True)
        prompt = build_prompt(kw, lang, hint, si, serp_r, deduped, crawl_r, wc, h2)
        od, _ = run_ai_and_validate(SYSTEM_PROMPT, prompt, anthropic_key, ss)
        if od:
            st.session_state.outline = od
            st.success("✅ New outline ready!")
    finally:
        st.session_state.running = False

# ═══════════════════════════════════════════════════════════════════
# RENDER RESULTS
# ═══════════════════════════════════════════════════════════════════
if st.session_state.outline and not st.session_state.running:
    kw = st.session_state.last_kw or keyword
    wc = st.session_state.wc_stats or {}

    st.divider()

    # Header row with edit toggle
    hcol, ecol = st.columns([6,2])
    with hcol:
        st.subheader(f"📝 Outline — {kw}")
    with ecol:
        edit_mode = st.toggle("✏️ Edit outline", value=st.session_state.edit_mode,
                              key="edit_toggle",
                              help="Switch between view and edit mode")
        st.session_state.edit_mode = edit_mode

    # Get the working outline (edited or original)
    working = st.session_state.edited_outline or st.session_state.outline

    if st.session_state.edit_mode:
        # Feature #2: editable grid
        edited = render_editor(working, wc)
        st.session_state.edited_outline = edited
        # Preview in real-time below editor
        with st.expander("👁️ Preview edited outline", expanded=False):
            render_outline_view(edited, wc)
        export_data = edited
    else:
        render_outline_view(working, wc)
        export_data = working

    # Export
    st.divider()
    txt = outline_to_text(kw, export_data, wc)
    c1,c2,c3 = st.columns([2,2,4])
    with c1:
        st.download_button("⬇️ Download .txt", data=txt,
                           file_name=f"outline_{kw[:40].replace(' ','_')}.txt",
                           mime="text/plain", use_container_width=True)
    with c2:
        if st.session_state.edited_outline:
            if st.button("↩️ Reset edits", use_container_width=True):
                st.session_state.edited_outline = None
                st.session_state.edit_mode = False
                st.rerun()
    with c3:
        with st.expander("📋 Copy raw text"):
            st.code(txt, language=None)

    with st.expander("🔧 Raw JSON"):
        st.json(export_data)

    # ── ZimmWriter CSV Export ─────────────────────────────────────
    st.divider()
    st.markdown("**📊 Export ZimmWriter CSV**")
    zimm_csv = outline_to_zimmwriter_csv(
        kw, export_data, st.session_state.serp or [],
        st.session_state.get("background_text", "")
    )
    zc1, zc2 = st.columns([1, 1])
    with zc1:
        if st.button("💾 Lưu vào output/", use_container_width=True,
                     help="Lưu file CSV vào thư mục output/ trong project"):
            try:
                fp = save_zimmwriter_to_disk(kw, zimm_csv)
                st.success(f"✅ Đã lưu: `{fp}`")
            except Exception as e:
                st.error(f"Lỗi khi lưu: {e}")
    with zc2:
        st.download_button(
            "⬇️ Download ZimmWriter CSV",
            data=zimm_csv.encode("utf-8-sig"),
            file_name=f"zimmwriter_{_kw_to_slug(kw)}.csv",
            mime="text/csv",
            use_container_width=True,
            help="Download CSV để import vào ZimmWriter Bulk Writer",
        )
    with st.expander("👁️ Preview ZimmWriter CSV"):
        st.code(zimm_csv, language=None)

# Landing
elif not st.session_state.outline:
    st.markdown("""
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;
                padding:2rem;text-align:center;margin-top:1rem">
      <div style="font-size:2.5rem">🧭</div>
      <div style="font-size:1.05rem;font-weight:600;margin:8px 0 4px">SEO Outline Generator</div>
      <div style="color:#64748b;font-size:0.88rem">
        Keyword → DataForSEO Top 10 → Crawl + Jina fallback → AI outline
      </div>
    </div>""", unsafe_allow_html=True)

# ── Tab Bulk ──────────────────────────────────────────────────────
with tab_bulk:
    st.markdown("### 📋 Bulk Keyword Processing")
    st.caption("Mỗi keyword = 1 hàng trong file ZimmWriter CSV. Nhập API keys trong sidebar trước.")

    bulk_input = st.text_area(
        "Keywords (mỗi dòng 1 keyword)",
        placeholder="what is a pergola\nbest pergola kits\nhow to build a pergola\npergola vs gazebo",
        height=220,
        disabled=st.session_state.bulk_running,
    )

    bs_col, btn_col, info_col = st.columns([2, 2, 4])
    with bs_col:
        batch_size = st.select_slider(
            "⚡ Parallel batch",
            options=[1, 2, 3, 5],
            value=st.session_state.bulk_batch_size,
            disabled=st.session_state.bulk_running,
            help="Số keywords chạy song song cùng lúc. Batch 3 = ~3x nhanh hơn.",
        )
    with btn_col:
        bulk_run_btn = st.button(
            "🚀 Run Bulk", type="primary", use_container_width=True,
            disabled=st.session_state.bulk_running,
        )
    with info_col:
        if st.session_state.bulk_running:
            st.info("⏳ Đang xử lý... vui lòng chờ")
        else:
            kws_preview = [k.strip() for k in bulk_input.splitlines() if k.strip()]
            if kws_preview:
                n_batches = -(-len(kws_preview) // batch_size)  # ceiling division
                st.caption(f"📊 {len(kws_preview)} keywords · {n_batches} batches · batch size {batch_size}")

    if bulk_run_btn and not st.session_state.bulk_running:
        kws = [k.strip() for k in bulk_input.splitlines() if k.strip()]
        errs = []
        if not kws:           errs.append("Nhập ít nhất 1 keyword.")
        if not dfs_login:     errs.append("DataForSEO login required.")
        if not dfs_password:  errs.append("DataForSEO password required.")
        if not anthropic_key: errs.append("Anthropic API key required.")
        if errs:
            for e in errs: st.error(e)
        else:
            st.session_state.bulk_keywords   = kws
            st.session_state.bulk_results    = []
            st.session_state.bulk_running    = True
            st.session_state.bulk_batch_size = batch_size
            st.rerun()

    if st.session_state.bulk_running:
        kws        = st.session_state.bulk_keywords
        bs         = st.session_state.bulk_batch_size
        n          = len(kws)
        n_batches  = -(-n // bs)
        prog       = st.progress(0)
        status_slot = st.empty()
        step_slot   = st.empty()

        results   = list(st.session_state.bulk_results)
        done_so_far = len(results)

        # Chia keywords còn lại thành batches
        remaining   = kws[done_so_far:]
        batches     = [remaining[i:i+bs] for i in range(0, len(remaining), bs)]
        batch_start = done_so_far // bs  # batch number đã xong

        for b_idx, batch in enumerate(batches):
            batch_num  = batch_start + b_idx + 1
            kw_labels  = " · ".join(f"**{k[:30]}**" for k in batch)
            status_slot.info(f"🔄 Batch {batch_num}/{n_batches}: {kw_labels}")

            if bs == 1:
                # Sequential với per-step status
                def _on_status(msg, _kw=batch[0]):
                    step_slot.caption(f"⏱️ {_kw}: {msg}")
                batch_results = [run_single_for_bulk(
                    batch[0], dfs_login, dfs_password, anthropic_key,
                    location_code, serp_lang, use_jina, t1, t2,
                    on_status=_on_status,
                )]
            else:
                step_slot.caption(f"⏱️ Running {len(batch)} keywords in parallel...")
                batch_results = run_batch_parallel(
                    batch, dfs_login, dfs_password, anthropic_key,
                    location_code, serp_lang, use_jina, t1, t2,
                )

            results.extend(batch_results)
            st.session_state.bulk_results = results

            done_in_batch = sum(1 for r in batch_results if r["status"] == "done")
            fail_in_batch = len(batch_results) - done_in_batch
            summary = f"✅ {done_in_batch} done" + (f" · ❌ {fail_in_batch} lỗi" if fail_in_batch else "")
            step_slot.caption(f"Batch {batch_num}: {summary}")
            prog.progress(len(results) / n)

        st.session_state.bulk_running = False
        status_slot.empty()
        step_slot.empty()
        st.rerun()

    if st.session_state.bulk_results and not st.session_state.bulk_running:
        results  = st.session_state.bulk_results
        done_n   = sum(1 for r in results if r["status"] == "done")
        fail_n   = len(results) - done_n
        st.success(f"✅ Hoàn thành **{done_n}/{len(results)}** keywords" +
                   (f" · {fail_n} lỗi" if fail_n else ""))

        # Status table
        tbl = pd.DataFrame([{
            "Keyword":      r["keyword"],
            "Status":       "✅ done" if r["status"] == "done" else f"❌ {r['status']}",
            "H2":           len((r.get("outline") or {}).get("outline", [])),
            "~Words":       r.get("wc_stats", {}).get("target", "—"),
        } for r in results])
        st.dataframe(tbl, use_container_width=True, hide_index=True)

        # Export
        bulk_csv = bulk_to_zimmwriter_csv(results)
        st.divider()
        st.markdown("**📊 Export ZimmWriter CSV**")
        ec1, ec2 = st.columns([1, 1])
        with ec1:
            if st.button("💾 Lưu vào output/", key="bulk_save", use_container_width=True):
                try:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    out_dir  = os.path.join(base_dir, "output")
                    os.makedirs(out_dir, exist_ok=True)
                    fname = f"zimmwriter_bulk_{time.strftime('%Y%m%d_%H%M%S')}.csv"
                    fp    = os.path.join(out_dir, fname)
                    with open(fp, "w", newline="", encoding="utf-8-sig") as f:
                        f.write(bulk_csv)
                    st.success(f"✅ Đã lưu: `{fp}`")
                except Exception as e:
                    st.error(f"Lỗi: {e}")
        with ec2:
            st.download_button(
                "⬇️ Download ZimmWriter CSV",
                data=bulk_csv.encode("utf-8-sig"),
                file_name=f"zimmwriter_bulk_{time.strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
                key="bulk_dl",
            )
        with st.expander("👁️ Preview CSV"):
            st.code(bulk_csv, language=None)

        if st.button("🗑️ Xoá kết quả", key="bulk_clear"):
            st.session_state.bulk_results  = []
            st.session_state.bulk_keywords = []
            st.rerun()
