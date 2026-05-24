"""
bulk_cli.py — CLI bulk keyword processor (chạy local, không cần browser)

Usage:
    python bulk_cli.py keywords.txt --market US --batch 5

Arguments:
    keywords.txt   File chứa keywords, mỗi dòng 1 keyword
    --market       VN | US | UK | AU | SG  (default: US)
    --batch        Số keyword chạy song song (default: 5)
    --output       Tên file CSV output (default: output/bulk_YYYYMMDD_HHMMSS.csv)
    --no-resume    Chạy lại tất cả, không bỏ qua key đã xong
    --no-jina      Tắt Jina fallback

API keys: đặt trong file .env:
    DFS_LOGIN=...
    DFS_PASSWORD=...
    ANTHROPIC_KEY=...
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from difflib import SequenceMatcher
from statistics import median
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ════════════════════════════════════════════════════════════════════
# MARKETS
# ════════════════════════════════════════════════════════════════════
MARKETS = {
    "VN": (2704, "vi"),
    "US": (2840, "en"),
    "UK": (2826, "en"),
    "AU": (2036, "en"),
    "SG": (2702, "en"),
}

# ════════════════════════════════════════════════════════════════════
# CONSTANTS  (copied from app.py — keep in sync)
# ════════════════════════════════════════════════════════════════════
SOCIAL_DOMAINS = {
    "facebook.com","twitter.com","x.com","instagram.com","tiktok.com",
    "youtube.com","linkedin.com","pinterest.com","tumblr.com","snapchat.com",
    "threads.net","vk.com","weibo.com","t.me","telegram.org",
    "reddit.com","quora.com","stackexchange.com","stackoverflow.com",
    "answers.com","answers.yahoo.com",
    "amazon.com","amazon.co.uk","amazon.com.au","ebay.com","aliexpress.com",
    "walmart.com","target.com","costco.com","overstock.com",
    "build.com","menards.com","etsy.com","bestbuy.com","chewy.com",
    "shopee.vn","lazada.vn","tiki.vn","sendo.vn",
    "trustpilot.com","yelp.com","tripadvisor.com","bbb.org","sitejabber.com",
    "g2.com","capterra.com","getapp.com",
    "craigslist.org","offerup.com","nextdoor.com",
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

_PARA_BOILERPLATE = re.compile(
    r"subscribe\s+to\s+(our|the)\b|sign\s+up\s+(for|to\s+get|to\s+receive)\b|"
    r"join\s+our\s+(newsletter|mailing\s+list)|"
    r"we\s+use\s+cookies|cookie\s+policy|accept\s+(all\s+)?cookies|"
    r"privacy\s+policy|terms\s+of\s+(use|service)|"
    r"affiliate\s+(link|disclosure)|this\s+post\s+may\s+contain\s+affiliate|"
    r"all\s+rights\s+reserved|copyright\s+©?\s*\d{4}|"
    r"follow\s+us\s+on\s+(facebook|twitter|instagram|pinterest|tiktok|youtube)|"
    r"like\s+us\s+on\s+facebook|find\s+us\s+on\s+social|"
    r"share\s+this\s+(article|post|page|story)|"
    r"image\s+(credit|source|courtesy)\s*[:—]|photo\s+(credit|by)\s*[:—]|"
    r"\bsponsored\s+(post|content|by)\b|this\s+is\s+a\s+sponsored|"
    r"\badd\s+to\s+cart\b|\bbuy\s+now\b|\bshop\s+now\b|\border\s+now\b|"
    r"filed\s+under\s*[:—]|tagged\s+(with|in)\s*[:—]|"
    r"leave\s+a\s+(comment|reply)\b|post\s+a\s+comment\b|"
    r"about\s+the\s+author|written\s+by\s*[:—]|"
    r"last\s+(updated|modified|reviewed)\s*[:—]\s*\w|"
    r"bấm\s+vào\s+đây|đăng\s+ký\s+nhận|nhận\s+thông\s+báo|"
    r"chính\s+sách\s+(bảo\s+mật|cookie)|bản\s+quyền\s+©",
    re.IGNORECASE,
)

CRAWL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}

JINA_BASE    = "https://r.jina.ai/"
JINA_HEADERS = {"Accept": "text/markdown", "X-Return-Format": "markdown"}
MAX_WORKERS  = 6
CRAWL_MAX_MB = 3

def _bs4_parser():
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

_INTENT_H2_DEFAULTS = {
    "listicle": 8, "how-to": 6, "comparison": 5, "review": 5,
    "commercial": 5, "transactional": 4, "informational": 6,
}

CURRENT_YEAR = 2026

SYSTEM_PROMPT = """Bạn là chuyên gia SEO content strategist. Tạo outline bài viết SEO tốt nhất.

QUY TẮC QUAN TRỌNG:

1. H2 TEXT — dùng ngưỡng tần suất [X/N] VÀ weighted score W (rank 1-2=3pts, rank 3-5=2pts, rank 6+=1pt):
   - [5+/N] HOẶC W≥8: GIỮ NGUYÊN text từ đối thủ (trang quan trọng đồng thuận → heading tốt nhất)
   - [3-4/N] HOẶC W 4-7: có thể paraphrase nhẹ
   - [1-2/N] HOẶC W≤3: viết mới hoàn toàn
   - source="competitor" khi lấy từ đối thủ, source="ai" khi tự tạo, source="hybrid" khi kết hợp
   - LUÔN xóa số thứ tự/prefix của competitor trước khi dùng heading:
     Ví dụ: "2. Deep Dive: Tub Types" → "Deep Dive: Tub Types"

2. H3:
   - CHỈ đưa vào h3s[] nếu đối thủ thực sự có H3 dưới H2 đó trong data crawl
   - Nếu đối thủ KHÔNG có H3 → để h3s=[] và dùng "bullets" để gợi ý nội dung viết gì
   - bullets là gợi ý ngắn (3-6 từ) về điểm cần cover trong section đó
   - Không được bịa H3 khi đối thủ không có
   - NGƯỠNG TỐI THIỂU: mỗi H2 phải có ÍT NHẤT 2 H3 thì mới dùng h3s[]. Nếu chỉ có 1 H3
     từ competitor → bỏ vào bullets thay vì h3s[]

