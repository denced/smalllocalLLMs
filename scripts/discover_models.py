#!/usr/bin/env python3
"""Discover new mlx-community 4-bit instruct models for the Youme catalog.

Queries the HuggingFace API for recently-updated mlx-community uploads,
filters for phone-suitable 4-bit instruct/chat models that aren't already
in models.json, and appends them with sensible defaults. Editorial fields
(`bestFor`, `contextWindow`, sometimes `licenseLabel`) are left as
`[TODO: ...]` placeholders so a human review pass is required before
merging.

Run `python3 scripts/discover_models.py --dry-run` to see what it would add
without writing anything.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent.parent / "models.json"
HF_API = "https://huggingface.co/api/models"
LIST_LIMIT = 500

# Substring matching against the lowercased repo leaf — simpler than a regex
# when names like "AudioDiT" or "gabliterated" jam tokens together with no
# word boundary in between. Add new patterns here as noise comes through PRs.
EXCLUDE_SUBSTRINGS = (
    # Non-language modalities or specialized tasks
    "vision", "-vl-", "reranker", "embed", "tts", "svara", "audio",
    "dit", "speech", "voice", "translate", "seg", "coder", "math",
    # Non-4-bit quants / experimental quant pipelines
    "nvfp4", "bf16", "mxfp", "6bit", "8bit", "dwq", "optiq", "awq",
    "bnb", "mlx-4bit",
    # Base / pre-trained weights (we want instruct/chat)
    "base", "pretrained",
    # Distillations of frontier models, uncensored variants
    "distill", "qwopus", "bliterated", "heretic",
    # Safety / classification
    "guard", "moderation", "privacy",
    # Experimental releases
    "preview", "draft", "beta",
)
# Match number-with-unit (e.g. "1.5B", "360M", "1b") only when followed by a
# separator or end-of-string — otherwise "4bit" gets misparsed as "4 billion".
PARAMS = re.compile(r"(\d+(?:\.\d+)?)([BbMm])(?=[-_.\s]|$)")

FAMILIES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^qwen", re.I), "Qwen"),
    (re.compile(r"^llama|^meta-llama", re.I), "Llama"),
    (re.compile(r"^phi", re.I), "Phi"),
    (re.compile(r"^gemma", re.I), "Gemma"),
    (re.compile(r"^smollm", re.I), "SmolLM"),
    (re.compile(r"^deepseek", re.I), "DeepSeek"),
    (re.compile(r"^mistral|^ministral", re.I), "Mistral"),
]

LICENSE_ALIASES = {
    "apache-2.0": "Apache 2.0",
    "mit": "MIT",
    "llama3.2": "Llama 3.2 Community",
    "llama3.3": "Llama 3.3 Community",
    "llama4": "Llama 4 Community",
    "gemma": "Gemma",
    "cc-by-nc-4.0": "CC BY-NC 4.0",
    "cc-by-4.0": "CC BY 4.0",
}


def http_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "youme-catalog-bot"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def params_b(s: str) -> float | None:
    m = PARAMS.search(s)
    if not m:
        return None
    val = float(m.group(1))
    return val if m.group(2).upper() == "B" else val / 1000.0


def is_phone_suitable(model_id: str) -> bool:
    """Accept 4-bit quants ≤ 5B params that aren't on the EXCLUDE list.

    Modern model repos often drop the `-Instruct-` suffix (e.g. `Qwen3.5-2B-4bit`,
    `SmolLM3-3B-4bit`), so we DON'T require an instruct tag — instead we trust
    EXCLUDE_SUBSTRINGS to reject base / specialized / experimental variants.
    """
    leaf = model_id.split("/", 1)[-1].lower()
    if "4bit" not in leaf:
        return False
    if any(sub in leaf for sub in EXCLUDE_SUBSTRINGS):
        return False
    b = params_b(leaf)
    return b is not None and b <= 5.0


def detect_family(model_id: str) -> str:
    leaf = model_id.split("/", 1)[-1]
    for rx, fam in FAMILIES:
        if rx.match(leaf):
            return fam
    return leaf.split("-")[0]


def display_name(model_id: str) -> str:
    leaf = model_id.split("/", 1)[-1]
    s = re.sub(r"-(Instruct|instruct|it|chat|Chat)-4bit$", "", leaf)
    s = re.sub(r"-4bit$", "", s)
    s = re.sub(r"(\D)(\d+(?:\.\d+)?[BbMm])", r"\1 \2", s)
    return s.replace("-", " ")


def min_ram_gb(billion_params: float) -> float:
    if billion_params <= 1.0:
        return 4.0
    if billion_params <= 2.5:
        return 5.5
    return 7.5


def license_label(card_data: dict | None) -> str:
    raw = (card_data or {}).get("license", "")
    if not raw:
        return "[TODO: license]"
    return LICENSE_ALIASES.get(raw.lower(), raw)


def format_param_count(b: float) -> str:
    if b >= 1.0:
        # 0.6 -> "0.6B", 1.0 -> "1B", 1.5 -> "1.5B"
        s = f"{b:g}"
        return f"{s}B"
    return f"{int(round(b * 1000))}M"


def format_release_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %Y")
    except (ValueError, TypeError):
        return ""


def estimated_size_bytes(billion_params: float) -> int:
    """Rough size estimate for a 4-bit quantized model.

    4-bit quants run roughly 0.55 GB per billion parameters (the bit-pack
    plus tokenizer/config overhead). Real values vary ±20% but this is fine
    for the picker's pre-download estimate. The HF API doesn't return file
    sizes in the listing endpoint so we don't query for the truth.
    """
    return int(billion_params * 0.55 * 1_000_000_000)


def main(dry_run: bool = False) -> None:
    manifest = json.loads(MANIFEST.read_text())
    have = {m["id"] for m in manifest["models"]}

    listing = http_json(
        f"{HF_API}?author=mlx-community&sort=lastModified&direction=-1&limit={LIST_LIMIT}"
    )

    new_entries: list[dict] = []
    for entry in listing:
        model_id = entry.get("id", "")
        if not model_id or model_id in have or not is_phone_suitable(model_id):
            continue

        try:
            detail = http_json(f"{HF_API}/{model_id}")
        except Exception as e:
            print(f"  skip {model_id} (detail fetch failed: {e})", file=sys.stderr)
            continue

        b = params_b(model_id.split("/", 1)[-1])
        if b is None:
            continue

        new_entries.append({
            "id": model_id,
            "displayName": display_name(model_id),
            "family": detect_family(model_id),
            "paramCount": format_param_count(b),
            "contextWindow": "[TODO: context window]",
            "releaseDate": format_release_date(entry.get("lastModified")),
            "bestFor": "[TODO: tagline]",
            "approxSizeBytes": estimated_size_bytes(b),
            "minRamGB": min_ram_gb(b),
            "licenseLabel": license_label(detail.get("cardData")),
        })

    if not new_entries:
        print("No new candidates.")
        return

    print(f"Proposing {len(new_entries)} new entries:")
    for n in new_entries:
        print(f"  + {n['id']} ({n['paramCount']}, {n['licenseLabel']}, {n['releaseDate']})")

    if dry_run:
        print("(dry-run; manifest not written)")
        return

    merged = manifest["models"] + new_entries
    merged.sort(key=lambda m: (m["family"], m["approxSizeBytes"]))
    manifest["models"] = merged
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {MANIFEST}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
