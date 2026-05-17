"""
edgar_risk_factors.py  —  Supply Chain Risk Data Extraction
─────────────────────────────────────────────────────────────────────
Fetches the most recent 10-K filing for each space company from SEC EDGAR
and extracts the 'Risk Factors' section as plain text.


Usage:
    pip install requests beautifulsoup4 lxml
    python edgar_risk_factors.py

Output:
    ./risk_factors/<TICKER>_risk_factors.txt   one file per company
    ./risk_factors/_manifest.json              run summary
"""

import json
import re
import time
import logging
import warnings
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration  ←  make sure your real name/email is in User-Agent
# ─────────────────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("risk_factors")
OUTPUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "YOUR_NAME YOUR_EMAIL",  # ← keep your details here
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json, text/html, application/xhtml+xml",
}

REQUEST_DELAY = 0.2   # seconds between requests  (SEC limit: 10 req/s)
FILING_DELAY  = 1.2   # extra pause between companies

SPACE_COMPANIES = [
    ("Rocket Lab USA",         "RKLB"),
    ("Intuitive Machines",     "LUNR"),
    ("Redwire Corporation",    "RDW"),
    ("Virgin Galactic",        "SPCE"),
    ("Planet Labs",            "PL"),
    ("Spire Global",           "SPIR"),
    ("Momentus",               "MNTS"),
    ("Lockheed Martin",        "LMT"),
    ("Northrop Grumman",       "NOC"),
    ("L3Harris Technologies",  "LHX"),
    ("Boeing",                 "BA"),
    ("Raytheon Technologies",  "RTX"),
    # Formerly public — last 10-K still on EDGAR, CIK resolved by name
    ("Aerojet Rocketdyne",     "AJRD"),
    ("Maxar Technologies",     "MAXR"),
    ("Mynaric AG",             "MYNA"),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# EDGAR helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_cik_by_ticker(ticker: str) -> str | None:
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers=HEADERS, timeout=15)
        r.raise_for_status()
        for entry in r.json().values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                log.info("  CIK for %s → %s (ticker)", ticker, cik)
                return cik
    except Exception as e:
        log.warning("  Ticker lookup failed: %s", e)
    return None


def get_cik_by_name(name: str) -> str | None:
    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar?company={}"
        "&CIK=&type=10-K&dateb=&owner=include&count=5"
        "&search_text=&action=getcompany&output=atom"
    ).format(requests.utils.quote(name))
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        entry = soup.find("entry")
        if entry:
            cik_tag = entry.find("cik")
            if cik_tag:
                cik = str(cik_tag.text).zfill(10)
                log.info("  CIK for '%s' → %s (name search)", name, cik)
                return cik
    except Exception as e:
        log.warning("  Name search failed: %s", e)
    return None


def get_cik(ticker: str, name: str) -> str | None:
    cik = get_cik_by_ticker(ticker)
    if not cik:
        log.info("  '%s' not in active tickers, trying name search...", ticker)
        cik = get_cik_by_name(name)
    return cik


def get_latest_10k_filing(cik: str) -> dict | None:
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error("  Submissions fetch failed: %s", e)
        return None

    f = data.get("filings", {}).get("recent", {})
    for i, form in enumerate(f.get("form", [])):
        if form in ("10-K", "10-K/A"):
            acc = f["accessionNumber"][i].replace("-", "")
            return {
                "accession_number": f["accessionNumber"][i],
                "filing_date":      f["filingDate"][i],
                "doc_url": (
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{acc}/{f['primaryDocument'][i]}"
                ),
                "cik": cik,
            }
    return None


