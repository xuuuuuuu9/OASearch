"""HTTP helpers for the Reflex frontend."""
from __future__ import annotations

import os
from typing import Any, Optional
from urllib.parse import urlencode

import httpx


API_BASE = os.getenv("NP_OA_API_URL", "http://127.0.0.1:8000")


async def get_json(path: str, params: Optional[dict[str, Any]] = None) -> Any:
    url = f"{API_BASE}{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


async def post_json(path: str, payload: dict[str, Any]) -> Any:
    url = f"{API_BASE}{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


async def patch_json(path: str, payload: dict[str, Any]) -> Any:
    url = f"{API_BASE}{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.patch(url, json=payload)
        response.raise_for_status()
        return response.json()


async def delete_json(path: str) -> Any:
    url = f"{API_BASE}{path}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.delete(url)
        response.raise_for_status()
        return response.json()


def library_search_query(q: str, scope: str, page: int, page_size: int) -> str:
    return urlencode(
        {
            "q": q,
            "scope": scope,
            "page": page,
            "page_size": page_size,
        }
    )
