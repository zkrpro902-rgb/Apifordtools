"""
DTOOLS — FastAPI Backend
Deploy sur Railway: railway up

Routes:
  GET /check?user=xxx&platform=discord   → username availability
  GET /ip?q=1.2.3.4                      → IP info (vide = IP du caller)
  GET /whois?q=domain.com               → WHOIS / RDAP info
  GET /invite?code=abcdef               → Discord invite info
  GET /health                           → status check
  POST /keys/verify                     → Vérifie une clé API
  POST /keys/generate                   → Génère une clé API
  POST /keys/revoke                     → Révoque une clé API
  GET /keys/list                        → Liste les clés API
"""

import asyncio
import re
import httpx
import sqlite3
import secrets
import string
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, Request
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

# ── IP LOOKUP ─────────────────────────────────────────────────
@app.get("/ip")
async def ip_lookup(request: Request, q: str = ""):
    # (le reste de la fonction reste inchangé)
    pass

# ── WHOIS ─────────────────────────────────────────────────────
@app.get("/whois")
async def whois(q: str = ""):
    # (le reste de la fonction reste inchangé)
    pass

# ── DISCORD INVITE ────────────────────────────────────────────
@app.get("/invite")
async def invite(code: str = ""):
    # (le reste de la fonction reste inchangé)
    pass

# ── KEY SYSTEM ────────────────────────────────────────────────
DB_PATH = os.getenv("KEYS_DB", "/tmp/dtools_keys.db")
BOT_SECRET = os.getenv("BOT_SECRET", "change_this_secret")

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            key         TEXT PRIMARY KEY,
            user_id     TEXT,
            username    TEXT,
            created_at  INTEGER,
            expires_at  INTEGER,
            max_uses    INTEGER DEFAULT -1,
            uses        INTEGER DEFAULT 0,
            active      INTEGER DEFAULT 1,
            note        TEXT DEFAULT ''
        )
    """)
    db.commit()
    return db

def gen_key():
    chars = string.ascii_uppercase + string.digits
    part = lambda n: ''.join(secrets.choice(chars) for _ in range(n))
    return f"DTOOLS-{part(4)}-{part(4)}-{part(4)}"

@app.post("/keys/verify")
async def verify_key(request: Request):
    try:
        data = await request.json()
        key = data.get("key","").strip().upper()
        if not key:
            return JSONResponse({"valid": False, "error": "Clé manquante"}, status_code=400)
        db = get_db()
        row = db.execute("SELECT * FROM keys WHERE key=?", (key,)).fetchone()
        db.close()
        if not row:
            return JSONResponse({"valid": False, "error": "Clé invalide"})
        if not row["active"]:
            return JSONResponse({"valid": False, "error": "Clé révoquée"})
        if row["expires_at"] and row["expires_at"] < int(time.time()):
            return JSONResponse({"valid": False, "error": "Clé expirée"})
        if row["max_uses"] != -1 and row["uses"] >= row["max_uses"]:
            return JSONResponse({"valid": False, "error": "Clé épuisée (max utilisations atteint)"})
        # Increment uses
        db = get_db()
        db.execute("UPDATE keys SET uses=uses+1 WHERE key=?", (key,))
        db.commit()
        db.close()
        expires = datetime.fromtimestamp(row["expires_at"]).strftime("%d/%m/%Y") if row["expires_at"] else "Jamais"
        return JSONResponse({
            "valid": True,
            "username": row["username"],
            "user_id": row["user_id"],
            "expires": expires,
            "uses": row["uses"] + 1,
            "max_uses": row["max_uses"],
        })
    except Exception as e:
        return JSONResponse({"valid": False, "error": str(e)}, status_code=500)

@app.post("/keys/generate")
async def generate_key(request: Request):
    try:
        data = await request.json()
        if data.get("secret") != BOT_SECRET:
            return JSONResponse({"ok": False, "error": "Secret invalide"}, status_code=403)
        user_id = str(data.get("user_id","unknown"))
        username = str(data.get("username","unknown"))
        expires_days = int(data.get("expires_days", 30))
        max_uses = int(data.get("max_uses", -1))
        note = str(data.get("note",""))
        key = gen_key()
        created = int(time.time())
        expires = created + expires_days * 86400 if expires_days > 0 else None
        db = get_db()
        db.execute(
            "INSERT INTO keys (key,user_id,username,created_at,expires_at,max_uses,uses,active,note) VALUES (?,?,?,?,?,?,0,1,?)",
            (key, user_id, username, created, expires, max_uses, note)
        )
        db.commit()
        db.close()
        expires_str = datetime.fromtimestamp(expires).strftime("%d/%m/%Y") if expires else "Jamais"
        return JSONResponse({"ok": True, "key": key, "expires": expires_str, "max_uses": max_uses})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/keys/list")
async def list_keys(secret: str = ""):
    if secret != BOT_SECRET:
        return JSONResponse({"ok": False, "error": "Secret invalide"}, status_code=403)
    db = get_db()
    rows = db.execute("SELECT * FROM keys ORDER BY created_at DESC LIMIT 100").fetchall()
    db.close()
    now = int(time.time())
    return JSONResponse({"ok": True, "keys": [
        {
            "key": r["key"], "username": r["username"], "user_id": r["user_id"],
            "active": bool(r["active"]),
            "expired": bool(r["expires_at"] and r["expires_at"] < now),
            "expires": datetime.fromtimestamp(r["expires_at"]).strftime("%d/%m/%Y") if r["expires_at"] else "Jamais",
            "uses": r["uses"], "max_uses": r["max_uses"],
            "created": datetime.fromtimestamp(r["created_at"]).strftime("%d/%m/%Y %H:%M"),
        } for r in rows
    ]})

@app.post("/keys/revoke")
async def revoke_key(request: Request):
    try:
        data = await request.json()
        if data.get("secret") != BOT_SECRET:
            return JSONResponse({"ok": False, "error": "Secret invalide"}, status_code=403)
        key = data.get("key","").strip().upper()
        db = get_db()
        db.execute("UPDATE keys SET active=0 WHERE key=?", (key,))
        db.commit()
        db.close()
        return JSONResponse({"ok": True, "revoked": key})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
