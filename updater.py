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

CHECKING_TEXT = "Wait sa ha kai mangita sa ta sa updates"

_POPUP_HTML = """
<style>
  .upd-overlay {
    position: fixed; inset: 0; z-index: 9999;
    display: flex; align-items: center; justify-content: center;
    background: radial-gradient(circle at 20% 20%, rgba(255,0,128,.35), transparent 50%),
                radial-gradient(circle at 80% 80%, rgba(0,200,255,.35), transparent 50%),
                rgba(10, 8, 30, .75);
    backdrop-filter: blur(8px);
    animation: upd-fade .3s ease-out;
    font-family: "Poppins", "Segoe UI", Roboto, sans-serif;
  }
  .upd-card {
    position: relative; padding: 36px 34px 30px; width: min(86vw, 340px);
    text-align: center; color: #fff; border-radius: 28px;
    background: linear-gradient(145deg, rgba(255,255,255,.16), rgba(255,255,255,.05));
    border: 1px solid rgba(255,255,255,.28);
    box-shadow: 0 20px 60px rgba(120, 40, 255, .45),
                inset 0 0 30px rgba(255,255,255,.08);
    animation: upd-pop .45s cubic-bezier(.2,1.4,.4,1);
  }
  .upd-card::before {
    content: ""; position: absolute; inset: -2px; z-index: -1; border-radius: 30px;
    background: linear-gradient(120deg, #ff0080, #ff8c00, #40e0d0, #7928ca, #ff0080);
    background-size: 300% 300%;
    animation: upd-flow 4s linear infinite;
    filter: blur(14px); opacity: .85;
  }
  .upd-spinner {
    width: 72px; height: 72px; margin: 0 auto 22px; border-radius: 50%;
    background: conic-gradient(from 0deg, #ff0080, #ff8c00, #ffe600, #00f5a0, #00d9f5, #7928ca, #ff0080);
    -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 9px), #000 calc(100% - 8px));
            mask: radial-gradient(farthest-side, transparent calc(100% - 9px), #000 calc(100% - 8px));
    animation: upd-spin 1s linear infinite;
    filter: drop-shadow(0 0 10px rgba(255,0,128,.7));
  }
  .upd-text {
    font-size: 18px; font-weight: 700; line-height: 1.4; letter-spacing: .3px;
    background: linear-gradient(90deg, #fff, #ffd1f3, #b8f3ff, #fff);
    background-size: 200% auto;
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: upd-shimmer 2.5s linear infinite;
  }
  .upd-dots { margin-top: 16px; display: flex; gap: 8px; justify-content: center; }
  .upd-dots span {
    width: 10px; height: 10px; border-radius: 50%;
    background: linear-gradient(135deg, #ff0080, #40e0d0);
    animation: upd-bounce 1.2s ease-in-out infinite;
  }
  .upd-dots span:nth-child(2) { animation-delay: .15s; }
  .upd-dots span:nth-child(3) { animation-delay: .3s; }

  @keyframes upd-fade    { from { opacity: 0 } to { opacity: 1 } }
  @keyframes upd-pop     { from { transform: scale(.7); opacity: 0 } to { transform: scale(1); opacity: 1 } }
  @keyframes upd-spin    { to { transform: rotate(360deg) } }
  @keyframes upd-flow    { 0% { background-position: 0% 50% } 100% { background-position: 300% 50% } }
  @keyframes upd-shimmer { to { background-position: 200% center } }
  @keyframes upd-bounce  { 0%, 80%, 100% { transform: translateY(0); opacity: .5 }
                           40% { transform: translateY(-10px); opacity: 1 } }
</style>
<div class="upd-overlay" id="upd-popup">
  <div class="upd-card">
    <div class="upd-spinner"></div>
    <div class="upd-text">__TEXT__</div>
    <div class="upd-dots"><span></span><span></span><span></span></div>
  </div>
</div>
"""


def popup_html(text=CHECKING_TEXT):
    """Return the styled 'checking for updates' popup as an HTML/CSS string."""
    return _POPUP_HTML.replace("__TEXT__", text)


def _ver(s):
    return tuple(int(p) for p in s.lstrip("vV").split(".") if p.isdigit())


def check(current_version, timeout=5):
    """Return {'version', 'url'} if a newer release exists, else None. Never raises."""
    try:
        req = Request(API, headers={"User-Agent": "numeracy-updater"})
        with urlopen(req, timeout=timeout, context=_CTX) as r:
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