def fetch_url(url: str) -> str | None:
    try:
        time.sleep(REQUEST_DELAY)
        r = requests.get(url, headers=HEADERS, timeout=60)
        r.raise_for_status()
        return r.text
    except Exception as e:
        log.error("  Fetch failed: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# HTML → plain text  (handles iXBRL inline tags)
# ─────────────────────────────────────────────────────────────────────────────

_XBRL_RE = re.compile(
    r"</?(?:ix:[A-Za-z]+|xbrli:[A-Za-z]+|link:[A-Za-z]+)[^>]*?>",
    re.I | re.S,
)

def html_to_plain_text(html: str) -> str:
    html = _XBRL_RE.sub("", html)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "meta", "link",
                     "footer", "nav", "iframe", "noscript"]):
        tag.decompose()
    for tag in soup.find_all(style=re.compile(r"display\s*:\s*none", re.I)):
        tag.decompose()

    # Use whole-body get_text with newline separator — simpler and more reliable
    # than leaf-node walking, and preserves the document order.
    body = soup.find("body") or soup
    raw = body.get_text(separator="\n")

    # Normalise whitespace
    raw = raw.replace("\xa0", " ").replace("\u200b", "")
    raw = re.sub(r"[ \t]{2,}", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Risk Factors extraction
# ─────────────────────────────────────────────────────────────────────────────


_RF_START = re.compile(
    r"item\s*1\s*a\b[.\-\u2013\u2014]?\s*[:\-\u2013\u2014]?\s*risk\s+factors",
    re.I,
)

_RF_END = re.compile(
    r"item\s*1\s*b\b"           # Item 1B — Unresolved Staff Comments
    r"|item\s*2\b"              # Item 2  — Properties
    r"|item\s*3\b",             # Item 3  — Legal Proceedings (fallback)
    re.I,
)

MIN_RF_CHARS = 3000   


def extract_risk_factors(plain_text: str) -> str:
    """
    Find every 'Item 1A – Risk Factors' occurrence, extract the text up to
    the next major Item heading, and return the longest candidate.
    The longest candidate is always the real section (not the TOC entry).
    """
    candidates = []

    for m_start in _RF_START.finditer(plain_text):
        search_from = m_start.end()
        m_end = _RF_END.search(plain_text, search_from)
        end_idx = m_end.start() if m_end else len(plain_text)
        section = plain_text[m_start.start():end_idx].strip()
        candidates.append(section)

    if not candidates:
        return ""

    best = max(candidates, key=len)
    log.info("  Found %d Item 1A occurrence(s); longest candidate: %d chars",
             len(candidates), len(best))
    return best if len(best) >= MIN_RF_CHARS else ""


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def process_company(name: str, ticker: str) -> dict:
    log.info("━━━ %s (%s) ━━━", name, ticker)
    result = {
        "company": name, "ticker": ticker, "status": "failed",
        "filing_date": None, "accession_number": None, "doc_url": None,
        "output_file": None, "risk_factors_chars": 0, "error": None,
    }

    cik = get_cik(ticker, name)
    if not cik:
        result["error"] = "CIK not found"
        return result
    time.sleep(REQUEST_DELAY)

    filing = get_latest_10k_filing(cik)
    if not filing:
        result["error"] = "No 10-K filing found"
        return result

    result.update({
        "filing_date":      filing["filing_date"],
        "accession_number": filing["accession_number"],
        "doc_url":          filing["doc_url"],
    })
    log.info("  10-K dated %s  →  %s", filing["filing_date"], filing["doc_url"])

    html = fetch_url(filing["doc_url"])
    if not html:
        result["error"] = "Could not download filing"
        return result

    log.info("  Parsing document (%d KB)...", len(html) // 1024)
    plain_text = html_to_plain_text(html)
    log.info("  Plain text: %d chars", len(plain_text))

    if len(plain_text) < 5000:
        result["error"] = "Document parsed to almost no text"
        return result

    risk_text = extract_risk_factors(plain_text)
    if not risk_text:
        result["error"] = "Risk Factors section not found or too short"
        log.warning("  ⚠ Extraction failed for %s", name)
        # Save a 30k debug snapshot around the 'item 1a' area for diagnosis
        m = _RF_START.search(plain_text)
        if m:
            snippet = plain_text[max(0, m.start()-200): m.start()+2000]
            debug_note = f"[Item 1A found at char {m.start()} — showing ±context]\n\n" + snippet
        else:
            debug_note = plain_text[:30000]
        safe = re.sub(r"[^A-Za-z0-9_]", "_", ticker)
        (OUTPUT_DIR / f"{safe}_DEBUG.txt").write_text(debug_note, encoding="utf-8")
        return result

    safe = re.sub(r"[^A-Za-z0-9_]", "_", ticker)
    out_path = OUTPUT_DIR / f"{safe}_risk_factors.txt"
    header = (
        f"Company:          {name}\n"
        f"Ticker:           {ticker}\n"
        f"CIK:              {cik}\n"
        f"Accession Number: {filing['accession_number']}\n"
        f"Filing Date:      {filing['filing_date']}\n"
        f"Source URL:       {filing['doc_url']}\n"
        f"Extracted:        {datetime.utcnow().isoformat()}Z\n"
        + "─" * 72 + "\n\n"
    )
    out_path.write_text(header + risk_text, encoding="utf-8")
    result.update({
        "status": "ok",
        "output_file": str(out_path),
        "risk_factors_chars": len(risk_text),
    })
    log.info("  ✓ Saved %d chars → %s", len(risk_text), out_path)
    return result


def main():
    log.info("Phase 1 – SEC EDGAR 10-K Risk Factors Extraction")
    log.info("Output directory: %s", OUTPUT_DIR.resolve())

    manifest = []
    for name, ticker in SPACE_COMPANIES:
        entry = process_company(name, ticker)
        manifest.append(entry)
        time.sleep(FILING_DELAY)

    manifest_path = OUTPUT_DIR / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    ok    = [e for e in manifest if e["status"] == "ok"]
    fails = [e for e in manifest if e["status"] != "ok"]
    log.info("\n%s", "═" * 60)
    log.info("Done.  ✓ %d succeeded  ✗ %d failed", len(ok), len(fails))
    for e in fails:
        log.warning("  FAILED: %s (%s) – %s", e["company"], e["ticker"], e["error"])
    log.info("Manifest → %s", manifest_path)


if __name__ == "__main__":
    main()
