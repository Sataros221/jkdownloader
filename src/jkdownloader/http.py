"""HTTP utilities with retry and automatic cloudscraper fallback."""

import time

import requests

from .core import BASE, RETRIES, SESSION


def activate_cloudscraper():
    global SESSION
    try:
        import cloudscraper

        new_session = cloudscraper.create_scraper()
        new_session.headers.update(
            {"Accept-Language": "es-ES,es;q=0.9", "Referer": BASE + "/"}
        )
        SESSION = new_session
        print("[!] Block detected (403/503): retrying with cloudscraper...")
        return True
    except ImportError:
        return False


def http_get(url, timeout=25, stream=False):
    last_error = None
    r = None
    for attempt in range(RETRIES):
        try:
            r = SESSION.get(url, timeout=timeout, stream=stream)
            if r.status_code in (403, 503) and attempt == 0:
                if activate_cloudscraper():
                    continue
            return r
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    if last_error:
        raise last_error
    return r


def episode_status_code(slug, n):
    url = f"{BASE}/{slug}/{n}/"
    try:
        with SESSION.get(url, timeout=25, stream=True) as r:
            return r.status_code
    except requests.RequestException:
        r = http_get(url)
        return r.status_code