3. TRÙNG NGHĨA — kiểm tra trước khi finalize:
   - H2 vs H2: nếu 2 H2 cùng chủ đề/ý nghĩa dù khác chữ → merge thành 1, bỏ cái trùng
   - H3 vs H2 cha: H3 KHÔNG được lặp lại ý của H2 ngay trên nó
   - H3 vs H3 trong cùng H2: mỗi H3 phải cover 1 khía cạnh khác nhau, không trùng nhau

4. FAQ: KHÔNG tạo FAQ. Để faq=[] rỗng.

5. NĂM THÁNG: Nếu keyword có năm cũ hoặc không có năm → dùng năm hiện tại trong H1/headings.
   Không được dùng năm < {CURRENT_YEAR}.

6. SỐ H2: generate đúng target_h2_count (±1).

7. LOẠI TRỪ HEADINGS TỪ REVIEW/ROUNDUP PAGES: Nhiều competitor là trang review sản phẩm
   (wirecutter, thespruce, consumer reports...). Headings của họ KHÔNG phù hợp với bài
   informational/how-to dù freq/score cao. Khi article_type là informational, how-to, hoặc
   comparison: KHÔNG được include H2 chỉ có nghĩa trong context review sản phẩm, ví dụ:
   - Product picks/awards: "Best Waterproof X", "A Simple Inexpensive X", "Our Top Pick"
   - Review boilerplate: "Flaws but not dealbreakers", "How we tested", "Also consider",
     "Runner-up", "Why trust us", "Our verdict", "Editor's choice"
   Chỉ include H2 structural — giải thích khái niệm, so sánh, hướng dẫn, factors, tips.

8. NGÔN NGỮ: output = ngôn ngữ của keyword.

