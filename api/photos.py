"""Hermes Cloud Studio — Photo proxy + cache (MERGED-011)."""
from __future__ import annotations

import hashlib

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from core.state import GOOGLE_API_KEY, PHOTO_CACHE_DIR

router = APIRouter()


@router.get("/api/photos/{photo_ref:path}")
async def proxy_photo(photo_ref: str, maxHeight: int = 400):
    """Fetch Google Maps photo and cache locally. Supports both gosom direct URLs and Places API refs."""
    cache_key = hashlib.md5(f"{photo_ref}_{maxHeight}".encode()).hexdigest()
    cache_path = PHOTO_CACHE_DIR / f"{cache_key}.jpg"

    if cache_path.exists():
        return FileResponse(cache_path, media_type="image/jpeg")

    # Gosom scraper provides direct Google Photos URLs (lh3.googleusercontent.com)
    if photo_ref.startswith("http"):
        url = photo_ref
        if "=" in url and "googleusercontent.com" in url:
            url = url.rsplit("=", 1)[0] + f"=w{maxHeight}-h{maxHeight}-k-no"
    elif GOOGLE_API_KEY:
        url = f"https://places.googleapis.com/v1/{photo_ref}/media?maxHeightPx={maxHeight}&key={GOOGLE_API_KEY}"
    else:
        raise HTTPException(503, "Photo not available")

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                cache_path.write_bytes(r.content)
                return Response(content=r.content, media_type="image/jpeg")
            else:
                raise HTTPException(r.status_code, "Photo fetch failed")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Photo proxy error: {e}")
