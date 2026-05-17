"""
build_risk_table.py
───────────────────
Master Supply Chain Risk Table Builder

Reads Risk Factors plain-text files produced by (edgar_risk_factors.py),
applies keyword tagging across six risk categories, scores each match by severity,
and writes a master CSV ready for pivot-table analysis or further NLP work.

Schema (one row per keyword hit):
  company            – Company display name
  ticker             – Stock ticker
  filing_year        – Fiscal year of the 10-K
  filing_date        – Full filing date (YYYY-MM-DD)
  risk_category      – Top-level category (e.g. "Supplier Concentration")
  risk_subcategory   – Specific tag (e.g. "Single-Source")
  keyword_matched    – The exact keyword phrase that triggered this row
  evidence_sentence  – The sentence containing the keyword (cleaned)
  keyword_count      – How many times this keyword appears in the full filing
  severity_score     – 1–5 auto-estimated from keyword density + amplifier words
  severity_rationale – Brief explanation of the score
  source_file        – Source .txt filename
  analyst_notes      – Blank column for manual annotation

Usage:
    pip install requests beautifulsoup4 lxml   
    python build_risk_table.py

Input:  ./risk_factors/*_risk_factors.txt
Output: ./risk_factors/master_risk_table.csv
        ./risk_factors/tagging_summary.json
"""

import csv
import json
import re
import os
import logging
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

INPUT_DIR  = Path("risk_factors")
OUTPUT_CSV  = INPUT_DIR / "master_risk_table.csv"
OUTPUT_JSON = INPUT_DIR / "tagging_summary.json"

# Maximum evidence sentences to keep per (company × keyword) pair.
# Set to None to keep all matches.
MAX_SENTENCES_PER_KEYWORD = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Keyword taxonomy
#
# Structure:
#   risk_category → risk_subcategory → [keyword patterns]
#
# Patterns are compiled as whole-word, case-insensitive regex.
# Add or edit keywords freely — they drive everything downstream.
# ─────────────────────────────────────────────────────────────────────────────

