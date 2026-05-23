# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Single-file Streamlit app (`app.py`, ~1800 lines) for SEO content outline generation. Combines DataForSEO (SERP + crawling) with Claude AI to produce competitor-informed article outlines. Supports Vietnamese and English. Deployed on both Streamlit Cloud and a VPS.

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
- **SSH:** `root@82.180.163.187` port 22, password auth

**To update VPS after pushing to GitHub:**
```bash
cd /home/diymode/seo-outline-tool && git pull origin main && systemctl restart seo-outline
```

**GitHub repo:** `https://github.com/Duongnguyen1107/seo-outline-tool`

## Standard Workflow After Code Changes

After any fix or feature, always: commit → push GitHub → deploy VPS.

```python
# Deploy via Python paramiko (SSH password auth — no key on this machine)
import paramiko, sys
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('82.180.163.187', username='root', password='Duong@11071995', timeout=30)
_, out, err = c.exec_command(
    'cd /home/diymode/seo-outline-tool && git pull origin main '
    '&& systemctl restart seo-outline && systemctl status seo-outline --no-pager'
)
sys.stdout.buffer.write(out.read())
sys.stdout.buffer.write(err.read())
c.close()
```

`sshpass` and `plink` are not available on this machine — always use the paramiko snippet above. Commit messages should follow the existing style (imperative, concise subject + body explaining why).

## Architecture: `app.py` (single file)

### Pipeline — 4 stages

**Stage 1 — SERP Fetch**
`fetch_serp()` calls DataForSEO for top 10 organic results, extracting `rank`, `url`, `title`, `description` (Google snippet). `intent_from_serp_titles()` confirms search intent. `SOCIAL_DOMAINS` blacklist filters out social/marketplace sites.

**Stage 2 — Competitor Crawling**
`crawl_all()` runs `crawl_one()` in parallel (`MAX_WORKERS=6` threads). Each URL goes through a 4-layer fallback, each layer returns both `headings` and `body_text`:
1. DataForSEO `instant_pages` — JS-rendered, $0.00025/URL, returns `meta.htags` + `meta.content.plain_text`
2. DataForSEO `content_parsing/live` — $0.000125/URL, returns `header`/`title` blocks as headings + `paragraph` blocks as body_text
3. Direct HTTP + BeautifulSoup — free; `_extract_body_from_html()` extracts `<p>` tags
4. Jina Reader (`r.jina.ai`) — free, Cloudflare-friendly; `_extract_body_from_jina()` extracts non-heading lines

`dedup_and_weight_headings()` merges headings using 72% string similarity, ranking by frequency. `competitor_h2_stats()` enforces a **minimum target of 5 H2 sections** (`max(avg, med, 5)`). `competitor_word_count_stats()` derives word count constraints.

**Stage 3 — Parallel AI Calls**
Two Claude calls run simultaneously via `ThreadPoolExecutor`:

