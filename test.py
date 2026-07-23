import os
import re
import time
import json
from typing import List, Dict
import requests
from dotenv import load_dotenv

load_dotenv()

SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")
BASE_URL = "https://africanfinancials.com"


def scraperapi_get(url: str, render: bool = False) -> str:
    payload = {
        "api_key": SCRAPER_API_KEY,
        "url": url,
        "keep_headers": "true",
        "country_code": "us",
        "render": "true" if render else "false",
    }
    resp = requests.get("https://api.scraperapi.com/", params=payload, timeout=60)
    resp.raise_for_status()
    return resp.text


def extract_clean_text(html: str) -> str:
    """
    Extract clean LLM-ready text from AfricanFinancials HTML.
    FIXED: Uses body extraction + tag stripping instead of broken regex selectors.
    """
    # 1. Remove scripts, styles, nav, footer, header, aside
    for tag in ["script", "style", "nav", "footer", "header", "aside"]:
        html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", html, flags=re.DOTALL | re.IGNORECASE)

    # 2. Extract body content (the actual page content is in the body)
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    content = body_match.group(1) if body_match else html

    # 3. Strip all remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", content)

    # 4. Decode HTML entities
    for old, new in [
        ("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&quot;", '"'), ("&#39;", "'"), ("&#8217;", "'"), ("&#8211;", "–"),
        ("&#8212;", "—"), ("&#8220;", '"'), ("&#8221;", '"'), ("&#8230;", "..."),
        ("&#8243;", '"'), ("&#x27;", "'"), ("&rsquo;", "'"), ("&lsquo;", "'"),
        ("&rdquo;", '"'), ("&ldquo;", '"'), ("&ndash;", "–"), ("&mdash;", "—"),
        ("&#8216;", "'"), ("&#8242;", "'"),
    ]:
        text = text.replace(old, new)

    # 5. Collapse whitespace
    text = re.sub(r"\s+", " ", text)

    # 6. Split into sentences and filter junk
    sentences = re.split(r'(?<=[.!?])\s+', text)
    cleaned = []
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 15:
            continue
        low = sent.lower()
        # Skip CSS/JS junk, nav elements, and font definitions
        if any(junk in low for junk in [
            "cloudflare", "access denied", "performance & security",
            "cookie policy", "privacy policy", "all rights reserved",
            "enable javascript", "captcha", "challenge platform",
            "fusion-fullwidth", "fusion-builder-row", "data-orig-src",
            "lazyload", "img-responsive", "decoding=", "base64",
            "var ", "function(", "window.", "document.", "jquery",
            "click to share", "share on", "tweet this", "email this",
            "avada", "wp-embed", "wp-content", "font-family:",
            "@font-face", "unicode-range", "src: url", "woff2",
            "toggle navigation", "search toggle", "advertise alerts",
            "skip to content", "font-display", "speak: never",
            'content: "', "linear-gradient", "box-shadow",
            "transition:", "transform:", "flex-direction",
            "align-items:", "justify-content", "max-width:",
            "padding:", "margin:", "border:", "background:",
            "display:", "position:", "z-index:", "opacity:",
            "width:", "height:", "color:", "font-size:",
            "line-height:", "text-align", "vertical-align",
            "pointer-events", "overflow:", "visibility:",
            "keyframes", "animation:", "media only screen",
            "min-device-width", "max-device-width",
        ]):
            continue
        # Skip font/CSS class names (all lowercase no spaces, often with dashes)
        if " " not in sent and "-" in sent and sent.islower():
            continue
        cleaned.append(sent)

    return " ".join(cleaned)


def get_company_reports(company_slug: str, year: int = 2025) -> List[Dict]:
    """
    Fetch all report types for a given company slug and year.

    Args:
        company_slug: URL slug, e.g. 'gtco', 'oando', 'zenithbank'
        year: Report year. Pass 2025 or 2026.

    Returns:
        List of dicts with clean text content
    """
    doc_types = {
        "ar": "Annual Report",
        "ab": "Abridged Report",
        # "ir-hy": "Half-Year Interim",
        # "ir-q1": "Q1 Interim",
        # "ir-q2": "Q2 Interim",
        # "ir-q3": "Q3 Interim",
        "pr": "Presentation",
    }

    reports = []

    for doc_code, doc_name in doc_types.items():
        url = f"{BASE_URL}/document/ng-{company_slug}-{year}-{doc_code}-00/"
        print(f"[TRY] {doc_name}: {url}")

        try:
            html = scraperapi_get(url, render=False)

            # Validation
            if len(html) < 1000:
                print("  SKIP: Empty response")
                continue
            if "Cloudflare" in html and len(html) < 15000:
                print("  SKIP: Cloudflare block")
                continue

            title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
            page_title = title_match.group(1).strip() if title_match else ""

            # Extract clean text
            content = extract_clean_text(html)

            if len(content) < 200:
                print(f"  SKIP: Too little content ({len(content)} chars)")
                continue

            reports.append({
                "title": page_title or f"ng-{company_slug}-{year}-{doc_code}-00",
                "url": url,
                "year": year,
                "doc_type": doc_name,
                "doc_code": doc_code,
                "content": content,
                "word_count": len(content.split()),
            })
            print(f"  SUCCESS: {len(content.split())} words")

        except requests.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            if status == 404:
                print("  404 (not found)")
            else:
                print(f"  HTTP {status}: {e}")
        except Exception as e:
            print(f"  ERROR: {e}")

        time.sleep(1.5)

    return reports


def save_for_llm(reports: List[Dict], company_slug: str, year: int):
    """Export to JSONL (chunked) and plain text."""
    base = f"{company_slug}_{year}"

    # JSONL — one JSON object per line, chunked for context windows
    with open(f"{base}.jsonl", "w", encoding="utf-8") as f:
        for r in reports:
            words = r["content"].split()
            chunk_size = 1000
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i:i+chunk_size])
                doc = {
                    "title": r["title"],
                    "company": company_slug.upper(),
                    "year": r["year"],
                    "doc_type": r["doc_type"],
                    "url": r["url"],
                    "chunk_index": i // chunk_size,
                    "text": chunk,
                }
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    # Plain text
    with open(f"{base}.txt", "w", encoding="utf-8") as f:
        for r in reports:
            f.write(f"\n\n{'='*60}\n")
            f.write(f"TITLE: {r['title']}\n")
            f.write(f"YEAR: {r['year']} | TYPE: {r['doc_type']}\n")
            f.write(f"URL: {r['url']}\n")
            f.write(f"{'='*60}\n\n")
            f.write(r["content"])

    print(f"[SAVED] {base}.jsonl and {base}.txt")


# ==================== USAGE ====================

if __name__ == "__main__":
    # Example: Get Wemaba 2025 reports
    reports = get_company_reports("wemaba", year=2025)

    if reports:
        save_for_llm(reports, "wemaba", 2025)
        print(f"\nFetched {len(reports)} reports:")
        for r in reports:
            print(f"  - {r['doc_type']}: {r['word_count']} words")
    else:
        print("\nNo reports fetched.")