KEYWORD_TAXONOMY = {

    "Supplier Concentration": {
        "Single-Source": [
            "single.?source",
            "single source",
            "sole.?source",
            "sole source",
            "only source",
            "one source",
            "single supplier",
            "one supplier",
        ],
        "Sole-Source": [
            "sole supplier",
            "sole provider",
            "only supplier",
            "only vendor",
            "single vendor",
            "exclusive supplier",
            "exclusive provider",
        ],
        "Limited Supplier": [
            "limited supplier",
            "limited number of supplier",
            "few supplier",
            "limited source",
            "limited vendor",
            "limited availability",
            "scarce supplier",
            "constrained supply base",
            "supply base",
            "limited qualified supplier",
            "qualified supplier",
        ],
        "Supplier Dependency": [
            "heavily dependent on supplier",
            "dependent on (a |one |single )?(third.party|supplier|vendor|subcontractor)",
            "reliance on supplier",
            "reliance on subcontractor",
            "critical supplier",
            "key supplier",
            "preferred supplier",
            "strategic supplier",
            "subcontractor performance",
            "supplier failure",
            "supplier default",
        ],
    },

    "Geopolitical Risk": {
        "Geopolitical": [
            "geopolit",
            "political instability",
            "political risk",
            "political uncertainty",
            "political tension",
            "political conflict",
            "civil unrest",
            "armed conflict",
            "military conflict",
            "war",
            "invasion",
            "sanctions",
            "trade war",
            "trade tension",
            "trade dispute",
            "tariff",
            "counter.tariff",
            "retaliatory tariff",
        ],
        "Country Risk": [
            "china",
            "russia",
            "iran",
            "north korea",
            "foreign adversar",
            "hostile nation",
            "adversarial nation",
            "state.sponsored",
            "nation.state",
        ],
        "Supply Chain Disruption": [
            "supply chain disruption",
            "supply disruption",
            "supply chain vulnerab",
            "supply chain risk",
            "supply chain resilien",
            "supply chain concentrat",
            "supply chain diversif",
            "logistics disruption",
            "shipping disruption",
            "port disruption",
            "transportation disruption",
        ],
    },

    "Export Control & Regulatory": {
        "Export Control": [
            "export control",
            "ITAR",
            "EAR",
            "Export Administration Regulation",
            "International Traffic in Arms",
            "deemed export",
            "export license",
            "export restriction",
            "export compliance",
            "export violation",
        ],
        "Trade Restriction": [
            "trade restriction",
            "trade embargo",
            "trade sanction",
            "import restriction",
            "import ban",
            "import tariff",
            "customs restriction",
            "embargoed countr",
            "denied party",
            "restricted party",
            "blacklist",
            "entity list",
        ],
        "Regulatory Compliance": [
            "regulatory compliance",
            "compliance failure",
            "regulatory risk",
            "regulatory change",
            "regulatory uncertainty",
            "government regulation",
            "compliance cost",
            "debarment",
            "suspension",
            "regulatory penalt",
        ],
    },

    "Material & Component Shortage": {
        "Material Shortage": [
            "material shortage",
            "raw material",
            "component shortage",
            "parts shortage",
            "supply shortage",
            "shortage of material",
            "shortage of component",
            "shortage of part",
            "availability of material",
            "material availab",
            "critical material",
        ],
        "Rare / Strategic Material": [
            "rare earth",
            "rare.earth element",
            "critical mineral",
            "strategic material",
            "strategic mineral",
            "precious metal",
            "titanium",
            "lithium",
            "cobalt",
            "nickel",
            "tungsten",
            "beryllium",
            "specialty chemical",
            "specialty alloy",
            "specialty metal",
        ],
        "Semiconductor / Electronics": [
            "semiconductor",
            "microchip",
            "chip shortage",
            "electronic component",
            "integrated circuit",
            "printed circuit",
            "microelectronic",
            "FPGA",
            "electronic part",
        ],
        "Inflation / Cost Pressure": [
            "inflation",
            "cost increase",
            "cost overrun",
            "price increase",
            "escalating cost",
            "rising cost",
            "material cost",
            "commodity price",
            "commodity cost",
            "input cost",
        ],
    },

    "Manufacturing & Production Risk": {
        "Production Capacity": [
            "production capacity",
            "manufacturing capacity",
            "capacity constraint",
            "capacity limitation",
            "production bottleneck",
            "production delay",
            "manufacturing delay",
            "delivery delay",
            "schedule delay",
            "production risk",
        ],
        "Quality / Defect": [
            "quality failure",
            "quality defect",
            "defective part",
            "defective component",
            "quality control",
            "quality assurance",
            "product defect",
            "manufacturing defect",
            "non.conforming",
            "non.conformance",
        ],
        "Workforce / Labor": [
            "labor shortage",
            "workforce shortage",
            "skilled labor",
            "talent shortage",
            "workforce risk",
            "labor dispute",
            "work stoppage",
            "strike",
            "union",
            "employee retention",
            "attrition",
        ],
    },

    "Technology & Cyber Risk": {
        "Cybersecurity": [
            "cybersecurity",
            "cyber attack",
            "cyber threat",
            "cyber incident",
            "cyber risk",
            "data breach",
            "ransomware",
            "malware",
            "hacking",
            "unauthorized access",
            "information security",
        ],
        "Technology Dependency": [
            "technology dependency",
            "proprietary technology",
            "technology obsolescence",
            "legacy system",
            "software failure",
            "IT system failure",
            "system outage",
            "software vulnerability",
        ],
        "Intellectual Property": [
            "intellectual property",
            "IP theft",
            "trade secret",
            "patent infringement",
            "technology transfer",
            "reverse engineering",
            "counterfeit",
            "counterfeit part",
            "counterfeit component",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Severity scoring
# ─────────────────────────────────────────────────────────────────────────────

# Words that amplify severity when found near a keyword hit
AMPLIFIERS = [
    "significant", "material", "severe", "critical", "substantial",
    "major", "serious", "adverse", "adversely", "principal", "primary",
    "key", "fundamental", "existential", "catastrophic", "disruption",
    "failure", "shortage", "unable", "inability", "loss", "penalty",
    "termination", "breach", "violation", "sanction",
]

# Words that dampen severity
DAMPENERS = [
    "historically", "not material", "not significant", "not expected",
    "unlikely", "mitigated", "remediated", "managed", "monitored",
    "compliance", "compliant", "immaterial", "minor",
]

_AMP_RE  = re.compile(r"\b(" + "|".join(AMPLIFIERS) + r")\b", re.I)
_DAMP_RE = re.compile(r"\b(" + "|".join(DAMPENERS) + r")\b", re.I)


def score_severity(sentence: str, keyword_count: int, total_keywords: int) -> tuple[int, str]:
    """
    Return (score 1-5, rationale string).

    Scoring logic:
      Base score driven by keyword frequency in the filing.
      Amplifier words in the evidence sentence push score up.
      Dampener words push score down.
    """
    # Base from frequency (how often the risk is mentioned across the filing)
    if total_keywords >= 20:
        base = 5
    elif total_keywords >= 10:
        base = 4
    elif total_keywords >= 5:
        base = 3
    elif total_keywords >= 2:
        base = 2
    else:
        base = 1

    amps  = len(_AMP_RE.findall(sentence))
    damps = len(_DAMP_RE.findall(sentence))

    score = base + min(amps, 2) - min(damps, 2)
    score = max(1, min(5, score))

    rationale = (
        f"base={base} (filing mentions={total_keywords}); "
        f"amplifiers={amps}; dampeners={damps}"
    )
    return score, rationale


# ─────────────────────────────────────────────────────────────────────────────
# Text helpers
# ─────────────────────────────────────────────────────────────────────────────

# Sentence splitter — splits on period/!/?  followed by whitespace + capital
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z•])")


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, cleaning up noise."""
    sentences = _SENT_SPLIT.split(text)
    cleaned = []
    for s in sentences:
        s = s.strip()
        s = re.sub(r"\s+", " ", s)
        # Skip very short fragments (likely headers or page numbers)
        if len(s) > 40:
            cleaned.append(s)
    return cleaned


def parse_header(text: str) -> dict:
    """
    Extract metadata from the header block written by Phase 1.
    Returns dict with company, ticker, filing_date, filing_year.
    """
    meta = {}
    patterns = {
        "company":      r"^Company:\s+(.+)$",
        "ticker":       r"^Ticker:\s+(.+)$",
        "filing_date":  r"^Filing Date:\s+(.+)$",
        "accession":    r"^Accession Number:\s+(.+)$",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.M)
        if m:
            meta[key] = m.group(1).strip()

    # Derive filing year from date
    if "filing_date" in meta:
        meta["filing_year"] = meta["filing_date"][:4]
    else:
        meta["filing_year"] = "Unknown"

    return meta


# ─────────────────────────────────────────────────────────────────────────────
# Compile keyword patterns
# ─────────────────────────────────────────────────────────────────────────────

def compile_taxonomy(taxonomy: dict) -> list[dict]:
    """
    Flatten and compile the taxonomy into a list of rule dicts, each with:
      category, subcategory, keyword, pattern (compiled regex)
    """
    rules = []
    for category, subcats in taxonomy.items():
        for subcategory, keywords in subcats.items():
            for kw in keywords:
                try:
                    pat = re.compile(r"\b" + kw + r"\b", re.I)
                except re.error:
                    # Some patterns don't need word boundaries (e.g. "geopolit")
                    pat = re.compile(kw, re.I)
                rules.append({
                    "category":    category,
                    "subcategory": subcategory,
                    "keyword":     kw,
                    "pattern":     pat,
                })
    return rules


RULES = compile_taxonomy(KEYWORD_TAXONOMY)


# ─────────────────────────────────────────────────────────────────────────────
# Core tagging function
# ─────────────────────────────────────────────────────────────────────────────

def tag_filing(risk_text: str, meta: dict, source_file: str) -> list[dict]:
    """
    Apply all keyword rules to the risk factor text.
    Returns a list of row dicts ready for CSV output.
    """
    sentences = split_sentences(risk_text)
    rows = []

    for rule in RULES:
        pat      = rule["pattern"]
        category = rule["category"]
        subcat   = rule["subcategory"]
        keyword  = rule["keyword"]

        # Count total occurrences across the full text (for frequency-based scoring)
        total_hits = len(pat.findall(risk_text))
        if total_hits == 0:
            continue

        # Find sentences that contain this keyword
        matching = [s for s in sentences if pat.search(s)]

        # Select top sentences by length (longer = more context = more useful)
        matching.sort(key=len, reverse=True)
        if MAX_SENTENCES_PER_KEYWORD:
            matching = matching[:MAX_SENTENCES_PER_KEYWORD]

        for sent in matching:
            score, rationale = score_severity(sent, total_hits, total_hits)
            rows.append({
                "company":           meta.get("company", ""),
                "ticker":            meta.get("ticker", ""),
                "filing_year":       meta.get("filing_year", ""),
                "filing_date":       meta.get("filing_date", ""),
                "risk_category":     category,
                "risk_subcategory":  subcat,
                "keyword_matched":   keyword,
                "evidence_sentence": sent,
                "keyword_count":     total_hits,
                "severity_score":    score,
                "severity_rationale":rationale,
                "source_file":       source_file,
                "analyst_notes":     "",
            })

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "company", "ticker", "filing_year", "filing_date",
    "risk_category", "risk_subcategory", "keyword_matched",
    "evidence_sentence", "keyword_count", "severity_score",
    "severity_rationale", "source_file", "analyst_notes",
]


def main():
    log.info("Phase 2 – Master Supply Chain Risk Table Builder")
    log.info("Input directory: %s", INPUT_DIR.resolve())

    txt_files = sorted(INPUT_DIR.glob("*_risk_factors.txt"))
    if not txt_files:
        log.error("No *_risk_factors.txt files found in %s", INPUT_DIR)
        log.error("Run edgar_risk_factors.py (Phase 1) first.")
        return

    log.info("Found %d filing(s) to process", len(txt_files))

    all_rows = []
    summary  = []

    for txt_path in txt_files:
        log.info("  Processing %s ...", txt_path.name)
        content = txt_path.read_text(encoding="utf-8")

        # Split header block from body
        separator = "─" * 72
        if separator in content:
            header_block, risk_text = content.split(separator, 1)
            risk_text = risk_text.strip()
        else:
            header_block = ""
            risk_text = content

        meta = parse_header(header_block)
        if not meta.get("company"):
            # Fallback: derive ticker from filename
            meta["company"] = txt_path.stem.replace("_risk_factors", "")
            meta["ticker"]  = meta["company"]
            meta["filing_year"] = "Unknown"
            meta["filing_date"] = "Unknown"

        rows = tag_filing(risk_text, meta, txt_path.name)
        all_rows.extend(rows)

        # Per-file summary
        cats_found = sorted({r["risk_category"] for r in rows})
        kws_found  = len({r["keyword_matched"] for r in rows})
        log.info(
            "    → %d rows | %d unique keywords | categories: %s",
            len(rows), kws_found, ", ".join(cats_found) if cats_found else "none"
        )
        summary.append({
            "file":            txt_path.name,
            "company":         meta.get("company", ""),
            "ticker":          meta.get("ticker", ""),
            "filing_year":     meta.get("filing_year", ""),
            "total_rows":      len(rows),
            "unique_keywords": kws_found,
            "categories":      cats_found,
        })

    # Write CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    # Write summary JSON
    OUTPUT_JSON.write_text(
        json.dumps({
            "generated":    datetime.utcnow().isoformat() + "Z",
            "total_rows":   len(all_rows),
            "filings":      len(txt_files),
            "per_company":  summary,
        }, indent=2),
        encoding="utf-8"
    )

    log.info("\n%s", "═" * 60)
    log.info("Done.")
    log.info("  Total rows written : %d", len(all_rows))
    log.info("  Filings processed  : %d", len(txt_files))
    log.info("  CSV  → %s", OUTPUT_CSV)
    log.info("  JSON → %s", OUTPUT_JSON)
    log.info("\nTip: open master_risk_table.csv in Excel → Insert → PivotTable")
    log.info("     Rows = risk_category, Columns = company, Values = count of severity_score")


if __name__ == "__main__":
    main()