JSON schema (tất cả field bắt buộc):
{{
  "h1": "string",
  "meta_description": "string 150-160 chars",
  "article_type": "informational|listicle|how-to|comparison|review|commercial|transactional",
  "search_intent_confirmed": "string",
  "unique_angles": ["string"],
  "outline": [
    {{
      "h2": "string",
      "source": "competitor|ai|hybrid",
      "h3s": ["string"],
      "bullets": ["gợi ý nội dung ngắn nếu không có H3"],
      "note": "string"
    }}
  ],
  "faq": []
}}"""

# ZimmWriter CSV
ZIMM_HEADERS = [
    "ARTICLE TITLE", "OUTLINE FOCUS", "BACKGROUND",
    "OUTLINE", "SEO KEYWORDS", "ONE WORDPRESS CATEGORY", "SLUG", "BG QUALITY", "BG GAPS",
]

_NO_DATA_RE = re.compile(
    r'^no\s+(relevant\s+factual\s+information|specific\s+\S[\S\s]{0,30}\s+instructions?'
    r'|relevant\s+\S[\S\s]{0,20}\s+information|background data available)',
    re.IGNORECASE,
)

def _clean_bg_no_data(text):
    """Strip 'no data' sections from background; return (cleaned_text, gaps_str)."""
    if not text:
        return text, ""
    blocks = [b.strip() for b in re.split(r'\n{2,}', text.strip())]
    cleaned, missing = [], []
    for block in blocks:
        if _NO_DATA_RE.match(block) or (len(block) < 250 and _NO_DATA_RE.search(block)):
            if cleaned:
                missing.append(cleaned.pop())
        else:
            cleaned.append(block)
    return '\n\n'.join(cleaned), '; '.join(missing) if missing else ''

_ZIMM_LIST_KWS = [
    "best","top ","top-","must","tips","ways to","reasons","things to",
    "places","options","ideas","examples","benefits","advantages",
    "features","recommendations","essentials","picks","suggestions",
    "attractions","activities","spots","gems","highlights","foods",
    "tốt nhất","hàng đầu","phải","mẹo","cách ","lý do","địa điểm",
    "lựa chọn","ý tưởng","lợi ích","ưu điểm","gợi ý","kinh nghiệm",
    "hoạt động","điểm đến","món ăn",
]

_ZIMM_TABLE_KWS = [
    " vs ","versus","comparison","compare","difference","types of",
    "specifications","specs","breakdown","pros and cons",
    "cost","price","requirements","overview of",
    "so sánh","khác nhau","loại ","thông số","ưu nhược",
    "chi phí","giá ","yêu cầu",
]

_US_UNITS = re.compile(
    r'\b(inch(?:es)?|foot|feet|\bft\b|gallon[s]?|\bgal\b|°F|Fahrenheit|'
    r'pound[s]?|\blbs?\b|\boz\b|ounce[s]?|mile[s]?|mph|quart[s]?|pint[s]?|yard[s]?)\b',
    re.IGNORECASE
)
_METRIC_ONLY = re.compile(
    r'\b\d+\s*mm\b|\bmillimeters?\b|\bmillimetres?\b|'
    r'\b\d+\s*cm\b|\bcentimeters?\b|\bcentimetres?\b|'
    r'\b\d+(?:\.\d+)?\s*m\b|\bmeters?\b|\bmetres?\b|'
    r'\b\d+\s*kg\b|\bkilograms?\b|\bliters?\b|\blitres?\b|'
    r'\bkilometers?\b|\bkilometres?\b|\bkm\b',
    re.IGNORECASE
)

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

VALID_SOURCES       = {"competitor","ai","hybrid"}
VALID_ARTICLE_TYPES = {"informational","listicle","how-to","comparison","review","commercial","transactional"}

JINA_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)

# ════════════════════════════════════════════════════════════════════
# ANSI colors
# ════════════════════════════════════════════════════════════════════
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def log(msg, color=""):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{color}[{ts}] {msg}{RESET}", flush=True)

# ════════════════════════════════════════════════════════════════════
# LANGUAGE + INTENT
# ════════════════════════════════════════════════════════════════════
def detect_language(kw):
    k = kw.lower()
    score = 3 if VI_MARKERS.search(k) else 0
    score += len(VI_WORDS.findall(k))
    return "vi" if score >= 2 else "en"

def detect_intent_from_modifier(kw):
    scores = {}
    signals = []
    k = kw.lower()
    for pat, intent, boost in INTENT_MODIFIERS:
        if re.search(pat, k):
            scores[intent] = scores.get(intent, 0) + boost
            signals.append(re.sub(r"\\b|\(|\)|\?|\.", "", pat).strip())
    if not scores:
        return {"intent": "informational", "confidence": "low", "signals": []}
    top  = max(scores, key=scores.get)
    conf = "high" if scores[top] >= 3 else "medium" if scores[top] >= 2 else "low"
    return {"intent": top, "confidence": conf, "signals": signals}

def intent_from_serp_titles(serp_results):
    scores = {}
    for r in serp_results:
        title = (r.get("title") or "").lower()
        for pat, intent, _ in INTENT_MODIFIERS:
            if re.search(pat, title):
                scores[intent] = scores.get(intent, 0) + 1
    if not scores:
        return {}
    return {"intent": max(scores, key=scores.get), "counts": scores}

def _intent_h2_default(mod_intent, serp_intent):
    intent = ((mod_intent or {}).get("intent") or
              (serp_intent or {}).get("intent") or "informational")
    return _INTENT_H2_DEFAULTS.get(intent, 6)

# ════════════════════════════════════════════════════════════════════
# SERP
# ════════════════════════════════════════════════════════════════════
def is_blocked(url):
    try:
        host = urlparse(url).netloc.lower().replace("www.", "")
        return any(host == d or host.endswith("." + d) for d in SOCIAL_DOMAINS)
    except Exception:
        return False

def domain_of(url):
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return url

def _raise_dfs_error(resp):
    if resp.status_code == 401:
        raise ValueError("❌ DataForSEO: Invalid credentials (401).")
    if resp.status_code == 402:
        raise ValueError("❌ DataForSEO: Insufficient balance (402).")
    if resp.status_code == 429:
        raise ValueError("❌ DataForSEO: Rate limit (429). Wait and retry.")
    if resp.status_code >= 500:
        raise ValueError(f"❌ DataForSEO: Server error ({resp.status_code}).")
    resp.raise_for_status()
    try:
        task = resp.json()["tasks"][0]
        if task.get("status_code") not in (20000, 20100):
            raise ValueError(f"❌ DataForSEO task error: {task.get('status_message','unknown')}")
    except (KeyError, IndexError, json.JSONDecodeError):
        pass

def fetch_serp(keyword, login, password, location_code, language_code):
    resp = httpx.post(
        "https://api.dataforseo.com/v3/serp/google/organic/live/advanced",
        auth=(login, password),
        json=[{"keyword": keyword, "location_code": location_code,
               "language_code": language_code, "depth": 30}],
        timeout=30,
    )
    _raise_dfs_error(resp)
    results = []
    try:
        for item in resp.json()["tasks"][0]["result"][0]["items"]:
            if item.get("type") != "organic":
                continue
            url = item.get("url", "")
            if not url or is_blocked(url):
                continue
            results.append({
                "rank": item.get("rank_absolute", 99),
                "url": url,
                "title": item.get("title", ""),
                "description": item.get("description", ""),
            })
            if len(results) >= 10:
                break
    except (KeyError, IndexError, TypeError):
        pass
    return results

# ════════════════════════════════════════════════════════════════════
# CRAWL
# ════════════════════════════════════════════════════════════════════
def _dfs_instant_pages(url, login, password, enable_js=True):
    resp = httpx.post(
        "https://api.dataforseo.com/v3/on_page/instant_pages",
        auth=(login, password),
        json=[{"url": url, "enable_javascript": enable_js, "load_resources": False, "custom_js": ""}],
        timeout=45,
    )
    resp.raise_for_status()
    try:
        item  = resp.json()["tasks"][0]["result"][0]["items"][0]
        meta  = item.get("meta", {}) or {}
        htags = meta.get("htags", {}) or {}
        headings = []
        for level in ("h1", "h2", "h3", "h4"):
            for text in (htags.get(level) or []):
                text = (text or "").strip()
                if not text or not (3 <= len(text) <= 250):
                    continue
                if BOILERPLATE_PATTERNS.match(text):
                    continue
                headings.append({"tag": level, "text": text})
        content_meta = meta.get("content", {}) or {}
        wc        = content_meta.get("plain_text_word_count", 0) or 0
        body_text = (content_meta.get("plain_text") or "").strip()
        return {"headings": headings, "word_count": wc, "body_text": body_text,
                "status_code": item.get("status_code", 0)}
    except (KeyError, IndexError, TypeError):
        return {"headings": [], "word_count": 0, "status_code": 0}

def _dfs_content_parsing(url, login, password):
    resp = httpx.post(
        "https://api.dataforseo.com/v3/on_page/content_parsing/live",
        auth=(login, password),
        json=[{"url": url, "markdown_view": False}],
        timeout=40,
    )
    resp.raise_for_status()
    try:
        item = resp.json()["tasks"][0]["result"][0]["items"][0]
        pc   = item.get("page_content", {}) or {}
        headings = []
        for section in (pc.get("main_columns") or []):
            for block in (section.get("content") or []):
                btype = block.get("type", "")
                if btype in ("header", "title"):
                    text = (block.get("text") or block.get("content") or "").strip()
                    try:
                        level = max(1, min(int(block.get("level", 2)), 4))
                    except (TypeError, ValueError):
                        level = 2
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

def _fetch_html(url, timeout):
    with httpx.Client(headers=CRAWL_HEADERS, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        raw = resp.content[:CRAWL_MAX_MB * 1024 * 1024]
        return raw.decode(resp.encoding or "utf-8", errors="replace")

def extract_headings_from_html(html):
    soup = BeautifulSoup(html, BS4_PARSER)
    for tag in soup(["script","style","nav","footer","header","aside","noscript","iframe","form"]):
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

def _fetch_via_jina(url, timeout=22):
    with httpx.Client(headers=JINA_HEADERS, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(JINA_BASE + url)
        resp.raise_for_status()
        return resp.text

def extract_headings_from_markdown(md):
    headings = []
    for m in JINA_HEADING_RE.finditer(md):
        level = len(m.group(1))
        text  = m.group(2).strip()
        text  = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        text  = re.sub(r"\*\*?([^*]+)\*\*?", r"\1", text).strip()
        if not text or not (3 <= len(text) <= 250):
            continue
        if BOILERPLATE_PATTERNS.match(text):
            continue
        headings.append({"tag": f"h{level}", "text": text})
    body_lines = [l for l in md.splitlines() if not l.startswith("#")]
    wc = len(" ".join(body_lines).split())
    return headings, wc

def _extract_body_from_html(html, max_chars=0):
    soup = BeautifulSoup(html, BS4_PARSER)
    for tag in soup(["script","style","nav","footer","header","aside","noscript","iframe","form"]):
        tag.decompose()
    content_el = (
        soup.find("article") or soup.find("main") or
        soup.find(id=re.compile(r"content|main|post|article", re.I)) or
        soup.find(class_=re.compile(r"content|main|post|article|entry", re.I)) or
        soup.body
    )
    paras = []
    for p in (content_el or soup).find_all("p"):
        text = p.get_text(separator=" ", strip=True)
        if len(text) <= 40:
            continue
        if len(text) < 200 and _PARA_BOILERPLATE.search(text):
            continue
        paras.append(text)
    text = "\n\n".join(paras)
    return text[:max_chars] if max_chars else text

def _extract_body_from_jina(md, max_chars=0):
    lines = []
    for l in md.splitlines():
        l = l.strip()
        if not l or l.startswith("#") or len(l) <= 40:
            continue
        if len(l) < 200 and _PARA_BOILERPLATE.search(l):
            continue
        lines.append(l)
    text = "\n\n".join(lines)
    return text[:max_chars] if max_chars else text

def crawl_one(url, t1, t2, use_jina_fallback, dfs_login="", dfs_password=""):
    base   = {"url": url, "headings": [], "word_count": 0, "body_text": "", "error": None, "method": "direct"}
    errors = []
    body_text_l1 = ""

    if dfs_login and dfs_password:
        try:
            result = _dfs_instant_pages(url, dfs_login, dfs_password, enable_js=True)
            body_text_l1 = result.get("body_text", "")
            if result["headings"]:
                return {**base, **result, "status": "dfs", "method": "dfs"}
            errors.append(f"dfs_instant: empty htags (status={result['status_code']})")
        except Exception as e:
            errors.append(f"dfs_instant: {str(e)[:60]}")
        try:
            result2 = _dfs_content_parsing(url, dfs_login, dfs_password)
            if result2["headings"]:
                if not result2.get("body_text") and body_text_l1:
                    result2 = {**result2, "body_text": body_text_l1}
                return {**base, **result2, "status": "dfs", "method": "dfs_content"}
            errors.append("dfs_content: no headings parsed")
        except Exception as e:
            errors.append(f"dfs_content: {str(e)[:60]}")

    try:
        html = _fetch_html(url, t1)
        headings, wc = extract_headings_from_html(html)
        if headings:
            return {**base, "headings": headings, "word_count": wc,
                    "body_text": _extract_body_from_html(html), "status": "ok", "method": "direct"}
    except Exception as e:
        errors.append(f"direct1: {str(e)[:60]}")

    time.sleep(0.3)
    try:
        html = _fetch_html(url, t2)
        headings, wc = extract_headings_from_html(html)
        if headings:
            return {**base, "headings": headings, "word_count": wc,
                    "body_text": _extract_body_from_html(html), "status": "retry_ok", "method": "direct"}
        errors.append("direct2: empty headings")
    except Exception as e:
        errors.append(f"direct2: {str(e)[:60]}")

    if use_jina_fallback:
        try:
            md = _fetch_via_jina(url)
            headings, wc = extract_headings_from_markdown(md)
            if not headings:
                headings, wc = extract_headings_from_html(md)
            if headings:
                return {**base, "headings": headings, "word_count": wc,
                        "body_text": _extract_body_from_jina(md), "status": "jina", "method": "jina"}
            errors.append("jina: no headings")
        except Exception as e:
            errors.append(f"jina: {str(e)[:60]}")

    return {**base, "body_text": body_text_l1, "status": "fail", "error": " | ".join(errors[-3:])}

def crawl_all(serp_results, t1, t2, use_jina, dfs_login="", dfs_password="", on_done=None):
    out = [None] * len(serp_results)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fmap = {
            ex.submit(crawl_one, r["url"], t1, t2, use_jina, dfs_login, dfs_password): i
            for i, r in enumerate(serp_results)
        }
        for f in as_completed(fmap):
            i = fmap[f]
            out[i] = {**serp_results[i], **f.result()}
            if on_done:
                on_done(sum(1 for x in out if x), len(serp_results), out[i])
    return out

def competitor_word_count_stats(crawl_results):
    counts = [r["word_count"] for r in crawl_results if r.get("word_count", 0) > 200]
    if not counts:
        return {}
    med = int(median(counts))
    return {"median": med, "min": min(counts), "max": max(counts),
            "target": int(med * 1.15), "count": len(counts)}

def competitor_h2_stats(crawl_results):
    h2_counts = [
        sum(1 for h in (r.get("headings") or []) if h["tag"] == "h2")
        for r in crawl_results if r.get("headings")
    ]
    if not h2_counts:
        return {}
    avg = round(sum(h2_counts) / len(h2_counts))
    med = int(median(h2_counts))
    return {"avg": avg, "median": med, "min": min(h2_counts), "max": max(h2_counts),
            "target": max(avg, med, 5), "counts": h2_counts}

def _similar(a, b, threshold=0.72):
    a, b = a.lower().strip(), b.lower().strip()
    return a == b or SequenceMatcher(None, a, b).ratio() >= threshold

def _rank_weight(rank):
    if rank <= 2: return 3
    if rank <= 5: return 2
    return 1

def dedup_and_weight_headings(crawl_results):
    all_h = []
    for r in crawl_results:
        rank = r.get("rank", 999)
        for h in (r.get("headings") or []):
            all_h.append((h["tag"], h["text"], domain_of(r["url"]), rank))
    clusters = []
    for tag, text, domain, rank in all_h:
        matched = False
        for c in clusters:
            if c["tag"] == tag and _similar(c["canonical"], text):
                if domain not in c["domains"]:
                    c["domains"].append(domain)
                    c["ranks"].append(rank)
                matched = True; break
        if not matched:
            clusters.append({"tag": tag, "canonical": text, "domains": [domain], "ranks": [rank], "h3s": []})
    for r in crawl_results:
        cur_h2_cluster = None
        for h in (r.get("headings") or []):
            if h["tag"] == "h2":
                cur_h2_cluster = None
                for c in clusters:
                    if c["tag"] == "h2" and _similar(c["canonical"], h["text"]):
                        cur_h2_cluster = c; break
            elif h["tag"] == "h3" and cur_h2_cluster is not None:
                h3_text = h["text"]
                if not any(_similar(existing, h3_text) for existing in cur_h2_cluster["h3s"]):
                    cur_h2_cluster["h3s"].append(h3_text)
    tag_order = {"h1": 0, "h2": 1, "h3": 2, "h4": 3}
    return [
        {"tag": c["tag"], "text": c["canonical"], "freq": len(c["domains"]),
         "weighted_score": sum(_rank_weight(r) for r in c["ranks"]),
         "domains": c["domains"], "h3s": c.get("h3s", [])}
        for c in sorted(clusters, key=lambda x: (tag_order.get(x["tag"], 9), -sum(_rank_weight(r) for r in x["ranks"])))
    ]

def format_headings_for_prompt(deduped, total_crawled):
    return "\n".join(
        f"  [{h['tag'].upper()}] [{h['freq']}/{total_crawled} W:{h.get('weighted_score', h['freq'])}] {h['text']}"
        for h in deduped
    )

# ════════════════════════════════════════════════════════════════════
# JSON VALIDATION
# ════════════════════════════════════════════════════════════════════
def validate_outline(data):
    errors = []
    if not isinstance(data, dict):
        return ["Response is not a JSON object"]
    for field, ftype in {"h1": str, "meta_description": str, "article_type": str, "outline": list}.items():
        if field not in data:
            errors.append(f"Missing required field: '{field}'")
        elif not isinstance(data[field], ftype):
            errors.append(f"Field '{field}' wrong type")
    if "article_type" in data and data["article_type"] not in VALID_ARTICLE_TYPES:
        errors.append(f"Unknown article_type '{data['article_type']}'")
    if "outline" in data and isinstance(data["outline"], list):
        if len(data["outline"]) == 0:
            errors.append("'outline' is empty")
        for i, item in enumerate(data["outline"]):
            if not isinstance(item, dict):
                errors.append(f"outline[{i}] not an object"); continue
            if "h2" not in item or not isinstance(item.get("h2"), str) or not item["h2"].strip():
                errors.append(f"outline[{i}] missing/empty 'h2'")
            if item.get("source") not in VALID_SOURCES:
                item["source"] = "ai"
            if not isinstance(item.get("h3s"), list): item["h3s"] = []
            if not isinstance(item.get("bullets"), list): item["bullets"] = []
    return errors

def fix_outline_data(data):
    data["faq"] = []
    if not isinstance(data.get("unique_angles"), list): data["unique_angles"] = []
    if data.get("article_type") not in VALID_ARTICLE_TYPES:
        data["article_type"] = "informational"
    for item in data.get("outline", []):
        if isinstance(item, dict):
            if item.get("source") not in VALID_SOURCES: item["source"] = "ai"
            if not isinstance(item.get("h3s"), list):    item["h3s"] = []
            if not isinstance(item.get("bullets"), list): item["bullets"] = []
            if item.get("h3s") and item.get("bullets"):  item["bullets"] = []
    return data

# ════════════════════════════════════════════════════════════════════
# CLAUDE API
# ════════════════════════════════════════════════════════════════════
def call_claude_stream(system, user, key, on_chunk=None, max_tokens=6000):
    full = ""; buf = b""; last_call = 0.0
    with httpx.Client(timeout=httpx.Timeout(connect=10, read=120, write=30, pool=5)) as client:
        with client.stream("POST", "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-sonnet-4-6", "max_tokens": max_tokens, "stream": True,
                  "system": system, "messages": [{"role": "user", "content": user}]},
        ) as resp:
            if resp.status_code == 401: raise ValueError("❌ Anthropic: Invalid API key (401).")
            if resp.status_code == 429: raise ValueError("❌ Anthropic: Rate limit (429).")
            if resp.status_code >= 500: raise ValueError(f"❌ Anthropic: Server error ({resp.status_code}).")
            resp.raise_for_status()
            for raw_bytes in resp.iter_bytes(chunk_size=512):
                buf += raw_bytes
                while b"\n" in buf:
                    line_bytes, buf = buf.split(b"\n", 1)
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data: "): continue
                    payload = line[6:]
                    if payload == "[DONE]": break
                    try:
                        evt = json.loads(payload)
                        if evt.get("type") == "content_block_delta":
                            full += evt["delta"].get("text", "")
                            now = time.monotonic()
                            if on_chunk and (now - last_call) >= 0.25:
                                on_chunk(full); last_call = now
                    except (json.JSONDecodeError, KeyError):
                        continue
    if on_chunk and full: on_chunk(full)
    return full

def call_claude_simple(system, user, key, model="claude-haiku-4-5-20251001", max_tokens=800):
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": model, "max_tokens": max_tokens, "system": system,
              "messages": [{"role": "user", "content": user}]},
        timeout=60,
    )
    if resp.status_code == 401: raise ValueError("❌ Anthropic: Invalid API key (401).")
    if resp.status_code == 429: raise ValueError("❌ Anthropic: Rate limit (429).")
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()

def parse_json_response(raw):
    clean = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    clean = re.sub(r"\n?```$", "", clean)
    return json.loads(clean)

# ════════════════════════════════════════════════════════════════════
# BACKGROUND GENERATION
# ════════════════════════════════════════════════════════════════════
def _filter_us_friendly(body_text):
    paragraphs = re.split(r'\n{2,}', body_text.strip())
    kept = []
    for para in paragraphs:
        us_hits     = len(_US_UNITS.findall(para))
        metric_hits = len(_METRIC_ONLY.findall(para))
        if us_hits > 0 or metric_hits == 0:
            kept.append(para)
    return "\n\n".join(kept)

def generate_outline_background(keyword, lang, crawl_results, outline_data, anthropic_key, serp_results=None):
    if not anthropic_key or not outline_data:
        return ""
    sections = [item.get("h2", "") for item in (outline_data.get("outline") or []) if item.get("h2")]
    if not sections:
        return ""

    _BT_CHAR_LIMIT = 15_000
    _BT_MIN_USEFUL = 500

    ranked = sorted(
        [r for r in (crawl_results or []) if len((r.get("body_text") or "")) > 100],
        key=lambda r: (0 if len((r.get("body_text") or "")) >= _BT_MIN_USEFUL else 1, r.get("rank", 999)),
    )
    snippets = []
    for r in ranked:
        bt = (r.get("body_text") or "").strip()
        if lang == "en":
            bt = _filter_us_friendly(bt)
        if len(bt) > 100:
            if len(bt) > _BT_CHAR_LIMIT:
                cut = bt.rfind("\n\n", 0, _BT_CHAR_LIMIT)
                bt  = bt[:cut] if cut > 5000 else bt[:_BT_CHAR_LIMIT]
            snippets.append(f"[Rank {r.get('rank','?')}: {domain_of(r.get('url',''))}]\n{bt}")
        if len(snippets) >= 3:
            break

    serp_descs = []
    for r in (serp_results or []):
        desc = (r.get("description") or "").strip()
        if len(desc) > 30:
            serp_descs.append(f"- [{domain_of(r.get('url',''))}] {desc}")

    if not snippets and not serp_descs:
        return ("[Không có dữ liệu body text]" if lang == "vi"
                else "[No background data available — competitor pages returned no body text]")

    sections_list = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sections))
    lang_name    = "Vietnamese" if lang == "vi" else "English"
    body_section = "\n\n---\n\n".join(snippets) if snippets else "(No full body text crawled)"
    serp_section = "\n".join(serp_descs) if serp_descs else "(No SERP descriptions available)"

    prompt = f"""Topic: "{keyword}"

