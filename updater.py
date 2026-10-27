"""Checks GitHub Releases for a newer version of the Numeracy Drill app."""
import json
from urllib.request import urlopen, Request

REPO = "juliuscelio-del/numeracy-android"
API = "https://api.github.com/repos/%s/releases/latest" % REPO


def _ver(s):
    return tuple(int(p) for p in s.lstrip("vV").split(".") if p.isdigit())


def check(current_version, timeout=5):
    """Return {'version', 'url'} if a newer release exists, else None. Never raises."""
    try:
        req = Request(API, headers={"User-Agent": "numeracy-updater"})
        with urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        if _ver(data["tag_name"]) <= _ver(current_version):
            return None
        for a in data.get("assets", []):
            if a["name"].endswith(".apk"):
                return {"version": data["tag_name"].lstrip("vV"),
                        "url": a["browser_download_url"]}
    except Exception:
        pass  # offline, rate-limited, etc.: just skip
    return None
