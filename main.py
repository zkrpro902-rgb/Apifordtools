"""
DTOOLS — FastAPI Backend
Deploy sur Railway: railway up

Routes:
  GET /check?user=xxx&platform=discord   → username availability
  GET /ip?q=1.2.3.4                      → IP info (vide = IP du caller)
  GET /whois?q=domain.com               → WHOIS / RDAP info
  GET /invite?code=abcdef               → Discord invite info
  GET /health                           → status check
"""

import asyncio
import re
import httpx
from fastapi import FastAPI, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="DTOOLS API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DTOOLSBot/1.0)"}


# ── WEBHOOK PROXY ──────────────────────────────────────────────
@app.post("/webhook")
async def webhook_proxy(request: Request):
    """
    Proxy pour envoyer un webhook Discord sans CORS.
    Body JSON: { "url": "https://discord.com/api/webhooks/...", "payload": {...} }
    """
    try:
        data = await request.json()
        url = data.get("url", "").strip()
        payload = data.get("payload", {})

        if not url or "discord.com/api/webhooks/" not in url and "discordapp.com/api/webhooks/" not in url:
            return JSONResponse({"ok": False, "error": "URL webhook invalide"}, status_code=400)

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            return JSONResponse({
                "ok": r.status_code in (200, 204),
                "status": r.status_code,
                "body": r.text[:200] if r.text else ""
            })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ── HEALTH ────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ── USERNAME CHECKER ──────────────────────────────────────────
@app.get("/check")
async def check(user: str = "", platform: str = ""):
    user = user.strip()
    platform = platform.strip().lower()

    if not user or not platform:
        return JSONResponse({"error": "Missing user or platform"}, status_code=400)

    result = await check_platform(platform, user)
    return JSONResponse(result)


async def check_platform(platform: str, user: str) -> dict:
    handlers = {
        "discord":     lambda: check_discord(user),
        "guns.lol":    lambda: check_url(f"https://guns.lol/{user}"),
        "sellix":      lambda: check_url(f"https://sellix.io/{user}"),
        "mysellauth":  lambda: check_url(f"https://mysellauth.com/{user}"),
        "kick":        lambda: check_url(f"https://kick.com/{user}"),
        "instagram":   lambda: check_instagram(user),
        "twitter/x":   lambda: check_url(f"https://twitter.com/{user}"),
        "tiktok":      lambda: check_url(f"https://www.tiktok.com/@{user}"),
        "twitch":      lambda: check_twitch(user),
        "youtube":     lambda: check_url(f"https://www.youtube.com/@{user}"),
        "github":      lambda: check_github(user),
        "reddit":      lambda: check_reddit(user),
        "telegram":    lambda: check_url(f"https://t.me/{user}"),
        "roblox":      lambda: check_roblox(user),
        "spotify":     lambda: check_url(f"https://open.spotify.com/user/{user}"),
        "cashapp":     lambda: check_url(f"https://cash.app/${user}"),
        "steam":       lambda: check_url(f"https://steamcommunity.com/id/{user}"),
        "snapchat":    lambda: check_url(f"https://www.snapchat.com/add/{user}"),
        "soundcloud":  lambda: check_url(f"https://soundcloud.com/{user}"),
        "pinterest":   lambda: check_url(f"https://pinterest.com/{user}"),
    }

    fn = handlers.get(platform)
    if not fn:
        return {"platform": platform, "status": "unsupported"}

    try:
        return await fn()
    except Exception as e:
        return {"platform": platform, "status": "error", "error": str(e)}


async def check_url(url: str) -> dict:
    async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
        r = await client.get(url, headers=HEADERS)
    available = r.status_code in (404, 410)
    return {"status": "available" if available else "taken", "http_status": r.status_code}


async def check_discord(user: str) -> dict:
    if len(user) < 2 or len(user) > 32:
        return {"status": "invalid", "reason": "Length must be 2-32"}
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.post(
            "https://discord.com/api/v9/unique-username/username-attempt-unauthed",
            json={"username": user},
            headers={"Content-Type": "application/json"}
        )
    d = r.json()
    if d.get("taken") is False:
        return {"status": "available"}
    if d.get("taken") is True:
        return {"status": "taken"}
    return {"status": "error", "raw": d}


async def check_github(user: str) -> dict:
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(
            f"https://api.github.com/users/{user}",
            headers={"User-Agent": "DTOOLSBot"}
        )
    return {"status": "available" if r.status_code == 404 else "taken", "http_status": r.status_code}


async def check_reddit(user: str) -> dict:
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(
            f"https://www.reddit.com/user/{user}/about.json",
            headers={"User-Agent": "DTOOLSBot/1.0"}
        )
    if r.status_code == 404:
        return {"status": "available"}
    try:
        d = r.json()
        if d.get("error") == 404:
            return {"status": "available"}
    except Exception:
        pass
    return {"status": "taken"}


