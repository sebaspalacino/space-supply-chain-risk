"""
validate_risk_table.py
──────────────────────


Reads master_risk_table.csv (produced by build_risk_table.py), sends each
evidence sentence to Claude for context-aware validation, and writes two
output files:

  master_risk_table_validated.csv   — rows Claude confirmed as real risks
  master_risk_table_rejected.csv    — rows Claude flagged as false positives
                                      (with rejection reason, for audit)

False positive types this catches (identified from your data):
  1. Named-entity misfires    e.g. "war" → "Australian War Memorial"
  2. Enumeration/listing      e.g. "cybersecurity" in a product list
  3. Mitigated context        e.g. "We have implemented controls to..."
  4. Incidental country mention e.g. "competitors in Russia and China"
  5. Definitional context     e.g. ITAR defined, not flagged as a risk
  6. Accounting/pricing use   e.g. "inflation adjustment clause"
  7. Wrong domain match       e.g. "strike price" / "European Union"

Usage:
    python validate_risk_table.py

    The Anthropic API key is handled automatically by the Claude.ai environment.
    If running locally: set ANTHROPIC_API_KEY in your environment.

Input:   ./risk_factors/master_risk_table.csv
Output:  ./risk_factors/master_risk_table_validated.csv
         ./risk_factors/master_risk_table_rejected.csv
         ./risk_factors/validation_log.json
"""

import csv
import json
import os
import time
import logging
from pathlib import Path
from datetime import datetime

import requests

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

INPUT_CSV       = Path("risk_factors/master_risk_table.csv")
VALIDATED_CSV   = Path("risk_factors/master_risk_table_validated.csv")
REJECTED_CSV    = Path("risk_factors/master_risk_table_rejected.csv")
LOG_JSON        = Path("risk_factors/validation_log.json")

# Claude model to use for validation
MODEL = "claude-sonnet-4-5"

# Requests per minute guard (Anthropic API: generous limits, but be polite)
# Each row = 1 API call. With 448 rows this takes ~3-5 minutes.
API_DELAY_SECONDS = 0.3

# If True, identical (keyword, sentence) pairs are only validated once
# and the result is reused — saves API calls for duplicate sentences.
CACHE_DUPLICATES = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic API call
# ─────────────────────────────────────────────────────────────────────────────

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

def get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY not set.\n"
            "Set it with:  set ANTHROPIC_API_KEY=sk-ant-...  (Windows)\n"
            "          or  export ANTHROPIC_API_KEY=sk-ant-...  (Mac/Linux)"
        )
    return key


