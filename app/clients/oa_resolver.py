"""OA URL resolver — orchestrates 6 sources in parallel per DOI.

Priority order (lower number = try first when downloading):
  10  Europe PMC      — direct PMC PDF, no Cloudflare, NIH speed
  15  OpenAlex repo   — repository-hosted PDFs (preprints, institutional)
  20  CrossRef link   — publisher-supplied
  25  OpenAlex pub    — OpenAlex's publisher pick
  30  Unpaywall best
  40  Unpaywall alts
  50  URL patterns    — arxiv/biorxiv/chemrxiv deterministic
  60  Landing page    — meta[citation_pdf_url], last resort
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

from .crossref import parse_work  # only for type
from .europepmc import EuropePMCClient
from .landing_page import scrape_pdf_urls
from .openalex import OpenAlexClient
from .unpaywall import UnpaywallClient
from .url_patterns import infer_urls


log = logging.getLogger("nplibrary.oa_resolver")


@dataclass
class Candidate:
    url: str
    source: str
    priority: int


SOURCE_PRIORITY = {
    "pmc":                10,
    "ncbi-pmc":           11,
    "openalex-repo":      15,
    "crossref-link":      20,
    "openalex-pub":       25,
    "unpaywall-best":     30,
    "unpaywall-alt":      40,
    "arxiv":              50,
    "biorxiv":            50,
    "chemrxiv":           50,
    "researchsquare":     50,
    "landing":            60,
}


# Hosts that almost certainly Cloudflare-block any programmatic download.
# Marked separately so the UI can warn the user up-front.
HOSTILE_HOSTS = {
    "pubs.acs.org",
}


def is_hostile_host(url: str) -> bool:
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    return host in HOSTILE_HOSTS


def _dedupe(cands: list[Candidate]) -> list[Candidate]:
    seen: set[str] = set()
    out: list[Candidate] = []
    for c in sorted(cands, key=lambda x: x.priority):
        # Normalize trailing slash and lowercase scheme/host
        key = c.url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


async def resolve(
    doi: str,
    *,
    crossref_pdf_links: Optional[list[str]] = None,
    unpaywall: Optional[UnpaywallClient] = None,
    europepmc: Optional[EuropePMCClient] = None,
    openalex: Optional[OpenAlexClient] = None,
    scrape_landing: bool = True,
) -> tuple[list[Candidate], dict[str, Any]]:
    """Resolve a DOI to candidate URLs from all available sources concurrently.

    Returns (sorted_candidates, oa_info_dict) where oa_info_dict has keys:
      is_oa, license, pmcid, oa_status

    The caller passes optional clients so they can be reused across many DOIs.
    """
    doi = (doi or "").strip().lower()
    if not doi:
        return [], {}

    async def _unpaywall() -> dict[str, Any]:
        if not unpaywall:
            return {}
        try:
            return await unpaywall.lookup(doi)
        except Exception as e:
            log.debug("unpaywall lookup failed %s: %r", doi, e)
            return {}

    async def _epmc() -> Optional[dict[str, Any]]:
        if not europepmc:
            return None
        try:
            return await europepmc.lookup(doi)
        except Exception as e:
            log.debug("europepmc lookup failed %s: %r", doi, e)
            return None

    async def _oalex() -> Optional[dict[str, Any]]:
        if not openalex:
            return None
        try:
            return await openalex.lookup(doi)
        except Exception as e:
            log.debug("openalex lookup failed %s: %r", doi, e)
            return None

    upw, epmc, oalex = await asyncio.gather(_unpaywall(), _epmc(), _oalex())

    candidates: list[Candidate] = []

    # 1. Europe PMC — preferred when actually deposited there
    pmcid = None
    if epmc and epmc.get("pmcid") and epmc.get("in_pmc"):
        pmcid = epmc["pmcid"]
        candidates.append(Candidate(
            EuropePMCClient.pdf_url_for_pmcid(pmcid),
            "pmc", SOURCE_PRIORITY["pmc"],
        ))
        candidates.append(Candidate(
            EuropePMCClient.ncbi_pdf_url_for_pmcid(pmcid),
            "ncbi-pmc", SOURCE_PRIORITY["ncbi-pmc"],
        ))

    # 2. OpenAlex repository PDFs (high priority — usually bypass publisher CF)
    if oalex:
        for url in oalex.get("repo_pdf_urls") or []:
            candidates.append(Candidate(url, "openalex-repo", SOURCE_PRIORITY["openalex-repo"]))

    # 3. CrossRef inline links (zero extra round trip)
    for url in crossref_pdf_links or []:
        candidates.append(Candidate(url, "crossref-link", SOURCE_PRIORITY["crossref-link"]))

    # 4. OpenAlex publisher locations
    if oalex:
        for url in oalex.get("pub_pdf_urls") or []:
            candidates.append(Candidate(url, "openalex-pub", SOURCE_PRIORITY["openalex-pub"]))

    # 5. Unpaywall best + alternates
    upw_urls = (upw or {}).get("all_pdf_urls") or []
    for i, url in enumerate(upw_urls):
        priority_key = "unpaywall-best" if i == 0 else "unpaywall-alt"
        candidates.append(Candidate(url, priority_key, SOURCE_PRIORITY[priority_key]))

    # 6. URL patterns (preprints) — zero round trip
    for url, src in infer_urls(doi):
        candidates.append(Candidate(url, src, SOURCE_PRIORITY.get(src, 50)))

    deduped = _dedupe(candidates)

    # 7. Landing-page scraping — only if nothing else turned up anything
    if scrape_landing and not deduped:
        try:
            scraped = await scrape_pdf_urls(doi)
            for url in scraped:
                deduped.append(Candidate(url, "landing", SOURCE_PRIORITY["landing"]))
        except Exception as e:
            log.debug("landing scrape failed %s: %r", doi, e)

    oa_info = {
        "is_oa": (upw or {}).get("is_oa") if upw else None,
        "license": (upw or {}).get("license"),
        "pmcid": pmcid,
        "oa_status": (oalex or {}).get("oa_status"),
    }
    # Trust OpenAlex over Unpaywall for is_oa when they disagree — OpenAlex
    # tends to be stricter (won't flag publisher-only access as OA).
    if oalex and oalex.get("is_oa") is False:
        oa_info["is_oa"] = False
    # Only override is_oa to True for *strong* sources.
    if not oa_info.get("is_oa"):
        strong_sources = {"pmc", "ncbi-pmc", "openalex-repo", "arxiv", "biorxiv", "chemrxiv", "researchsquare"}
        if any(c.source in strong_sources for c in deduped):
            oa_info["is_oa"] = True

    return deduped, oa_info


async def resolve_many(
    dois: list[str],
    *,
    crossref_pdf_links_map: Optional[dict[str, list[str]]] = None,
    unpaywall_concurrency: int = 20,
    epmc_concurrency: int = 16,
    openalex_concurrency: int = 12,
) -> dict[str, tuple[list[Candidate], dict[str, Any]]]:
    """Batch entry point used by the search task. Shares clients across DOIs."""
    if not dois:
        return {}

    async with UnpaywallClient(concurrency=unpaywall_concurrency) as upw, \
               EuropePMCClient(concurrency=epmc_concurrency) as epmc, \
               OpenAlexClient(concurrency=openalex_concurrency) as oalex:
        async def _one(d: str) -> tuple[str, tuple[list[Candidate], dict[str, Any]]]:
            return d, await resolve(
                d,
                crossref_pdf_links=(crossref_pdf_links_map or {}).get(d),
                unpaywall=upw,
                europepmc=epmc,
                openalex=oalex,
                scrape_landing=False,   # batch mode: skip slow landing scrape
            )

        results = await asyncio.gather(*[asyncio.create_task(_one(d)) for d in dois])
    return dict(results)
