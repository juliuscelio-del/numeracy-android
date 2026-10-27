"""Checks GitHub Releases for a newer version of the Numeracy Drill app."""
import json
import ssl
from urllib.request import urlopen, Request

try:
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _CTX = None

REPO = "juliuscelio-del/numeracy-android"
API = "https://api.github.com/repos/%s/releases/latest" % REPO

# Filled in by check() so the app can show what happened (for debugging).
last_error = None   # e.g. "URLError: certificate verify failed"
last_tag = None     # latest release tag found on GitHub, e.g. "v1.0.3"


def _ver(s):
    return tuple(int(p) for p in s.lstrip("vV").split(".") if p.isdigit())


def check(current_version, timeout=8):
    """Return {'version', 'url'} if a newer release exists, else None. Never raises."""
    global last_error, last_tag
    last_error = None
    last_tag = None
    try:
        req = Request(API, headers={"User-Agent": "numeracy-updater"})
        with urlopen(req, timeout=timeout, context=_CTX) as r:
            data = json.load(r)
        last_tag = data["tag_name"]
        if _ver(last_tag) <= _ver(current_version):
            return None
        for a in data.get("assets", []):
            if a["name"].endswith(".apk"):
                return {"version": last_tag.lstrip("vV"),
                        "url": a["browser_download_url"]}
        last_error = "Latest release has no .apk asset"
    except Exception as e:
        last_error = "%s: %s" % (type(e).__name__, e)  # offline, SSL, rate-limited, etc.
    return None