async def check_twitch(user: str) -> dict:
    async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
        r = await client.get(f"https://www.twitch.tv/{user}", headers=HEADERS)
    text = r.text
    available = "Sorry. Unless you" in text or "page not found" in text.lower() or r.status_code == 404
    return {"status": "available" if available else "taken", "http_status": r.status_code}


async def check_instagram(user: str) -> dict:
    async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
        r = await client.get(f"https://www.instagram.com/{user}/", headers=HEADERS)
    if r.status_code == 404:
        return {"status": "available"}
    available = "Page Not Found" in r.text or "Sorry, this page" in r.text
    return {"status": "available" if available else "taken", "http_status": r.status_code}


async def check_roblox(user: str) -> dict:
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(f"https://api.roblox.com/users/get-by-username?username={user}")
    d = r.json()
    if d.get("errorMessage") or not d.get("Id"):
        return {"status": "available"}
    return {"status": "taken", "id": d.get("Id")}


# ── IP LOOKUP ─────────────────────────────────────────────────
@app.get("/ip")
async def ip_lookup(request: Request, q: str = ""):
    ip = q.strip() or None

    # Fallback: get caller IP from headers
    if not ip:
        ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.headers.get("CF-Connecting-IP")
            or request.client.host
            or None
        )

    # Primary: ip-api.com
    try:
        fields = "status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,org,as,query"
        target = f"http://ip-api.com/json/{ip}?fields={fields}" if ip else f"http://ip-api.com/json/?fields={fields}"
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(target)
        d = r.json()
        if d.get("status") == "success":
            return JSONResponse({
                "ip":           d.get("query"),
                "country":      d.get("country"),
                "country_code": d.get("countryCode"),
                "region":       d.get("regionName"),
                "city":         d.get("city"),
                "postal":       d.get("zip"),
                "latitude":     d.get("lat"),
                "longitude":    d.get("lon"),
                "timezone":     d.get("timezone"),
                "isp":          d.get("isp"),
                "org":          d.get("org"),
                "asn":          d.get("as"),
            })
    except Exception:
        pass

    # Fallback: ipwho.is
    try:
        target2 = f"https://ipwho.is/{ip}" if ip else "https://ipwho.is/"
        async with httpx.AsyncClient(timeout=8) as client:
            r2 = await client.get(target2)
        d2 = r2.json()
        if d2.get("success"):
            conn = d2.get("connection", {})
            tz = d2.get("timezone", {})
            return JSONResponse({
                "ip":           d2.get("ip"),
                "country":      d2.get("country"),
                "country_code": d2.get("country_code"),
                "region":       d2.get("region"),
                "city":         d2.get("city"),
                "postal":       d2.get("postal"),
                "latitude":     d2.get("latitude"),
                "longitude":    d2.get("longitude"),
                "timezone":     tz.get("id") if isinstance(tz, dict) else tz,
                "isp":          conn.get("isp"),
                "org":          conn.get("org"),
                "asn":          f"AS{conn['asn']}" if conn.get("asn") else "—",
            })
    except Exception:
        pass

    return JSONResponse({"error": "IP lookup failed"}, status_code=500)


# ── WHOIS ─────────────────────────────────────────────────────
RDAP_SERVERS = {
    "com": "https://rdap.verisign.com/com/v1/",
    "net": "https://rdap.verisign.com/net/v1/",
    "org": "https://rdap.publicinterestregistry.org/rdap/",
    "io":  "https://rdap.nic.io/",
    "dev": "https://rdap.nic.dev/",
    "app": "https://rdap.nic.app/",
    "co":  "https://rdap.nic.co/",
    "fr":  "https://rdap.nic.fr/",
    "de":  "https://rdap.denic.de/",
    "uk":  "https://rdap.nominet.uk/",
    "ca":  "https://rdap.cira.ca/",
    "me":  "https://rdap.nic.me/",
    "gg":  "https://rdap.nic.gg/",
}


def parse_rdap(d: dict, domain: str) -> dict:
    def get_event(action):
        for e in d.get("events", []):
            if e.get("eventAction") == action:
                return e.get("eventDate", "—")
        return "—"

    ns = ", ".join(n.get("ldhName", "") for n in d.get("nameservers", [])) or "—"
    status = d.get("status", [])
    status_str = ", ".join(status) if isinstance(status, list) else str(status)

    registrar = "—"
    for entity in d.get("entities", []):
        if "registrar" in entity.get("roles", []):
            vcard = entity.get("vcardArray", [None, []])[1]
            for v in vcard:
                if v[0] == "fn":
                    registrar = v[3]
                    break

    return {
        "domain":      domain,
        "registrar":   registrar,
        "created":     get_event("registration"),
        "expires":     get_event("expiration"),
        "updated":     get_event("last changed"),
        "status":      status_str or "—",
        "nameservers": ns,
        "dnssec":      "Signed" if d.get("secureDNS", {}).get("delegationSigned") else "Unsigned",
        "source":      "rdap",
    }