def call_claude(prompt: str, api_key: str) -> str:
    """Send a prompt to Claude and return the text response."""
    headers = {
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    body = {
        "model":      MODEL,
        "max_tokens": 200,
        "messages":   [{"role": "user", "content": prompt}],
        "system": (
            "You are a supply chain risk analyst reviewing sentences extracted "
            "from SEC 10-K filings. Your job is to decide whether a sentence "
            "genuinely expresses a supply chain risk for the company. "
            "Respond ONLY with a valid JSON object — no markdown, no explanation."
        ),
    }
    resp = requests.post(ANTHROPIC_API_URL, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


# ─────────────────────────────────────────────────────────────────────────────
# Validation prompt
# ─────────────────────────────────────────────────────────────────────────────

def build_prompt(row: dict) -> str:
    return f"""You are reviewing a sentence from a company's 10-K SEC filing Risk Factors section.

Company: {row['company']}
Risk category being checked: {row['risk_category']} → {row['risk_subcategory']}
Keyword that triggered this row: "{row['keyword_matched']}"
Evidence sentence: "{row['evidence_sentence']}"

Decide whether this sentence GENUINELY expresses a supply chain risk for this company.

A sentence is a GENUINE risk if it:
- Describes a real vulnerability, dependency, or threat the company faces
- Explains why the keyword represents an actual business risk
- Uses the keyword in the context of supply chain, operations, or business continuity

A sentence is a FALSE POSITIVE if:
- The keyword matches a proper noun or named entity (e.g. "War Memorial", "European Union", "Strike price")
- The sentence is a product/capability listing ("we offer cybersecurity products...")
- The keyword is used in an accounting or financial formula context ("inflation adjustment clause")
- The sentence describes a mitigated or resolved risk ("we have implemented controls...")
- The country name appears only in a market/competition context, not supply risk
- The sentence is definitional ("ITAR is a regulation that...")
- The keyword appears in a completely unrelated context

Respond ONLY with this exact JSON format:
{{
  "is_genuine_risk": true or false,
  "confidence": "high" or "medium" or "low",
  "rejection_reason": "brief reason if false positive, else null",
  "revised_subcategory": "corrected subcategory if miscategorized, else null"
}}"""


# ─────────────────────────────────────────────────────────────────────────────
# Parse Claude's JSON response safely
# ─────────────────────────────────────────────────────────────────────────────

import re as _re

def parse_response(text: str) -> dict:
    """Extract JSON from Claude's response robustly."""
    # Strip markdown code fences if present
    text = _re.sub(r"```(?:json)?|```", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract just the JSON object
        m = _re.search(r"\{.*\}", text, _re.S)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    # Fallback: assume genuine if we can't parse (fail-safe)
    log.warning("  Could not parse Claude response: %s", text[:100])
    return {
        "is_genuine_risk":    True,
        "confidence":         "low",
        "rejection_reason":   None,
        "revised_subcategory": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main validation loop
# ─────────────────────────────────────────────────────────────────────────────

# Output CSV fields — original fields + validation columns
EXTRA_FIELDS = ["llm_validated", "llm_confidence", "rejection_reason", "revised_subcategory"]

def main():
    log.info("Phase 2b – LLM Context Validation")
    log.info("Input:  %s", INPUT_CSV)

    if not INPUT_CSV.exists():
        log.error("Input file not found: %s", INPUT_CSV)
        log.error("Run build_risk_table.py (Phase 2) first.")
        return

    api_key = get_api_key()

    # Read all rows
    with open(INPUT_CSV, encoding="utf-8") as f:
        reader    = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows      = list(reader)

    log.info("Loaded %d rows from %s", len(rows), INPUT_CSV.name)
    log.info("Model: %s | Cache duplicates: %s", MODEL, CACHE_DUPLICATES)

    out_fields = fieldnames + EXTRA_FIELDS

    validated_rows = []
    rejected_rows  = []
    cache          = {}   # (keyword, sentence[:120]) → parsed response
    api_calls      = 0
    cache_hits     = 0
    errors         = 0

    for i, row in enumerate(rows):
        cache_key = (row["keyword_matched"], row["evidence_sentence"][:120])

        if CACHE_DUPLICATES and cache_key in cache:
            result = cache[cache_key]
            cache_hits += 1
        else:
            try:
                prompt   = build_prompt(row)
                raw      = call_claude(prompt, api_key)
                result   = parse_response(raw)
                api_calls += 1
                if CACHE_DUPLICATES:
                    cache[cache_key] = result
                time.sleep(API_DELAY_SECONDS)
            except Exception as exc:
                log.warning("  Row %d API error: %s — keeping row", i, exc)
                result = {
                    "is_genuine_risk":    True,
                    "confidence":         "low",
                    "rejection_reason":   f"API error: {exc}",
                    "revised_subcategory": None,
                }
                errors += 1

        # Annotate row
        row["llm_validated"]       = str(result.get("is_genuine_risk", True))
        row["llm_confidence"]      = result.get("confidence", "low")
        row["rejection_reason"]    = result.get("rejection_reason") or ""
        row["revised_subcategory"] = result.get("revised_subcategory") or ""

        # Apply revised subcategory if Claude corrected it
        if result.get("revised_subcategory"):
            row["risk_subcategory"] = result["revised_subcategory"]

        if result.get("is_genuine_risk", True):
            validated_rows.append(row)
        else:
            rejected_rows.append(row)

        # Progress log every 25 rows
        if (i + 1) % 25 == 0 or i == len(rows) - 1:
            log.info(
                "  [%d/%d] ✓ kept=%d  ✗ rejected=%d  cache_hits=%d  api_calls=%d",
                i + 1, len(rows),
                len(validated_rows), len(rejected_rows),
                cache_hits, api_calls,
            )

    # Write validated CSV
    with open(VALIDATED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(validated_rows)

    # Write rejected CSV (for audit — never just discard)
    with open(REJECTED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(rejected_rows)

    # Rejection breakdown by type
    rejection_reasons = {}
    for r in rejected_rows:
        reason = r["rejection_reason"] or "unspecified"
        # Bucket into short labels
        if "named entity" in reason.lower() or "proper noun" in reason.lower():
            bucket = "Named entity misfire"
        elif "list" in reason.lower() or "enumerat" in reason.lower() or "product" in reason.lower():
            bucket = "Listing / capability description"
        elif "mitigat" in reason.lower() or "compli" in reason.lower() or "implement" in reason.lower():
            bucket = "Mitigated / compliant context"
        elif "competit" in reason.lower() or "market" in reason.lower():
            bucket = "Incidental market mention"
        elif "defin" in reason.lower() or "regulat" in reason.lower():
            bucket = "Definitional / regulatory boilerplate"
        elif "account" in reason.lower() or "financ" in reason.lower() or "pricing" in reason.lower():
            bucket = "Accounting / pricing context"
        else:
            bucket = "Other"
        rejection_reasons[bucket] = rejection_reasons.get(bucket, 0) + 1

    # Write log
    log_data = {
        "generated":           datetime.utcnow().isoformat() + "Z",
        "model":               MODEL,
        "input_rows":          len(rows),
        "validated_kept":      len(validated_rows),
        "rejected":            len(rejected_rows),
        "rejection_rate_pct":  round(100 * len(rejected_rows) / len(rows), 1),
        "api_calls_made":      api_calls,
        "cache_hits":          cache_hits,
        "errors":              errors,
        "rejection_breakdown": rejection_reasons,
    }
    LOG_JSON.write_text(json.dumps(log_data, indent=2), encoding="utf-8")

    # Summary
    log.info("\n%s", "═" * 60)
    log.info("Validation complete.")
    log.info("  Input rows    : %d", len(rows))
    log.info("  Kept (genuine): %d  (%.1f%%)", len(validated_rows), 100*len(validated_rows)/len(rows))
    log.info("  Rejected      : %d  (%.1f%%)", len(rejected_rows),  100*len(rejected_rows)/len(rows))
    log.info("  API calls     : %d  (cache saved %d calls)", api_calls, cache_hits)
    if errors:
        log.warning("  Errors        : %d rows defaulted to 'keep'", errors)
    log.info("\n  Rejection breakdown:")
    for bucket, count in sorted(rejection_reasons.items(), key=lambda x: -x[1]):
        log.info("    %-42s %d", bucket, count)
    log.info("\n  Validated CSV → %s", VALIDATED_CSV)
    log.info("  Rejected CSV  → %s  (audit trail)", REJECTED_CSV)
    log.info("  Log JSON      → %s", LOG_JSON)
    log.info("\nTip: review master_risk_table_rejected.csv to spot any over-filtering,")
    log.info("     then adjust KEYWORD_TAXONOMY or re-run with revised prompts.")


if __name__ == "__main__":
    main()