== ARTICLE H2 SECTIONS (target structure) ==
{sections_list}

== GOOGLE SEARCH SNIPPETS ==
{serp_section}

== FULL BODY TEXT FROM TOP COMPETITOR PAGES ==
{body_section}

---

Task: For each H2 section listed above, extract ONLY the directly relevant factual information from the competitor data above and write 2–4 sentences of facts.

Rules (strictly enforced):
- Write in {lang_name}
- Use ONLY facts explicitly present in the source data above — do NOT add, invent, or infer anything new
- For each section: 2–4 sentences of the most relevant facts. Omit a section entirely if no relevant facts exist for it.
- Plain text only — no bullet points, no markdown, no # headers
- Format: section title on its own line, immediately followed by the facts paragraph
- US MARKET FOCUS (English only): prioritize data in US imperial units. Skip metric-only data points.
- PRIORITY SOURCE: Write primarily from Rank 1. Only pull from Rank 2/3 for facts entirely absent
  in Rank 1 — never to add a second value for the same measurement already stated by Rank 1.
- CONFLICTING DATA: each measurement or number must appear EXACTLY ONCE per section. If sources
  give different values for the same metric, use Rank 1's value only and skip all other values
  for that measurement entirely. Do not write two sentences that state different numbers for the
  same fact.
