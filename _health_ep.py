@app.get("/api/linkedin/health")
async def vm_linkedin_health(force_refresh: bool = Query(False)):
    """Probe LinkedIn /feed/ via SOCKS5 + LI_AT and return cached health.
    Used by PC's pre-dispatch precheck so a user can't launch a campaign
    while LinkedIn is throttling — saves quota and avoids deepening the cooldown.
    """
    try:
        from linkedin.cooldown import check_health
        result = await check_health(force_refresh=force_refresh)
        return result
    except Exception as e:
        return {"state": "blocked", "reason": f"probe_exception:{e}"}


@app.post("/api/linkedin/health/clear")
async def vm_linkedin_health_clear():
    """Manually clear the cooldown cache (admin / debugging)."""
    try:
        from linkedin.cooldown import CACHE_FILE
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
        return {"ok": True, "note": "cache cleared — next request will probe live"}
    except Exception as e:
        return {"ok": False, "error": str(e)}