- **Sonnet** (`claude-sonnet-4-6`, `max_tokens=6000`): `call_claude_stream()` streams the SEO outline. Uses raw `httpx` SSE — the `anthropic` SDK is **not** used. `build_prompt()` assembles keyword, intent, SERP titles, deduplicated headings with H3 context, word count range, H2 target, and a semantic dedup instruction (#11).

- **Haiku** (`claude-haiku-4-5-20251001`): `call_claude_simple()` (non-streaming) + `generate_background_text()` distills real facts from competitor `body_text` + SERP `description` fields into 400–900 word background text for ZimmWriter. Strictly no hallucination — returns a note if no body text was crawled. Before sending to Haiku, `_filter_us_friendly()` strips metric-only paragraphs (no imperial equivalent) from English crawls to remove non-US market noise. Prompt enforces: CONFLICTING DATA rule (true conflict = same subject+measurement+context, pick Rank 1 value); US MARKET FOCUS rule (imperial first, skip metric-only data points).

Single mode: Haiku runs in background thread while Sonnet streams on main thread. Bulk mode: both submitted to `ThreadPoolExecutor(max_workers=2)` simultaneously.

`validate_outline_data()` checks JSON structure; `fix_outline_data()` auto-corrects (clears FAQ, resolves h3s/bullets conflicts — h3s wins).

Language detection: `detect_language(kw)` auto-detects from keyword. Both single and bulk use auto-detected language.

**Stage 4 — ZimmWriter CSV Export**
`_outline_to_zimmwriter_row()` builds one CSV row. BACKGROUND column uses Haiku-generated text if available, falls back to top 3 competitor URLs. CSV downloads encoded as `utf-8-sig` (BOM) for Excel compatibility. Files saved to `output/` folder.

### UI Tabs

**Tab 1 — Single Keyword**
Full pipeline with live progress, crawl details expander, editable outline (`st.data_editor`), and export options.

**Tab 2 — Bulk**
Paste N keywords (one per line). Configurable parallel batch size (1/2/3/5) via `select_slider`. `run_batch_parallel()` uses `ThreadPoolExecutor` per batch. `run_single_for_bulk()` is the per-keyword worker (no Streamlit calls inside).

### Key Constants & Configuration

| Symbol | Line | Purpose |
|--------|------|---------|
| `SOCIAL_DOMAINS` | ~124 | Blacklist: social, forums, retail, review sites — content-only crawl |
| `_filter_us_friendly()` | ~776 | Pre-Haiku filter: drops metric-only paragraphs from EN body_text |
| `_US_UNITS` / `_METRIC_ONLY` | ~762 | Regex patterns used by `_filter_us_friendly()` |
| `BOILERPLATE_PATTERNS` | ~133 | Regex to strip nav/footer headings |
| `MAX_WORKERS` | 163 | Crawl threads per keyword (=6) |
| `CRAWL_MAX_MB` | 164 | Max response size per crawled page (=3 MB) |
| `INTENT_MODIFIERS` | ~175 | Keyword patterns for intent detection |
| `CURRENT_YEAR` | 833 | Update annually — used in prompt |
| `SYSTEM_PROMPT` | 835 | Bilingual SEO strategist persona |

### SYSTEM_PROMPT Rules (critical)
`SYSTEM_PROMPT` is a regular string (not f-string), so `{CURRENT_YEAR}` is sent as literal text — known issue, minor impact. Key rules:
- **Rule 1**: H2 frequency thresholds (copy verbatim at 5+/N, paraphrase at 3-4/N, rewrite at 1-2/N). Always strip numbered/lettered prefixes from competitor headings (e.g. `"2. Deep Dive:"` → `"Deep Dive:"`).
- **Rule 3**: Semantic dedup — H2 vs H2, H3 vs parent H2, H3 vs H3 must each cover distinct angles.
- **Rule 4**: FAQ always empty.

### Background Generation Rules (Haiku prompt)
- **CONFLICTING DATA**: true conflict = same subject + measurement + context. Pick Rank 1 value; never list both side by side.
- **US MARKET FOCUS**: imperial units first; skip metric-only data points (non-US market noise). Only applies to English.
- **OUTLINE FOCUS field**: parts joined with `". "` — each part must have trailing `.` stripped first (`p.rstrip(". ")`) to avoid double periods.

### Session State Keys
Single: `serp`, `crawl`, `outline`, `edited_outline`, `wc_stats`, `h2_stats`, `last_kw`, `detected_lang`, `intent_hint`, `deduped`, `serp_intent`, `kw_history`, `running`, `edit_mode`, `background_text`
Bulk: `bulk_running`, `bulk_keywords`, `bulk_results`, `bulk_batch_size`

## Markets Supported

VN (2704/vi), US (2840/en), UK (2826/en), AU (2036/en), SG (2702/en) — each maps to DataForSEO `location_code` + language code.

## Monolithic Design Intent

Single-file structure is deliberate. Do not refactor into packages.

## Bulk Processing Notes

- **Recommended batch size:** 3 (safe for Claude Tier 1 rate limits)
- **Max safe batch size on this VPS:** 5 (2 CPU cores, 3.7GB available RAM)
- **Concurrent load:** batch_size=N means N×6 crawl threads + N×2 Claude calls simultaneously
- Each keyword takes ~2–4 min. Browser must stay open during bulk run.
