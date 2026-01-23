"""Scrapers específicos (Fase 2).

Objetivo:
- Extraer metadata de alta calidad en fuentes con APIs estables.
- Reducir scraping HTML cuando hay endpoints JSON oficiales.

Estos scrapers están en adapters porque son I/O puro (HTTP).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from adapters.http_client import build_async_client
from core.config import AppSettings


async def fetch_github_user(*, username: str, settings: AppSettings | None = None) -> dict[str, Any] | None:
    settings = settings or AppSettings()
    url = f"https://api.github.com/users/{username}"
    headers = {
        # GitHub requiere UA. Accept JSON versión estable.
        "Accept": "application/vnd.github+json",
    }

    async with build_async_client(settings, extra_headers=headers) as client:
        resp = await client.get(url)

    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        return None

    data = resp.json()
    # Campos útiles (si existen)
    return {
        "api": "github",
        "login": data.get("login"),
        "name": data.get("name"),
        "bio": data.get("bio"),
        "company": data.get("company"),
        "location": data.get("location"),
        "blog": data.get("blog"),
        "email": data.get("email"),
        "twitter_username": data.get("twitter_username"),
        "avatar_url": data.get("avatar_url"),
        "html_url": data.get("html_url"),
        "public_repos": data.get("public_repos"),
        "followers": data.get("followers"),
        "following": data.get("following"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    }


async def fetch_github_recent_events(
    *,
    username: str,
    limit: int = 10,
    settings: AppSettings | None = None,
) -> list[dict[str, Any]]:
    """Extrae eventos públicos recientes (útil para commits en PushEvent).

    Nota:
    - Es público y puede estar rate-limited sin token.
    - No inferimos atributos sensibles; solo capturamos evidencia textual/temporal.
    """

    settings = settings or AppSettings()
    url = f"https://api.github.com/users/{username}/events/public"
    headers = {"Accept": "application/vnd.github+json"}

    try:
        async with build_async_client(settings, extra_headers=headers) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if not isinstance(data, list):
            return []
        out: list[dict[str, Any]] = []
        for ev in data[: max(0, int(limit))]:
            if not isinstance(ev, dict):
                continue
            out.append(ev)
        return out
    except Exception:
        return []


async def fetch_github_deep(
    *,
    username: str,
    limit_events: int = 10,
    settings: AppSettings | None = None,
) -> dict[str, Any] | None:
    """Combina perfil base + actividad reciente (mensajes de commits si hay PushEvent)."""

    settings = settings or AppSettings()
    base = await fetch_github_user(username=username, settings=settings)
    if base is None:
        return None

    events = await fetch_github_recent_events(username=username, limit=limit_events, settings=settings)
    commits: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("type") != "PushEvent":
            continue
        created_at = ev.get("created_at")
        payload = ev.get("payload")
        if not isinstance(payload, dict):
            continue
        for c in payload.get("commits") or []:
            if not isinstance(c, dict):
                continue
            msg = c.get("message")
            if not isinstance(msg, str) or not msg.strip():
                continue
            commits.append({"message": msg.strip(), "timestamp": created_at})

    return {
        **base,
        "recent_commits": commits[:20],
    }


async def fetch_reddit_user_about(*, username: str, settings: AppSettings | None = None) -> dict[str, Any] | None:
    settings = settings or AppSettings()
    url = f"https://www.reddit.com/user/{username}/about.json"

    # Reddit suele exigir UA decente.
    headers = {
        "Accept": "application/json",
        # Reddit suele bloquear UAs “raros”. Forzamos un UA compatible.
        "User-Agent": "Mozilla/5.0 (compatible; OSINT-D2/1.0)",
    }

    async with build_async_client(settings, extra_headers=headers) as client:
        resp = await client.get(url)

    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        return None

    data = resp.json()
    if not isinstance(data, dict):
        return None

    payload = data.get("data")
    if not isinstance(payload, dict):
        return None

    subreddit = payload.get("subreddit")
    if not isinstance(subreddit, dict):
        subreddit = {}

    created_utc = payload.get("created_utc")
    created_iso = None
    if isinstance(created_utc, (int, float)):
        created_iso = datetime.fromtimestamp(float(created_utc), tz=timezone.utc).isoformat()

    return {
        "api": "reddit",
        "name": payload.get("name"),
        "id": payload.get("id"),
        "created_utc": created_utc,
        "created_at": created_iso,
        "public_description": subreddit.get("public_description"),
        "title": subreddit.get("title"),
        "icon_img": subreddit.get("icon_img"),
        "banner_img": subreddit.get("banner_img"),
        "over_18": subreddit.get("over_18"),
        "subscribers": subreddit.get("subscribers"),
    }


async def fetch_reddit_recent_comments(
    *,
    username: str,
    limit: int = 10,
    settings: AppSettings | None = None,
) -> dict[str, Any] | None:
    """Extrae comentarios recientes (texto crudo + subreddit).

    Nota:
    - Solo datos públicos.
    - Puede devolver 429/403 dependiendo de Reddit.
    """

    settings = settings or AppSettings()
    url = f"https://www.reddit.com/user/{username}/comments.json?limit={max(1, int(limit))}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; OSINT-D2/1.0)",
    }

    try:
        async with build_async_client(settings, extra_headers=headers) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, dict):
            return None
        payload = data.get("data")
        if not isinstance(payload, dict):
            return None
        children = payload.get("children")
        if not isinstance(children, list):
            return None

        comments: list[dict[str, Any]] = []
        subreddits: set[str] = set()
        for child in children:
            if not isinstance(child, dict):
                continue
            c = child.get("data")
            if not isinstance(c, dict):
                continue
            body = c.get("body")
            if not isinstance(body, str) or not body.strip():
                continue
            sr = c.get("subreddit")
            if isinstance(sr, str) and sr:
                subreddits.add(sr)
            comments.append(
                {
                    "body": body,
                    "subreddit": sr,
                    "created_utc": c.get("created_utc"),
                    "permalink": c.get("permalink"),
                }
            )

        return {"recent_comments": comments, "subreddits": sorted(subreddits)}
    except Exception:
        return None


async def fetch_reddit_deep(
    *,
    username: str,
    limit_comments: int = 10,
    settings: AppSettings | None = None,
) -> dict[str, Any] | None:
    """Combina about.json + comentarios recientes."""

    settings = settings or AppSettings()
    about = await fetch_reddit_user_about(username=username, settings=settings)
    if about is None:
        return None

    comments = await fetch_reddit_recent_comments(username=username, limit=limit_comments, settings=settings)
    return {
        **about,
        **(comments or {}),
    }
