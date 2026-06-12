import json
import logging
import os
import threading
import time
import urllib.parse

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

DANBOORU_BASE_URL = "https://danbooru.donmai.us"
DANBOORU_HEADERS = {
    "User-Agent": "Danbooru-Gallery/1.0",
    "Accept": "application/json,*/*;q=0.8",
}
DANBOORU_CONNECTION_HELP = "连接服务器失败：需要配置VPN虚拟网卡（TUN）模式，或在启动器内设置使用系统代理。"

_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_TS = 0.0
_IMAGE_PROXY_SEMAPHORE = threading.Semaphore(3)
_MIN_REQUEST_INTERVAL = 0.2


def _repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _gallery_settings_path():
    return os.path.join(
        _repo_root(),
        "comfy",
        "custom_nodes",
        "ComfyUI-Danbooru-Gallery",
        "py",
        "danbooru_gallery",
        "settings.json",
    )


def _load_gallery_auth():
    path = _gallery_settings_path()
    try:
        if not os.path.exists(path):
            return "", ""
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return str(data.get("danbooru_username") or ""), str(data.get("danbooru_api_key") or "")
    except Exception as exc:
        logger.debug("Could not load Danbooru Gallery auth settings: %s", exc)
        return "", ""


def _proxy_setting():
    for key in ("SIMPLEAI_DANBOORU_PROXY", "DANBOORU_PROXY"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return key, value
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return key, value
    return "", ""


def _request_proxies():
    source, proxy_url = _proxy_setting()
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def _throttle():
    global _LAST_REQUEST_TS
    with _REQUEST_LOCK:
        now = time.monotonic()
        elapsed = now - _LAST_REQUEST_TS
        if elapsed < _MIN_REQUEST_INTERVAL:
            time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
        _LAST_REQUEST_TS = time.monotonic()


def _danbooru_request(method, url, **kwargs):
    headers = dict(kwargs.pop("headers", None) or {})
    for key, value in DANBOORU_HEADERS.items():
        headers.setdefault(key, value)
    proxies = kwargs.pop("proxies", None)
    if proxies is None:
        proxies = _request_proxies()

    response = None
    for attempt in range(2):
        _throttle()
        response = requests.request(method, url, headers=headers, proxies=proxies, **kwargs)
        if response.status_code not in (429, 503) or attempt == 1:
            return response
        retry_after = response.headers.get("Retry-After")
        delay = 2.0
        try:
            if retry_after is not None:
                delay = min(max(float(retry_after), 0.5), 10.0)
        except ValueError:
            pass
        time.sleep(delay)
    return response


def _normalize_query_tags(tags, rating=""):
    tokens = []
    date_tag = ""
    raw_tags = str(tags or "").replace(",", " ")
    for tag in raw_tags.split():
        token = tag.strip()
        if not token:
            continue
        if token.startswith("date:"):
            date_tag = token
        else:
            tokens.append(token)

    if len(tokens) > 2:
        tokens = tokens[:2]
    if date_tag:
        tokens.append(date_tag)

    rating_values = [
        item.strip().lower()
        for item in str(rating or "").replace("|", ",").split(",")
        if item.strip()
    ]
    rating_values = [item for item in rating_values if item not in {"all", "any"}]
    allowed = {"general", "sensitive", "questionable", "explicit", "g", "s", "q", "e"}
    rating_values = [item for item in rating_values if item in allowed]
    if len(rating_values) == 1:
        tokens.append(f"rating:{rating_values[0]}")
    elif len(rating_values) > 1:
        tokens.extend(f"~rating:{item}" for item in rating_values)

    return " ".join(tokens).strip()


def _error_payload(message, details="", status=502, **extra):
    payload = {
        "ok": False,
        "error": message,
        "details": details,
        "http_status": int(status or 500),
    }
    payload.update(extra)
    return payload


def _connection_error_payload(status=502, **extra):
    return _error_payload(DANBOORU_CONNECTION_HELP, "", status=status, network_error=True, **extra)


def proxy_status():
    source, proxy_url = _proxy_setting()
    return {
        "source": source,
        "configured": bool(proxy_url),
        "value": "configured" if proxy_url else "",
    }


def check_network():
    url = f"{DANBOORU_BASE_URL}/posts.json"
    try:
        response = _danbooru_request("GET", url, params={"limit": 1}, timeout=10)
        return {
            "ok": True,
            "connected": response.status_code == 200,
            "http_status": response.status_code,
            "proxy": proxy_status(),
        }
    except requests.exceptions.RequestException as exc:
        logger.warning("Danbooru network check failed: %s", exc)
        return {
            "ok": True,
            "connected": False,
            "network_error": True,
            "error": DANBOORU_CONNECTION_HELP,
            "details": "",
            "proxy": proxy_status(),
        }


def list_posts(query):
    query = query if isinstance(query, dict) else {}
    tags = str(query.get("search[tags]") or query.get("tags") or "")
    post_id = str(query.get("search[id]") or query.get("id") or "").strip()
    if post_id and post_id.isdigit():
        tags = f"id:{post_id}"
    rating = str(query.get("search[rating]") or query.get("rating") or "")
    try:
        limit = max(1, min(int(query.get("limit") or 40), 100))
    except Exception:
        limit = 40
    try:
        page = max(1, int(query.get("page") or 1))
    except Exception:
        page = 1

    username, api_key = _load_gallery_auth()
    auth = HTTPBasicAuth(username, api_key) if username and api_key else None
    params = {
        "tags": _normalize_query_tags(tags, rating=rating),
        "limit": limit,
        "page": page,
    }

    try:
        response = _danbooru_request(
            "GET",
            f"{DANBOORU_BASE_URL}/posts.json",
            params=params,
            auth=auth,
            timeout=15,
        )
    except requests.exceptions.RequestException as exc:
        logger.warning("Danbooru posts request failed: %s", exc)
        return _connection_error_payload(status=502, items=[], posts=[], proxy=proxy_status())

    if response.status_code != 200:
        details = response.text[:500] if response.text else response.reason
        return _error_payload(
            f"Danbooru HTTP {response.status_code}",
            details,
            status=response.status_code,
            items=[],
            posts=[],
            proxy=proxy_status(),
        )

    try:
        posts = response.json()
    except Exception as exc:
        return _error_payload("Danbooru response parse failed", str(exc), status=502, items=[], posts=[], proxy=proxy_status())
    if not isinstance(posts, list):
        posts = []

    has_more = len(posts) >= limit
    return {
        "ok": True,
        "items": posts,
        "posts": posts,
        "page": page,
        "limit": limit,
        "has_more": has_more,
        "next_page": page + 1 if has_more else None,
        "query_tags": params["tags"],
        "proxy": proxy_status(),
    }


def _validate_proxy_url(url):
    if not url:
        return False, "missing url", None
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False, "invalid url", None
    if parsed.scheme not in ("http", "https"):
        return False, "invalid scheme", None
    host = (parsed.hostname or "").lower()
    if host != "donmai.us" and not host.endswith(".donmai.us"):
        return False, "host not allowed", None
    return True, "", parsed


def proxy_media(url):
    valid, reason, _parsed = _validate_proxy_url(str(url or ""))
    if not valid:
        return _error_payload(reason, "", status=400 if reason != "host not allowed" else 403)

    with _IMAGE_PROXY_SEMAPHORE:
        try:
            response = _danbooru_request(
                "GET",
                url,
                timeout=20,
                headers={"Accept": "image/avif,image/webp,image/apng,image/*,video/*,*/*;q=0.8"},
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("Danbooru media proxy failed: %s", exc)
            return _connection_error_payload(status=502)

    if response.status_code != 200:
        return _error_payload(
            f"Danbooru media HTTP {response.status_code}",
            response.text[:300] if response.text else response.reason,
            status=response.status_code,
        )

    return {
        "ok": True,
        "content": response.content,
        "content_type": response.headers.get("Content-Type") or "application/octet-stream",
        "cache_control": response.headers.get("Cache-Control") or "public, max-age=86400",
        "status": 200,
    }