- SAME-SOURCE DEDUP: even within a single source, do not repeat near-identical measurements
  with slight variations (e.g. "22–28 inches" then "23–28 inches" then "24–28 inches" in the
  same section). Pick the single most specific or most-cited range and state it once only.
"""
    system = ("You are a research assistant. Extract and write only the relevant factual "
              "information from the provided source text. Never invent or add anything not in the source."
              if lang == "en" else
              "Bạn là research assistant. Trích xuất và viết chỉ thông tin thực tế liên quan từ nguồn được cung cấp.")
    try:
        raw   = call_claude_simple(system, prompt, anthropic_key, max_tokens=2000)
        clean = re.sub(r'^#{1,6}\s+.*$', '', raw, flags=re.MULTILINE)
        clean = re.sub(r'^\*\*[^*]+\*\*\s*$', '', clean, flags=re.MULTILINE)
        clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean)
        clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
        return clean
    except Exception:
        return ""

# ════════════════════════════════════════════════════════════════════
# BUILD PROMPT
# ════════════════════════════════════════════════════════════════════
def build_prompt(keyword, lang, mod_intent, serp_intent, serp_results, deduped, crawl_results, wc_stats, h2_stats):
    mod_str   = (f"{mod_intent['intent']} ({mod_intent['confidence']}, "
                 f"signals: {', '.join(mod_intent['signals'][:4]) or 'none'})")
    serp_str  = (f"{serp_intent.get('intent','?')} (from SERP titles)" if serp_intent else "unclear")
    titles_block  = "\n".join(f"  #{r['rank']} {r['title']}" for r in serp_results if r.get("title"))
    total_crawled = sum(1 for r in crawl_results if r.get("headings"))
    headings_block = format_headings_for_prompt(deduped, total_crawled)

    h3_context = ""
    h2s_with_h3s = [h for h in deduped if h["tag"] == "h2" and h.get("h3s")]
    if h2s_with_h3s:
        h3_lines = []
        for h2 in h2s_with_h3s[:20]:
            h3_lines.append(f"  H2: {h2['text']}")
            for h3 in h2["h3s"][:6]:
                h3_lines.append(f"    → H3: {h3}")
        if h3_lines:
            h3_context = "\nH3 THỰC TẾ TỪ COMPETITORS (chỉ những H2 có H3):\n" + "\n".join(h3_lines) + "\n"

    wc_block = (f"Word count: competitor median={wc_stats['median']:,}, target=~{wc_stats['target']:,} words\n"
                if wc_stats else "Word count: no competitor data — use your judgment.\n")
    h2_target = h2_stats.get("target") if h2_stats else _intent_h2_default(mod_intent, serp_intent)
    h2_block  = (f"Competitor H2 count: avg={h2_stats['avg']}, median={h2_stats['median']}, "
                 f"range={h2_stats['min']}–{h2_stats['max']}\nTARGET H2 COUNT = {h2_target} (±1)\n"
                 if h2_stats else
                 f"Competitor H2 count: no data.\nTARGET H2 COUNT = {h2_target} (±1) — estimated from intent.\n")

    return f"""Keyword: "{keyword}"