@app.get("/whois")
async def whois(q: str = ""):
    domain = re.sub(r"^https?://", "", q.strip().lower())
    domain = re.sub(r"/.*", "", domain)

    if not domain:
        return JSONResponse({"error": "Missing domain"}, status_code=400)

    tld = domain.rsplit(".", 1)[-1]

    # Try RDAP first
    rdap_base = RDAP_SERVERS.get(tld)
    if rdap_base:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(f"{rdap_base}domain/{domain}")
            if r.is_success:
                return JSONResponse(parse_rdap(r.json(), domain))
        except Exception:
            pass

    # Fallback: whoisjson.com
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r2 = await client.get(
                f"https://whoisjson.com/api/v1/whois?domain={domain}",
                headers={"Authorization": "TOKEN=free"}
            )
        if r2.is_success:
            d2 = r2.json()
            ns = d2.get("name_servers", [])
            return JSONResponse({
                "domain":      domain,
                "registrar":   d2.get("registrar", "—"),
                "created":     d2.get("creation_date", "—"),
                "expires":     d2.get("expiration_date", "—"),
                "updated":     d2.get("updated_date", "—"),
                "status":      ", ".join(d2["status"]) if isinstance(d2.get("status"), list) else d2.get("status", "—"),
                "nameservers": ", ".join(ns) if isinstance(ns, list) else ns or "—",
                "dnssec":      d2.get("dnssec", "—"),
                "source":      "whoisjson",
            })
    except Exception:
        pass

    # Last resort: python-whois lib
    try:
        import whois as pywhois
        w = pywhois.whois(domain)
        def fmt(v):
            if isinstance(v, list): v = v[0]
            return str(v) if v else "—"
        return JSONResponse({
            "domain":      domain,
            "registrar":   fmt(w.registrar),
            "created":     fmt(w.creation_date),
            "expires":     fmt(w.expiration_date),
            "updated":     fmt(w.updated_date),
            "status":      fmt(w.status),
            "nameservers": ", ".join(w.name_servers) if w.name_servers else "—",
            "dnssec":      "—",
            "source":      "python-whois",
        })
    except Exception:
        pass

    return JSONResponse({"error": "WHOIS lookup failed for this domain"}, status_code=500)


# ── DISCORD INVITE ────────────────────────────────────────────
CHANNEL_TYPES = {0:"Text", 2:"Voice", 4:"Category", 5:"Announcement", 13:"Stage", 15:"Forum"}
VERIFY_LEVELS = ["Aucune", "Low", "Medium", "High", "Very High"]


@app.get("/invite")
async def invite(code: str = ""):
    code = re.sub(r".*discord\.gg/", "", code.strip(), flags=re.IGNORECASE)
    code = re.sub(r"\?.*", "", code)

    if not code:
        return JSONResponse({"error": "Missing invite code"}, status_code=400)

    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(
            f"https://discord.com/api/v9/invites/{code}?with_counts=true&with_expiration=true"
        )

    if r.status_code == 404:
        return JSONResponse({"valid": False, "code": code, "error": "Invite not found or expired"})
    if not r.is_success:
        return JSONResponse({"valid": False, "code": code, "error": f"Discord API error: {r.status_code}"})

    d = r.json()
    guild = d.get("guild", {})
    channel = d.get("channel", {})
    inviter = d.get("inviter", {})
    ch_type = channel.get("type")

    return JSONResponse({
        "valid":          True,
        "code":           code,
        "guild_id":       guild.get("id", "—"),
        "guild_name":     guild.get("name", "DM/Group"),
        "guild_desc":     guild.get("description") or "—",
        "guild_features": ", ".join(guild.get("features", [])) or "—",
        "verification":   VERIFY_LEVELS[guild.get("verification_level", 0)] if guild.get("verification_level", 0) < len(VERIFY_LEVELS) else "—",
        "nsfw":           "Oui" if guild.get("nsfw") else "Non",
        "member_count":   f"{d.get('approximate_member_count', 0):,}",
        "online_count":   f"{d.get('approximate_presence_count', 0):,}",
        "channel_name":   channel.get("name", "—"),
        "channel_type":   CHANNEL_TYPES.get(ch_type, f"Type {ch_type}"),
        "inviter":        f"{inviter.get('username', '—')}#{inviter.get('discriminator', '0')}" if inviter else "—",
        "inviter_id":     inviter.get("id", "—"),
        "expires_at":     d.get("expires_at") or "Jamais",
        "temporary":      "Oui" if d.get("temporary") else "Non",
        "max_uses":       str(d.get("max_uses")) if d.get("max_uses") else "Illimité",
        "uses":           str(d.get("uses", "—")),
    })
