"""Pattern-based PDF URL inference from a DOI.

Pure string operations — no network. Generates direct PDF URLs for known
preprint repositories whose DOI → URL mapping is deterministic.
"""
from __future__ import annotations

import re


_ARXIV_PREFIX = "10.48550/arxiv."
_BIORXIV_PREFIX = "10.1101/"
_CHEMRXIV_PREFIX = "10.26434/"
_RESEARCHSQUARE_PREFIX = "10.21203/rs."


def infer_urls(doi: str) -> list[tuple[str, str]]:
    """Return list of (url, source) tuples likely to be a PDF for this DOI.

    Each pattern is high-confidence — these are direct, deterministic mappings
    that the host serves as a real PDF without auth.
    """
    doi = (doi or "").lower().strip()
    out: list[tuple[str, str]] = []
    if not doi:
        return out

    if doi.startswith(_ARXIV_PREFIX):
        arxiv_id = doi[len(_ARXIV_PREFIX):]
        out.append((f"https://arxiv.org/pdf/{arxiv_id}.pdf", "arxiv"))
        return out

    if doi.startswith(_BIORXIV_PREFIX):
        rest = doi[len(_BIORXIV_PREFIX):]
        # bioRxiv DOIs look like 2024.01.01.123456 ; medRxiv similar.
        # Both serve PDF at biorxiv.org/content/{rest}.full.pdf
        if re.match(r"\d{4}\.\d{2}\.\d{2}\.\d+", rest):
            out.append((
                f"https://www.biorxiv.org/content/{_BIORXIV_PREFIX}{rest}.full.pdf",
                "biorxiv",
            ))
        return out

    if doi.startswith(_CHEMRXIV_PREFIX):
        # ChemRxiv DOI format is 10.26434/chemrxiv-2024-xxxxx
        # Their stable PDF URL pattern (post 2021 migration to Cambridge OE):
        rest = doi[len(_CHEMRXIV_PREFIX):]
        out.append((
            f"https://chemrxiv.org/engage/api-gateway/chemrxiv/assets/orp/resource/item/"
            f"{rest}/original/{rest}.pdf",
            "chemrxiv",
        ))
        return out

    if doi.startswith(_RESEARCHSQUARE_PREFIX):
        # Research Square preprints DOI: 10.21203/rs.3.rs-XXXXX/v1
        # PDF at researchsquare.com/article/{slug}/v{N}
        m = re.match(r"rs\.\d+\.rs-(\d+)/v(\d+)", doi[len(_RESEARCHSQUARE_PREFIX):])
        if m:
            slug = m.group(1)
            ver = m.group(2)
            out.append((
                f"https://www.researchsquare.com/article/rs-{slug}/v{ver}.pdf",
                "researchsquare",
            ))
        return out

    return out