Language: {lang}
Current year: {CURRENT_YEAR}

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
2. H2 copy: [5+/{total_crawled}] HOẶC W≥8 → COPY NGUYÊN TEXT, source="competitor"
3. H2 paraphrase: [3-4/{total_crawled}] HOẶC W 4–7 → paraphrase nhẹ, source="competitor"
4. H2 rewrite: [1-2/{total_crawled}] HOẶC W≤3 → viết mới, source="hybrid"/"ai"
5. H3: CHỈ điền nếu competitor thực sự có H3 (xem H3 THỰC TẾ bên trên)
6. Không có H3 từ competitor → dùng bullets (3-6 từ/bullet, 3-5 bullets)
7. faq = []
8. Generate EXACTLY {h2_target} H2 sections (±1)
9. All text in {'Vietnamese' if lang=='vi' else 'English'}
10. note = "[X/{total_crawled} competitors, W:score]" cho mỗi H2
11. TRÙNG NGHĨA: rà soát — mỗi heading phải cover 1 góc nhìn độc lập

Return pure JSON only."""

# ════════════════════════════════════════════════════════════════════
# CSV EXPORT
# ════════════════════════════════════════════════════════════════════
def _kw_to_slug(kw):
    slug = re.sub(r"[^a-z0-9\s-]", "", kw.lower())
    return re.sub(r"\s+", "-", slug.strip())[:60]

def _zimm_tag(text, level):
    t = text.lower()
    if any(kw in t for kw in _ZIMM_TABLE_KWS): return "{table}"
    if any(kw in t for kw in _ZIMM_LIST_KWS):  return "{list}"
    return ""

def _classify_bg_quality(background_text, crawl_stats=None):
    words = len((background_text or "").split())
    ok    = (crawl_stats or {}).get("ok", 0)
    total = max((crawl_stats or {}).get("total", 1), 1)
    ratio = ok / total
    if words >= 500 and ratio >= 0.4: return "HIGH"
    if words >= 150:                  return "MEDIUM"
    return "LOW"

def build_csv_row(keyword, data, serp_results, background_text="", lang="en", crawl_stats=None):
    title  = data.get("h1") or keyword
    intent = data.get("search_intent_confirmed", "")
    angles = data.get("unique_angles", [])
    focus_parts  = [p.rstrip(". ") for p in [intent] + angles[:3] if p]
    outline_focus = ". ".join(focus_parts)
    raw_bg       = background_text or "\n".join(r["url"] for r in (serp_results or []) if r.get("url"))[:3]
    background, bg_gaps = _clean_bg_no_data(raw_bg)
    lines = []
    for block in data.get("outline", []):
        h2 = (block.get("h2") or "").strip()
        if h2:
            lines.append(f"{h2}{_zimm_tag(h2, 'h2')}")
        for h3 in (block.get("h3s") or []):
            h3 = h3.strip()
            if h3: lines.append(f"- {h3}{_zimm_tag(h3, 'h3')}")
        for b in (block.get("bullets") or []):
            b = b.strip()
            if b: lines.append(f"- {b}{_zimm_tag(b, 'h3')}")
    outline_text = "\n".join(lines)
    slug         = _kw_to_slug(keyword)
    bg_quality   = _classify_bg_quality(background, crawl_stats)
    return [title, outline_focus, background, outline_text, "", "", slug, bg_quality, bg_gaps]

def append_row(csv_path, row, write_header):
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n")
        if write_header:
            w.writerow(ZIMM_HEADERS)
        w.writerow(row)

# ════════════════════════════════════════════════════════════════════
# SINGLE KEYWORD PIPELINE
# ════════════════════════════════════════════════════════════════════
def run_one(kw, dfs_login, dfs_password, anthropic_key, location_code, serp_lang, use_jina, t1=12, t2=20, on_status=None):
    def _s(msg):
        if on_status: on_status(msg)

    result = {"keyword": kw, "status": "error", "outline": None,
              "serp": [], "background": "", "crawl_stats": {}, "lang": serp_lang}
    try:
        _s("Fetching SERP...")
        serp = fetch_serp(kw, dfs_login, dfs_password, location_code, serp_lang)
        if not serp:
            result["status"] = "no_serp"; return result
        result["serp"] = serp

        lang         = detect_language(kw) or serp_lang
        result["lang"] = lang
        intent_hint  = detect_intent_from_modifier(kw)
        serp_intent  = intent_from_serp_titles(serp)

        _s(f"Crawling {len(serp)} pages...")
        crawl    = crawl_all(serp, t1, t2, use_jina, dfs_login, dfs_password)
        wc_stats = competitor_word_count_stats(crawl)
        h2_stats = competitor_h2_stats(crawl)
        deduped  = dedup_and_weight_headings(crawl)
        result["crawl_stats"] = {
            "ok":    sum(1 for r in crawl if r.get("headings")),
            "total": len(serp),
            "dfs":   sum(1 for r in crawl if r.get("method") in ("dfs", "dfs_content")),
            "jina":  sum(1 for r in crawl if r.get("method") == "jina"),
            "fail":  sum(1 for r in crawl if r.get("status") == "fail"),
        }

        _s("Generating outline (Sonnet)...")
        prompt = build_prompt(kw, lang, intent_hint, serp_intent, serp, deduped, crawl, wc_stats, h2_stats)
        raw    = call_claude_stream(SYSTEM_PROMPT, prompt, anthropic_key, max_tokens=6000)
        data   = parse_json_response(raw)
        errors = validate_outline(data)
        fatal  = [e for e in errors if "Missing" in e or "empty" in e]
        if fatal:
            result["status"] = "ai_error: " + "; ".join(fatal[:2]); return result
        outline_data = fix_outline_data(data)

        _s("Generating background (Haiku)...")
        bg = generate_outline_background(kw, lang, crawl, outline_data, anthropic_key, serp)
        result["outline"]    = outline_data
        result["background"] = bg
        result["status"]     = "done"
        _s("Done")
    except Exception as e:
        result["status"] = f"error: {str(e)[:120]}"
    return result

# ════════════════════════════════════════════════════════════════════
# CLI MAIN
# ════════════════════════════════════════════════════════════════════
def load_keywords(path):
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def load_done_slugs(csv_path):
    done = set()
    if not os.path.exists(csv_path):
        return done
    try:
        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                slug = (row.get("SLUG") or "").strip()
                if slug:
                    done.add(slug)
    except Exception:
        pass
    return done

def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Bulk SEO outline CLI")
    parser.add_argument("keywords_file", help="Keywords file (one per line)")
    parser.add_argument("--market",    default="US", choices=MARKETS.keys())
    parser.add_argument("--batch",     type=int, default=5)
    parser.add_argument("--output",    default="")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--no-jina",   action="store_true")
    args = parser.parse_args()

    dfs_login     = os.getenv("DFS_LOGIN", "")
    dfs_password  = os.getenv("DFS_PASSWORD", "")
    anthropic_key = os.getenv("ANTHROPIC_KEY", "")

    if not dfs_login or not dfs_password:
        print(f"{RED}❌ DFS_LOGIN / DFS_PASSWORD chưa set trong .env{RESET}"); sys.exit(1)
    if not anthropic_key:
        print(f"{RED}❌ ANTHROPIC_KEY chưa set trong .env{RESET}"); sys.exit(1)

    location_code, serp_lang = MARKETS[args.market]
    use_jina = not args.no_jina

    keywords = load_keywords(args.keywords_file)
    if not keywords:
        print(f"{RED}❌ Không tìm thấy keyword trong file{RESET}"); sys.exit(1)

    out_dir  = os.path.join(os.path.dirname(__file__), "output")
    csv_path = args.output or os.path.join(out_dir, f"bulk_cli_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

    done_slugs = set() if args.no_resume else load_done_slugs(csv_path)
    pending    = [kw for kw in keywords if _kw_to_slug(kw) not in done_slugs]
    skipped    = len(keywords) - len(pending)

    log(f"{BOLD}📋 Total: {len(keywords)} | Pending: {len(pending)} | Skipped: {skipped}{RESET}")
    log(f"📁 Output: {csv_path}")
    log(f"🌐 Market: {args.market} | Batch: {args.batch} | Jina: {use_jina}\n")

    if not pending:
        log("✅ Tất cả keywords đã xong. Dùng --no-resume để chạy lại.", GREEN); return

    batches     = [pending[i:i + args.batch] for i in range(0, len(pending), args.batch)]
    file_exists = os.path.exists(csv_path)
    total_done  = 0
    t_start     = time.time()

    for b_idx, batch in enumerate(batches):
        log(f"{BOLD}── Batch {b_idx+1}/{len(batches)}: {', '.join(b[:35] for b in batch)}{RESET}")

        results_map = {}
        with ThreadPoolExecutor(max_workers=len(batch)) as ex:
            fmap = {
                ex.submit(
                    run_one, kw, dfs_login, dfs_password, anthropic_key,
                    location_code, serp_lang, use_jina,
                    on_status=lambda msg, k=kw: log(f"  {k[:38]:<38} {msg}", CYAN),
                ): kw
                for kw in batch
            }
            for f in as_completed(fmap):
                kw = fmap[f]
                try:
                    results_map[kw] = f.result()
                except Exception as e:
                    results_map[kw] = {"keyword": kw, "status": f"error: {e}", "outline": None,
                                       "serp": [], "background": "", "crawl_stats": {}, "lang": serp_lang}

        for kw in batch:
            result = results_map[kw]
            cs     = result.get("crawl_stats", {})
            ok, total = cs.get("ok", 0), max(cs.get("total", 1), 1)
            bg_wc  = len((result.get("background") or "").split())

            if result.get("status") == "done" and result.get("outline"):
                rate = ok / total
                icon = "🟢" if rate >= 0.7 else ("🟡" if rate >= 0.4 else "🔴")
                log(f"✅ {kw[:50]:<50} crawl {icon}{ok}/{total}  bg={bg_wc}w", GREEN)
                row = build_csv_row(kw, result["outline"], result.get("serp", []),
                                    result.get("background", ""), result.get("lang", "en"),
                                    result.get("crawl_stats"))
                append_row(csv_path, row, not file_exists)
                file_exists = True
            else:
                log(f"❌ {kw[:50]:<50} {result['status']}", RED)

        total_done += len(batch)
        elapsed    = time.time() - t_start
        eta        = (len(pending) - total_done) * (elapsed / total_done)
        log(f"Progress: {total_done}/{len(pending)} | Elapsed: {elapsed/60:.1f}m | ETA: {eta/60:.1f}m\n")

    log(f"{BOLD}{GREEN}✅ Xong! {total_done} keywords trong {(time.time()-t_start)/60:.1f} phút{RESET}")
    log(f"📁 {csv_path}", GREEN)

if __name__ == "__main__":
    main()
