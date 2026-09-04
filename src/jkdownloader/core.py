"""Constants, regex patterns and shared HTTP session."""

import re

import requests

BASE = "https://jkanime.net"
REDIRECTOR = "https://c1.jkplayers.com/d/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
MAX_EP = 5000
RETRIES = 3
MAX_SEASONS = 12
DEAD_MARKERS = ("invalid or deleted", "file removed", "file deleted")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": UA,
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": BASE + "/",
})

RE_SERVERS = re.compile(r"var\s+servers\s*=\s*(\[.*?\])\s*;", re.S)
RE_PAIRS = re.compile(
    r'"remote"\s*:\s*"([^"]+)"[^{}]*?"slug"\s*:\s*"([^"]*)"[^{}]*?"server"\s*:\s*"([^"]+)"',
    re.S,
)
RE_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
RE_LINKS = re.compile(r'href="https://jkanime\.net/([a-z0-9-]{5,})/"')
