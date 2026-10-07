"""RSS collector: sources (Supabase) → events."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import httpx
from dotenv import load_dotenv

TRACKING_PARAMS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})
YOUTUBE_CHANNEL_RE = re.compile(
    r"(?:youtube\.com/feeds/videos\.xml\?.*(?:channel_id|playlist_id)=)"
    r"(?P<id>UC[\w-]{22})",
    re.IGNORECASE,
)
HTTP = httpx.Client(
    headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "application/atom+xml;q=0.8,*/*;q=0.7"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    },
    # SOCS обходит экран consent.youtube.com («Before you continue…»).
    cookies={
        "CONSENT": "YES+1",
        "SOCS": "CAI",
    },
    timeout=60.0,
    follow_redirects=True,
)


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", urlencode(query), ""))


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_published(entry: dict[str, Any]) -> str | None:
    for key in ("published", "updated"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except (TypeError, ValueError, IndexError):
            pass
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if not struct:
            continue
        try:
            dt = datetime(*struct[:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except (TypeError, ValueError):
            pass
    return None


def entry_description(entry: dict[str, Any]) -> str | None:
    for key in ("summary", "description"):
        value = entry.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def youtube_channel_id(feed_url: str) -> str | None:
    match = YOUTUBE_CHANNEL_RE.search(feed_url)
    if match:
        return match.group("id")
    query = dict(parse_qsl(urlparse(feed_url).query))
    channel_id = query.get("channel_id") or ""
    if channel_id.startswith("UC") and len(channel_id) == 24:
        return channel_id
    playlist_id = query.get("playlist_id") or ""
    if playlist_id.startswith("UU") and len(playlist_id) >= 24:
        return "UC" + playlist_id[2:24]
    return None


def rows_from_feedparser(parsed: Any) -> list[dict[str, Any]]:
    collected_at = iso_now()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for entry in parsed.entries:
        link = entry.get("link")
        if not link:
            continue
        url = normalize_url(link)
        if not url or url in seen:
            continue
        seen.add(url)

        title = entry.get("title")
        if isinstance(title, str):
            title = title.strip() or None
        else:
            title = None

        description = entry_description(entry)
        metrics = {"description": description} if description else None

        rows.append(
            {
                "url": url,
                "title": title,
                "published_at": parse_published(entry),
                "collected_at": collected_at,
                "metrics": metrics,
            }
        )
    return rows


def collect_rss(feed_url: str) -> list[dict[str, Any]]:
    response = HTTP.get(feed_url)
    content_type = (response.headers.get("content-type") or "").lower()
    body = response.text

    if response.status_code != 200:
        raise RuntimeError(f"RSS HTTP {response.status_code}")
    if "html" in content_type or body.lstrip().lower().startswith("<!doctype"):
        raise RuntimeError("RSS вернул HTML вместо ленты")

    parsed = feedparser.parse(body)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        exc = getattr(parsed, "bozo_exception", None)
        raise RuntimeError(str(exc) if exc else "feed parse error")
    return rows_from_feedparser(parsed)


def extract_yt_initial_data(html: str) -> dict[str, Any] | None:
    marker = "ytInitialData"
    start = html.find(marker)
    if start < 0:
        return None
    start = html.find("{", start)
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for index in range(start, len(html)):
        ch = html[index]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(html[start : index + 1])
    return None


def yt_text(node: Any) -> str | None:
    if node is None:
        return None
    if isinstance(node, str):
        return node.strip() or None
    if isinstance(node, dict):
        if "content" in node and isinstance(node["content"], str):
            return node["content"].strip() or None
        if "simpleText" in node:
            return yt_text(node["simpleText"])
        runs = node.get("runs")
        if isinstance(runs, list):
            joined = "".join(
                str(part.get("text", "")) for part in runs if isinstance(part, dict)
            ).strip()
            return joined or None
    return None


def _video_id_from_node(node: dict[str, Any]) -> str | None:
    if isinstance(node.get("videoId"), str) and node["videoId"]:
        return node["videoId"]
    content_id = node.get("contentId")
    if isinstance(content_id, str) and content_id and " " not in content_id:
        return content_id
    entity = node.get("entityId")
    if isinstance(entity, str) and entity.startswith("shorts-shelf-item-"):
        return entity.removeprefix("shorts-shelf-item-")
    on_tap = node.get("onTap") or {}
    command = on_tap.get("innertubeCommand") or {}
    for key in ("reelWatchEndpoint", "watchEndpoint"):
        endpoint = command.get(key) or {}
        video_id = endpoint.get("videoId")
        if isinstance(video_id, str) and video_id:
            return video_id
    return None


def _title_from_node(node: dict[str, Any]) -> str | None:
    title = yt_text(node.get("title"))
    if title:
        return title
    metadata = node.get("metadata") or {}
    if isinstance(metadata, dict):
        lockup_meta = metadata.get("lockupMetadataViewModel") or {}
        if isinstance(lockup_meta, dict):
            title = yt_text(lockup_meta.get("title"))
            if title:
                return title
    overlay = node.get("overlayMetadata") or {}
    if isinstance(overlay, dict):
        title = yt_text(overlay.get("primaryText"))
        if title:
            return title
    a11y = node.get("accessibilityText")
    if isinstance(a11y, str) and a11y.strip():
        # "Title, 45 million views - play Short"
        return a11y.split(",", 1)[0].strip() or None
    return None


def _description_from_node(node: dict[str, Any]) -> str | None:
    for key in ("descriptionSnippet", "description"):
        text = yt_text(node.get(key))
        if text:
            return text
    a11y = node.get("accessibilityText")
    if isinstance(a11y, str) and a11y.strip():
        return a11y.strip()
    return None


def _published_relative_from_node(node: dict[str, Any]) -> str | None:
    text = yt_text(node.get("publishedTimeText"))
    if text:
        return text
    metadata = node.get("metadata") or {}
    if not isinstance(metadata, dict):
        return None
    lockup_meta = metadata.get("lockupMetadataViewModel") or {}
    if not isinstance(lockup_meta, dict):
        return None
    content_meta = (lockup_meta.get("metadata") or {}).get(
        "contentMetadataViewModel"
    ) or {}
    rows = content_meta.get("metadataRows") or []
    for row in rows:
        for part in row.get("metadataParts") or []:
            label = part.get("accessibilityLabel") or yt_text(part.get("text"))
            if isinstance(label, str) and (
                "ago" in label.lower() or "назад" in label.lower()
            ):
                return label
    return None


def walk_video_nodes(obj: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        for key in (
            "videoRenderer",
            "gridVideoRenderer",
            "reelItemRenderer",
            "shortsLockupViewModel",
            "lockupViewModel",
        ):
            node = obj.get(key)
            if isinstance(node, dict):
                out.append(node)
        for value in obj.values():
            walk_video_nodes(value, out)
    elif isinstance(obj, list):
        for value in obj:
            walk_video_nodes(value, out)


def rows_from_channel_data(data: dict[str, Any], *, shorts: bool) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    walk_video_nodes(data, nodes)
    collected_at = iso_now()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for node in nodes:
        video_id = _video_id_from_node(node)
        if not video_id:
            continue
        content_type = node.get("contentType")
        use_shorts = shorts or content_type == "LOCKUP_CONTENT_TYPE_SHORTS"
        if use_shorts:
            url = normalize_url(f"https://www.youtube.com/shorts/{video_id}")
        else:
            url = normalize_url(f"https://www.youtube.com/watch?v={video_id}")
        if url in seen:
            continue
        seen.add(url)

        title = _title_from_node(node)
        description = _description_from_node(node)
        published_relative = _published_relative_from_node(node)
        metrics: dict[str, Any] = {}
        if description:
            metrics["description"] = description
        if published_relative:
            metrics["published_relative"] = published_relative

        rows.append(
            {
                "url": url,
                "title": title,
                "published_at": None,
                "collected_at": collected_at,
                "metrics": metrics or None,
            }
        )
    return rows


def collect_channel_page(channel_id: str) -> list[dict[str, Any]]:
    """Разбор HTML вкладки Shorts (и при необходимости Videos) канала."""
    errors: list[str] = []
    for path, shorts in (("/shorts", True), ("/videos", False)):
        url = f"https://www.youtube.com/channel/{channel_id}{path}"
        try:
            response = HTTP.get(url)
        except httpx.HTTPError as exc:
            errors.append(f"{path}: {exc}")
            continue
        if response.status_code != 200:
            errors.append(f"{path}: HTTP {response.status_code}")
            continue
        data = extract_yt_initial_data(response.text)
        if not data:
            errors.append(f"{path}: нет ytInitialData")
            continue
        rows = rows_from_channel_data(data, shorts=shorts)
        if rows:
            return rows
        errors.append(f"{path}: карточек не найдено")
    raise RuntimeError(
        "парсинг страницы канала не дал роликов (" + "; ".join(errors) + ")"
    )


def collect_youtube_api(channel_id: str, api_key: str) -> list[dict[str, Any]]:
    """Uploads playlist: UC… → UU… (опционально, если ключ задан)."""
    playlist_id = "UU" + channel_id[2:]
    response = HTTP.get(
        "https://www.googleapis.com/youtube/v3/playlistItems",
        params={
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": "15",
            "key": api_key,
        },
    )
    if response.status_code != 200:
        detail = response.text[:200].replace("\n", " ")
        raise RuntimeError(f"YouTube API HTTP {response.status_code}: {detail}")

    data = response.json()
    collected_at = iso_now()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in data.get("items") or []:
        snippet = item.get("snippet") or {}
        details = item.get("contentDetails") or {}
        video_id = details.get("videoId") or (snippet.get("resourceId") or {}).get(
            "videoId"
        )
        if not video_id:
            continue
        url = normalize_url(f"https://www.youtube.com/watch?v={video_id}")
        if url in seen:
            continue
        seen.add(url)

        title = snippet.get("title")
        if isinstance(title, str):
            title = title.strip() or None
        else:
            title = None

        description = snippet.get("description")
        if isinstance(description, str):
            description = description.strip() or None
        else:
            description = None

        rows.append(
            {
                "url": url,
                "title": title,
                "published_at": snippet.get("publishedAt"),
                "collected_at": collected_at,
                "metrics": {"description": description} if description else None,
            }
        )
    return rows


def collect_feed(feed_url: str, youtube_api_key: str = "") -> list[dict[str, Any]]:
    channel_id = youtube_channel_id(feed_url)
    try:
        return collect_rss(feed_url)
    except RuntimeError as rss_error:
        if not channel_id:
            raise rss_error
        try:
            return collect_channel_page(channel_id)
        except RuntimeError as page_error:
            if youtube_api_key:
                return collect_youtube_api(channel_id, youtube_api_key)
            raise RuntimeError(f"{rss_error}; {page_error}") from page_error


class Supabase:
    def __init__(self, base_url: str, key: str) -> None:
        self._rest = base_url.rstrip("/") + "/rest/v1"
        self._client = httpx.Client(
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    def close(self) -> None:
        self._client.close()

    def list_rss_sources(self) -> list[dict[str, Any]]:
        response = self._client.get(
            f"{self._rest}/sources",
            params={
                "select": "id,url,consecutive_errors",
                "enabled": "eq.true",
                "kind": "eq.rss",
                "order": "id.asc",
            },
        )
        response.raise_for_status()
        return response.json()

    def patch_source(self, source_id: int, payload: dict[str, Any]) -> None:
        response = self._client.patch(
            f"{self._rest}/sources",
            params={"id": f"eq.{source_id}"},
            json=payload,
        )
        response.raise_for_status()

    def insert_events(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        response = self._client.post(
            f"{self._rest}/events",
            params={"on_conflict": "url"},
            headers={
                "Prefer": "resolution=ignore-duplicates,return=representation",
            },
            json=rows,
        )
        response.raise_for_status()
        data = response.json()
        return len(data) if isinstance(data, list) else 0


def main() -> int:
    load_dotenv()
    base_url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    youtube_api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not base_url or not key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env", file=sys.stderr)
        return 1

    db = Supabase(base_url, key)
    total_found = 0
    total_written = 0

    try:
        sources = db.list_rss_sources()
    except httpx.HTTPError as exc:
        print(f"Failed to load sources: {exc}", file=sys.stderr)
        db.close()
        return 1

    if not sources:
        print(
            "No RSS sources: table sources has no rows with enabled=true and kind='rss'. "
            "Run db/002_sources.sql."
        )
        db.close()
        print("total_sources=0 found=0 written=0")
        return 0

    for source in sources:
        source_id = source["id"]
        feed_url = source["url"]
        errors = int(source.get("consecutive_errors") or 0)
        fetched_at = iso_now()

        try:
            db.patch_source(source_id, {"last_fetched_at": fetched_at})
            items = collect_feed(feed_url, youtube_api_key)
            rows = [{**item, "source_id": source_id} for item in items]
            written = db.insert_events(rows)
            db.patch_source(
                source_id,
                {
                    "last_success_at": iso_now(),
                    "consecutive_errors": 0,
                },
            )
            found = len(items)
            print(f"{feed_url}  found={found}  written={written}")
            total_found += found
            total_written += written
        except Exception as exc:  # noqa: BLE001 — per-source report, continue
            try:
                db.patch_source(
                    source_id,
                    {"consecutive_errors": errors + 1},
                )
            except httpx.HTTPError:
                pass
            print(f"{feed_url}  found=0  written=0  error={exc}")

    db.close()
    HTTP.close()
    print(
        f"total_sources={len(sources)} found={total_found} written={total_written}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
