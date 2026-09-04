"""Download link extraction and validation."""

import base64
import binascii
import json

import requests

from .core import BASE, DEAD_MARKERS, RE_PAIRS, RE_SERVERS, REDIRECTOR
from .http import http_get


def get_language(entry):
    try:
        return int(str(entry.get("lang", 1)).strip() or 1)
    except ValueError:
        return 1


def decode_entry(entry):
    server = str(entry.get("server", "")).strip()
    lang = get_language(entry)
    slug = str(entry.get("slug", "")).strip()
    try:
        remote = (
            base64.b64decode(entry.get("remote", "")).decode("utf-8", "replace").strip()
        )
    except binascii.Error, ValueError:
        remote = ""
    if server.lower() == "mediafire" and remote:
        url = remote.rstrip("/") + "/" + slug if slug else remote
        url = url.replace("://mediafire.com", "://www.mediafire.com")
        return server, lang, url, None
    return server, lang, None, (slug if remote or slug else None)


def parse_servers(html):
    entries = []
    m = RE_SERVERS.search(html)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, list):
                entries = [e for e in data if isinstance(e, dict)]
        except json.JSONDecodeError:
            pass
    if not entries:
        for rem, slg, srv in RE_PAIRS.findall(html):
            entries.append({"remote": rem, "slug": slg, "server": srv})
    return entries


def mediafire_alive(url):
    try:
        r = http_get(url, timeout=20)
    except requests.RequestException:
        return False
    if r.status_code != 200:
        return False
    body = r.text.lower()
    return not any(m in body for m in DEAD_MARKERS)


def mega_alive(url):
    if "/folder/" in url:
        return True
    handle = url.split("/file/", 1)[-1].split("#", 1)[0].split("?", 1)[0]
    handle = handle.strip("/")
    if not handle:
        return True
    try:
        r = requests.post(
            "https://g.api.mega.co.nz/cs",
            params={"id": "0"},
            data=json.dumps([{"a": "g", "p": handle}]),
            timeout=15,
        )
        data = r.json()
    except Exception:
        print(f"[!] Mega API request failed for: {url}")
        return False
    if isinstance(data, list) and data:
        d = data[0]
        if isinstance(d, int):
            if d < 0:
                print(f"[!] Mega link dead (API error {d}): {url}")
                return False
            return True
        if isinstance(d, dict):
            return "s" in d or "at" in d
    print(f"[!] Unexpected Mega API response: {data}")
    return False


def link_alive(url, server, verify):
    if not verify:
        return True
    low = url.lower()
    if "mediafire" in low:
        return mediafire_alive(url)
    if "mega.nz" in low:
        return mega_alive(url)
    return True


def resolve_redirector(slug):
    try:
        r = http_get(REDIRECTOR + slug + "/", timeout=25)
    except requests.RequestException:
        return None
    if r.status_code == 200 and "jkplayers" not in r.url:
        return r.url
    return None


def _try_group(group, primary, fallbacks, verify):
    primaries = []
    for e in group:
        server = str(e.get("server", "")).strip()
        if server.lower() == primary:
            _, _, direct_url, redirect_slug = decode_entry(e)
            size = str(e.get("size", "?")).strip()
            if direct_url:
                primaries.append((direct_url, server or primary, size))
            elif redirect_slug:
                final = resolve_redirector(redirect_slug)
                if final:
                    primaries.append((final, server or primary, size))
    if primaries:
        if not verify:
            return primaries, primaries[0][1], None
        alive = [d for d in primaries if link_alive(d[0], d[1], True)]
        if alive:
            return alive, alive[0][1], None
        reason = f"{primary} dead"
    else:
        reason = f"no {primary}"

    for fb in fallbacks:
        for e in group:
            server = str(e.get("server", "")).strip()
            if server.lower() == fb:
                _, _, direct_url, redirect_slug = decode_entry(e)
                size = str(e.get("size", "?")).strip()
                if direct_url and link_alive(direct_url, server or fb, verify):
                    return ([(direct_url, server or fb, size)], server or fb, reason)
                if redirect_slug:
                    final = resolve_redirector(redirect_slug)
                    if final and link_alive(final, server or fb, verify):
                        return ([(final, server or fb, size)], server or fb, reason)
    return [], None, reason


def choose_links(entries, primary, fallbacks, verify):
    preferred = [e for e in entries if get_language(e) == 1]
    links, server, reason = _try_group(preferred, primary, fallbacks, verify)
    if links:
        return links, server, reason, False
    alternate = [e for e in entries if get_language(e) != 1]
    if alternate:
        links, server, _ = _try_group(alternate, primary, fallbacks, verify)
        if links:
            return links, server, "only in another language", True
    return [], None, reason, False


def process_episode(slug, n, primary, fallbacks, verify, all_servers):
    url = f"{BASE}/{slug}/{n}/"
    try:
        r = http_get(url)
    except requests.RequestException as exc:
        return n, None, None, f"network error ({exc.__class__.__name__})", False
    if r.status_code == 404:
        return n, None, None, "404", False
    if r.status_code != 200:
        return n, None, None, f"HTTP {r.status_code}", False

    entries = parse_servers(r.text)
    if all_servers:
        result, seen = [], set()
        for e in entries:
            server, lang, direct_url, redirect_slug = decode_entry(e)
            if direct_url:
                final = direct_url
            elif redirect_slug:
                final = REDIRECTOR + redirect_slug + "/"
            else:
                continue
            if final not in seen:
                seen.add(final)
                result.append((final, server, str(e.get("size", "?")).strip()))
        if result:
            return n, result, "all", None, False
        return n, None, None, "no links", False

    links, used_server, reason, other_lang = choose_links(
        entries, primary, fallbacks, verify
    )
    if links:
        return n, links, used_server, reason, other_lang
    return n, None, None, reason or "no links", False
