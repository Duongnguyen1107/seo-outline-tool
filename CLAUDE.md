# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Single-file Streamlit app (`app.py`, ~1600 lines) for SEO content outline generation. Combines DataForSEO (SERP + crawling) with Claude AI to produce competitor-informed article outlines. Supports Vietnamese and English. Deployed on both Streamlit Cloud and a VPS.

## Running the App

```bash
pip install -r requirements.txt
streamlit run app.py
```

API keys (DataForSEO login/password, Anthropic API key) are entered in the sidebar at runtime — never stored on disk.

## Deployments

**Streamlit Cloud:** `https://vbjmcmdmym3dwr7jsvpsux.streamlit.app`

**VPS (primary):** `https://diymode.work/seo-outline-generator`
- Ubuntu 24.04, CloudPanel, Hostinger — `82.180.163.187`
- App lives at `/home/diymode/seo-outline-tool/`
- Systemd service: `seo-outline` (runs as user `diymode`)
- Nginx proxy config in `/etc/nginx/sites-enabled/diymode.work.conf` using `location ^~ /seo-outline-generator` (the `^~` modifier is critical — prevents the existing static-file regex location from intercepting Streamlit's JS/CSS)

**To update VPS after pushing to GitHub:**
```bash
cd /home/diymode/seo-outline-tool && git pull origin main && systemctl restart seo-outline
```

**GitHub repo:** `https://github.com/Duongnguyen1107/seo-outline-tool`

## Architecture: `app.py` (single file)

### Pipeline — 3 stages

**Stage 1 — SERP Fetch**
`fetch_serp()` calls DataForSEO for top 10 organic results. `intent_from_serp_titles()` confirms search intent. `SOCIAL_DOMAINS` blacklist filters out social/marketplace sites.

**Stage 2 — Competitor Crawling**
`crawl_all()` runs `crawl_one()` in parallel (`MAX_WORKERS=6` threads). Each URL goes through a 4-layer fallback:
1. DataForSEO `instant_pages` — JS-rendered, $0.00025/URL, timeout 45s
2. DataForSEO `content_parsing/live` — cheaper fallback, $0.000125/URL, timeout 40s
3. Direct HTTP + BeautifulSoup — free, fast, Cloudflare-vulnerable
4. Jina Reader (`r.jina.ai`) — free, Cloudflare-friendly last resort

`dedup_and_weight_headings()` merges headings using 72% string similarity, ranking by frequency. `competitor_h2_stats()` enforces a **minimum target of 5 H2 sections** (`max(avg, med, 5)`). `competitor_word_count_stats()` derives word count constraints.

**Stage 3 — AI Outline Generation**
`call_claude_stream()` streams from `claude-sonnet-4-6` with `max_tokens=6000`. `build_prompt()` assembles keyword, intent, SERP titles, deduplicated competitor headings with H3 context, word count range, and H2 count target. The H2 fallback target when crawl fails is `7` (integer), not a string.

Language detection: `detect_language(kw)` auto-detects from keyword characters/words. Both single and bulk modes use auto-detected language — bulk does NOT default to market language.

### UI Tabs

**Tab 1 — Single Keyword**
Full pipeline with live progress, crawl details expander, editable outline (`st.data_editor`), and export options.

**Tab 2 — Bulk**
Paste N keywords (one per line). Configurable parallel batch size (1/2/3/5) via `select_slider`. `run_batch_parallel()` uses `ThreadPoolExecutor` per batch. Progress updates after each batch. Results show status table + download.

### ZimmWriter CSV Export
Both single and bulk export to ZimmWriter Bulk SEO CSV format (Sheet1 layout). Columns filled automatically: ARTICLE TITLE (H1), OUTLINE FOCUS (intent + angles), BACKGROUND (top 3 competitor URLs), OUTLINE (H2 + `- H3` format), SLUG. SEO KEYWORDS and WP CATEGORY left blank for manual input. Files saved to `output/` folder.

### Key Constants & Configuration

| Symbol | Location | Purpose |
|--------|----------|---------|
| `SOCIAL_DOMAINS` | ~line 121 | Blacklist filtering SERP results |
| `BOILERPLATE_PATTERNS` | ~line 130 | Regex to strip nav/footer headings |
| `INTENT_MODIFIERS` | ~line 172 | Keyword patterns for intent detection |
| `MAX_WORKERS` | ~line 163 | Crawl threads per keyword (=6) |
| `CURRENT_YEAR` | ~line 701 | Update annually — used in prompt |
| `SYSTEM_PROMPT` | ~line 703 | Bilingual SEO strategist persona |

### Known Issues in SYSTEM_PROMPT
`SYSTEM_PROMPT` is a regular string (not f-string), so `{CURRENT_YEAR}` on line 723 is sent to Claude as literal text. The `{{` / `}}` in the JSON schema are also literal (not collapsed). These are known bugs with minor impact — Claude still interprets correctly.

### Session State Keys
Single: `serp`, `crawl`, `outline`, `edited_outline`, `wc_stats`, `h2_stats`, `last_kw`, `detected_lang`, `intent_hint`, `deduped`, `serp_intent`, `kw_history`, `running`, `edit_mode`
Bulk: `bulk_running`, `bulk_keywords`, `bulk_results`, `bulk_batch_size`

## Markets Supported

VN (2704/vi), US (2840/en), UK (2826/en), AU (2036/en), SG (2702/en) — each maps to DataForSEO `location_code` + language code.

## Monolithic Design Intent

Single-file structure is deliberate. Do not refactor into packages.

## Bulk Processing Notes

- **Recommended batch size:** 3 (safe for Claude Tier 1 rate limits)
- **Max safe batch size on this VPS:** 5 (2 CPU cores, 3.7GB available RAM)
- **Concurrent load:** batch_size=N means N×6 crawl threads simultaneously
- Each keyword takes ~2–4 min (SERP + crawl 10 pages + AI). Browser must stay open during bulk run.
- `run_single_for_bulk()` is the per-keyword worker (no Streamlit calls inside). `run_batch_parallel()` wraps it in `ThreadPoolExecutor`.
