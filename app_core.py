"""Shared by the desktop launcher and the Android app: data folder, teacher PIN, start/stop server, address cleanup."""
import os, sys, threading, importlib

if sys.stdout is None: sys.stdout = open(os.devnull, "w")
if sys.stderr is None: sys.stderr = open(os.devnull, "w")

DEFAULT_PORT = 8000
SCHOOL = "Guadalupe NHS"
APP_NAME = "Numeracy Drill"


def default_data_dir():
    """Where the teacher's data lives (never inside the app itself, so updating the app keeps the data)."""
    env = os.environ.get("NUMERACY_DATA")
    if env:
        return env
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    base = docs if os.path.isdir(docs) else os.path.expanduser("~")
    return os.path.join(base, "GNHS-Numeracy-Data")


def load_server(data_dir=None):
    """Import the server module (once). It reads NUMERACY_DATA at import time."""
    os.environ["NUMERACY_DATA"] = data_dir or default_data_dir()
    os.makedirs(os.environ["NUMERACY_DATA"], exist_ok=True)
    if "numeracy_server" in sys.modules:
        return sys.modules["numeracy_server"]
    return importlib.import_module("numeracy_server")


def has_saved_pin(srv):
    rec = srv.load_pin()
    srv.PIN_REC = rec
    return rec is not None


def create_pin(srv, pin):
    rec = srv.make_pin(pin)
    srv.save_pin(rec)
    srv.PIN_REC = rec


def check_pin(srv, pin):
    return srv.PIN_REC is not None and srv.pin_ok(pin)


class Host:
    """Runs the drill server in a background thread."""

    def __init__(self, srv, port=DEFAULT_PORT, ips_func=None):
        self.srv = srv
        self.ips_func = ips_func
        self.httpd = None
        self.port = None
        for p in range(port, port + 10):
            try:
                self.httpd = srv.make_server(p)
                self.port = p
                break
            except OSError:
                continue
        if self.httpd is None:
            raise OSError("No free port between %d and %d" % (port, port + 9))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def ips(self):
        try:
            found = self.ips_func() if self.ips_func else []
            return found or self.srv.ips()
        except Exception:
            return ["localhost"]

    def join_urls(self):
        return ["http://%s:%d" % (ip, self.port) for ip in self.ips()]

    def teacher_url(self):
        return "http://127.0.0.1:%d/host" % self.port

    def test_url(self):
        return "http://127.0.0.1:%d/test/host" % self.port

    def stop(self):
        try:
            self.srv._write_now()
        except Exception:
            pass
        try:
            self.srv.t_write_now()
        except Exception:
            pass
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass


def clean_address(text):
    """'192.168.1.5' -> 'http://192.168.1.5:8000'; keeps a typed port or full link."""
    t = (text or "").strip().replace(" ", "")
    if not t:
        return ""
    if "://" not in t:
        t = "http://" + t
    rest = t.split("://", 1)[1].split("/", 1)[0]
    if ":" not in rest:
        head, _, tail = t.partition(rest)
        t = head + rest + ":%d" % DEFAULT_PORT + tail
    return t
