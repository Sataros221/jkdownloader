"""jkanime series analysis: validation, discovery and search."""

import re
from urllib.parse import urlparse

import requests

from .core import BASE, MAX_EP, MAX_SEASONS, RE_LINKS, RE_TITLE
from .http import episode_status_code, http_get


def normalize_series(text):
    text = text.strip().rstrip("/")
    if text.lower().startswith("http"):
        path = urlparse(text).path.strip("/")
        if not path:
            raise SystemExit(
                "[x] Invalid URL. Use the SERIES URL, e.g.:\n"
                "    https://jkanime.net/tensei-shitara-slime-datta-ken/"
            )
        return path.split("/")[0]
    return text.split("/")[0]


def validate_series(slug):
    r = http_get(f"{BASE}/{slug}/")
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise SystemExit(
            f"[x] jkanime returned HTTP {r.status_code} for series {slug}"
        )
    m = RE_TITLE.search(r.text)
    title = m.group(1).strip() if m else slug
    title = re.split(r"\s+-\s+anime\s", title)[0].strip()
    return title, r.text


def discover_family(slug):
    prefix = slug + "-"
    order = [slug]
    queue = [slug]
    while queue and len(order) < MAX_SEASONS:
        current = queue.pop(0)
        try:
            r = http_get(f"{BASE}/{current}/")
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        for cand in RE_LINKS.findall(r.text):
            if (
                cand.startswith(prefix)
                and cand not in order
                and len(order) < MAX_SEASONS
            ):
                order.append(cand)
                queue.append(cand)
    return order


def episode_exists(slug, n, cache):
    if n in cache:
        return cache[n]
    cache[n] = episode_status_code(slug, n) == 200
    return cache[n]


def find_last_episode(slug, cache):
    if not episode_exists(slug, 1, cache):
        return 0
    high = 2
    while high <= MAX_EP and episode_exists(slug, high, cache):
        high *= 2
    high = min(high, MAX_EP)
    low = max(1, high // 2)
    while low < high:
        mid = (low + high + 1) // 2
        if episode_exists(slug, mid, cache):
            low = mid
        else:
            high = mid - 1
    return low
