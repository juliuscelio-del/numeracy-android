"""Guadalupe NHS Numeracy Drill: Android app (Kivy).
Start screen: TEACHER (PIN, this phone runs the drill) or STUDENT (join the teacher's address).
The drill itself is a web page, shown inside a WebView."""
import os, sys, threading, traceback, time, math, colorsys
from kivy.app import App
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.graphics import Color, RoundedRectangle, Ellipse, Line, PushMatrix, PopMatrix, Rotate
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.uix.modalview import ModalView
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.utils import get_color_from_hex as hexc

import app_core as core

try:
    from _version import __version__
except ImportError:
    __version__ = "0.0.0"
import updater

SCAN_SECONDS = 15   # the "searching for updates" popup stays at least this long
CHECKING_TEXT = "Wait sa ha kai mangita sa ta sa updates"
UPDATING_TEXT = "Paabot kadali sa downloadon pa ag updates"   # shown while the update downloads and installs
DEBUG_UPDATER = False   # True: show why an update check failed. Set to False when everything works.

BLUE, GREEN, RED, PURPLE, GREY = "#2f6df6", "#1fc76a", "#ff5a5f", "#8b5cf6", "#7b8db3"
INK, MUTED, BG = "#12306b", "#5f78a8", "#e4f1ff"
WHITE = "#ffffff"
Window.clearcolor = hexc(BG)

# ------------------------------------------------------------------ Android helpers (pyjnius)
try:
    from jnius import autoclass, PythonJavaClass, java_method
    from android.runnable import run_on_ui_thread
    ANDROID = True
except Exception:
    ANDROID = False

    def run_on_ui_thread(f):
        return f

_wv = {"view": None}


def _activity():
    return autoclass("org.kivy.android.PythonActivity").mActivity


def keep_screen_on():
    if not ANDROID:
        return

    @run_on_ui_thread
    def _do():
        try:
            _activity().getWindow().addFlags(128)  # FLAG_KEEP_SCREEN_ON
        except Exception:
            traceback.print_exc()
    _do()


_mlock = {"lock": None}


def multicast_lock(on):
    """Some phones ignore broadcast packets unless the app holds this lock."""
    if not ANDROID:
        return
    try:
        if on:
            Context = autoclass("android.content.Context")
            wm = _activity().getSystemService(Context.WIFI_SERVICE)
            lk = wm.createMulticastLock("numeracy")
            lk.setReferenceCounted(False)
            lk.acquire()
            _mlock["lock"] = lk
        elif _mlock["lock"] is not None:
            _mlock["lock"].release()
            _mlock["lock"] = None
    except Exception:
        traceback.print_exc()


def get_ips():
    """Wi-Fi / hotspot addresses of this phone (works even when it is the hotspot)."""
    out = []
    if not ANDROID:
        return out
    try:
        NI = autoclass("java.net.NetworkInterface")
        en = NI.getNetworkInterfaces()
        while en.hasMoreElements():
            ni = en.nextElement()
            if not ni.isUp() or ni.isLoopback():
                continue
            addrs = ni.getInetAddresses()
            while addrs.hasMoreElements():
                a = addrs.nextElement()
                if a.isLoopbackAddress() or a.getHostAddress().count(".") != 3:
                    continue
                out.append(a.getHostAddress())
    except Exception:
        traceback.print_exc()
    return out


if ANDROID:
    class _Downloader(PythonJavaClass):
        """Downloads (PDF / reports) open in the phone's own browser, which knows how to save them."""
        __javainterfaces__ = ["android/webkit/DownloadListener"]
        __javacontext__ = "app"

        @java_method("(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;J)V")
        def onDownloadStart(self, url, ua, disp, mime, length):
            try:
                Intent = autoclass("android.content.Intent")
                Uri = autoclass("android.net.Uri")
                i = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                _activity().startActivity(i)
            except Exception:
                traceback.print_exc()


def open_url(url):
    """Open a link in the phone's own browser (used for downloading the update)."""
    if not ANDROID:
        import webbrowser
        webbrowser.open(url)
        return
    try:
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        _activity().startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    except Exception:
        traceback.print_exc()


# ---- in-app update: download with Android's DownloadManager, then open the system installer
APK_NAME = "numeracy-update.apk"
APK_MIME = "application/vnd.android.package-archive"


def can_install_apks():
    """True if the user already allowed this app to install APKs (Android 8+)."""
    if not ANDROID:
        return True
    try:
        return bool(_activity().getPackageManager().canRequestPackageInstalls())
    except Exception:
        traceback.print_exc()
        return True


def open_install_permission_settings():
    """Opens the 'Install unknown apps' switch for this app."""
    try:
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        Settings = autoclass("android.provider.Settings")
        act = _activity()
        act.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                 Uri.parse("package:" + act.getPackageName())))
    except Exception:
        traceback.print_exc()


def cleanup_old_apk():
    """Deletes a previously downloaded update file."""
    if not ANDROID:
        return
    try:
        File = autoclass("java.io.File")
        Environment = autoclass("android.os.Environment")
        d = _activity().getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
        if d is not None:
            f = File(d, APK_NAME)
            if f.exists():
                f.delete()
    except Exception:
        traceback.print_exc()


def start_apk_download(url):
    """Queues the APK in Android's DownloadManager. Returns the download id."""
    Request = autoclass("android.app.DownloadManager$Request")
    Uri = autoclass("android.net.Uri")
    Context = autoclass("android.content.Context")
    Environment = autoclass("android.os.Environment")
    act = _activity()
    req = Request(Uri.parse(url))
    req.setTitle("Numeracy Drill update")
    req.setMimeType(APK_MIME)
    req.setDestinationInExternalFilesDir(act, Environment.DIRECTORY_DOWNLOADS, APK_NAME)
    dm = act.getSystemService(Context.DOWNLOAD_SERVICE)
    return dm.enqueue(req)


def download_progress(did):
    """Returns (status, bytes_done, bytes_total); status is 'running', 'done' or 'failed'."""
    DM = autoclass("android.app.DownloadManager")
    Query = autoclass("android.app.DownloadManager$Query")
    Context = autoclass("android.content.Context")
    dm = _activity().getSystemService(Context.DOWNLOAD_SERVICE)
    q = Query()
    try:
        q.setFilterById([did])
    except Exception:
        q.setFilterById(did)
    c = dm.query(q)
    try:
        if not c.moveToFirst():
            return "failed", 0, 0
        status = c.getInt(c.getColumnIndex(DM.COLUMN_STATUS))
        done = c.getLong(c.getColumnIndex(DM.COLUMN_BYTES_DOWNLOADED_SO_FAR))
        total = c.getLong(c.getColumnIndex(DM.COLUMN_TOTAL_SIZE_BYTES))
    finally:
        c.close()
    if status == DM.STATUS_SUCCESSFUL:
        return "done", done, total
    if status == DM.STATUS_FAILED:
        return "failed", done, total
    return "running", done, total


def install_downloaded_apk(did):
    """Opens Android's installer for the downloaded APK."""
    Intent = autoclass("android.content.Intent")
    Context = autoclass("android.content.Context")
    act = _activity()
    dm = act.getSystemService(Context.DOWNLOAD_SERVICE)
    uri = dm.getUriForDownloadedFile(did)
    if uri is None:
        raise RuntimeError("downloaded file not found")
    i = Intent(Intent.ACTION_VIEW)
    i.setDataAndType(uri, APK_MIME)
    i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_GRANT_READ_URI_PERMISSION)
    act.startActivity(i)


@run_on_ui_thread
def open_webview(url):
    if not ANDROID:
        import webbrowser
        webbrowser.open(url)
        return
    try:
        close_webview_now()
        WebView = autoclass("android.webkit.WebView")
        WebViewClient = autoclass("android.webkit.WebViewClient")
        LayoutParams = autoclass("android.view.ViewGroup$LayoutParams")
        act = _activity()
        wv = WebView(act)
        s = wv.getSettings()
        s.setJavaScriptEnabled(True)
        s.setDomStorageEnabled(True)
        s.setBuiltInZoomControls(False)
        wv.setWebViewClient(WebViewClient())
        wv._dl = _Downloader()  # keep a reference so it is not garbage collected
        wv.setDownloadListener(wv._dl)
        act.addContentView(wv, LayoutParams(-1, -1))
        wv.loadUrl(url)
        _wv["view"] = wv
    except Exception:
        traceback.print_exc()


def close_webview_now():
    wv = _wv.get("view")
    if wv is not None:
        try:
            wv.getParent().removeView(wv)
            wv.destroy()
        except Exception:
            pass
        _wv["view"] = None


@run_on_ui_thread
def close_webview():
    close_webview_now()


@run_on_ui_thread
def webview_back():
    wv = _wv.get("view")
    if wv is None:
        return
    try:
        if wv.canGoBack():
            wv.goBack()
        else:
            close_webview_now()
    except Exception:
        close_webview_now()


# ------------------------------------------------------------------ UI
def big_button(text, color, on_press, height=64):
    b = Button(text=text, size_hint_y=None, height=dp(height), font_size=sp(18), bold=True,
               background_normal="", background_color=hexc(color), color=(1, 1, 1, 1))
    b.bind(on_release=lambda *_: on_press())
    return b


def text(txt, size=15, color=INK, bold=False, height=None, halign="center"):
    lb = Label(text=txt, font_size=sp(size), color=hexc(color), bold=bold, halign=halign, valign="middle",
               size_hint_y=None)
    lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    lb.bind(texture_size=lambda w, ts: setattr(w, "height", max(ts[1] + dp(8), dp(height or 0))))
    return lb


def box():
    return BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(12))


def field(hint, password=False, value=""):
    return TextInput(hint_text=hint, text=value, password=password, multiline=False, size_hint_y=None,
                     height=dp(56), font_size=sp(20), halign="center", padding=[dp(10), dp(14)])


def hsv(h, s=0.75, v=1.0, a=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return (r, g, b, a)


class VibrantDialog(ModalView):
    """Dark glassy card with a colour-cycling glow border, a spinning ring and bouncing dots."""

    def __init__(self, message, **kw):
        super().__init__(size_hint=(0.88, None), height=dp(310), auto_dismiss=False,
                         background="", background_color=(0, 0, 0, 0),
                         overlay_color=(0.05, 0.03, 0.16, 0.85), **kw)
        self._t = 0.0
        self._ev = None

        card = BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(14))
        with card.canvas.before:
            self._glow_c = Color(1, 0, 0.5, 0.9)
            self._glow = RoundedRectangle(radius=[dp(32)])
            Color(0.09, 0.06, 0.24, 1)
            self._body = RoundedRectangle(radius=[dp(29)])
            Color(1, 1, 1, 0.07)
            self._shine = RoundedRectangle(radius=[dp(29), dp(29), 0, 0])
        self._card = card

        # spinning ring
        self._ring = Widget(size_hint_y=None, height=dp(90))
        with self._ring.canvas:
            Color(1, 1, 1, 0.12)
            self._ring_bg = Line(width=dp(5))
            PushMatrix()
            self._rot = Rotate(angle=0, origin=(0, 0))
            self._arc_c = Color(1, 0, 0.5, 1)
            self._arc = Line(width=dp(5), cap="round")
            PopMatrix()
        card.add_widget(self._ring)

        # message
        self._msg = Label(text=message, font_size=sp(19), bold=True, halign="center", valign="middle",
                          color=(1, 1, 1, 1))
        self._msg.bind(size=lambda w, s: setattr(w, "text_size", s))
        card.add_widget(self._msg)

        # bouncing dots
        self._dots = Widget(size_hint_y=None, height=dp(28))
        self._dot_c, self._dot_e = [], []
        with self._dots.canvas:
            for _ in range(3):
                self._dot_c.append(Color(1, 1, 1, 1))
                self._dot_e.append(Ellipse())
        card.add_widget(self._dots)

        card.bind(pos=self._layout, size=self._layout)
        self.add_widget(card)
        self.bind(on_dismiss=lambda *_: self._stop())

    def open(self, *a, **kw):
        super().open(*a, **kw)
        if self._ev is None:
            self._ev = Clock.schedule_interval(self._tick, 1 / 30.0)

    def _stop(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None

    def _layout(self, *_):
        c = self._card
        g = dp(3)
        self._glow.pos = (c.x - g, c.y - g)
        self._glow.size = (c.width + 2 * g, c.height + 2 * g)
        self._body.pos = c.pos
        self._body.size = c.size
        self._shine.pos = (c.x, c.center_y)
        self._shine.size = (c.width, c.height / 2.0)

    def _tick(self, dt):
        self._t += dt
        t = self._t
        self._layout()
        self._glow_c.rgba = hsv(t * 0.12, 0.8, 1, 0.9)
        self._arc_c.rgba = hsv(t * 0.12 + 0.5, 0.7, 1, 1)
        self._msg.color = hsv(t * 0.12 + 0.9, 0.16, 1, 1)

        ring = self._ring
        cx, cy = ring.center
        r = min(ring.width, ring.height) / 2.0 - dp(6)
        self._ring_bg.circle = (cx, cy, r)
        self._arc.circle = (cx, cy, r, 0, 270)
        self._rot.origin = (cx, cy)
        self._rot.angle = -t * 360.0

        d, gap = dp(13), dp(11)
        x0 = self._dots.center_x - (3 * d + 2 * gap) / 2.0
        for i in range(3):
            bounce = max(0.0, math.sin(t * 5.0 - i * 0.7))
            self._dot_c[i].rgba = hsv(t * 0.12 + i * 0.12, 0.7, 1, 0.45 + 0.55 * bounce)
            self._dot_e[i].pos = (x0 + i * (d + gap), self._dots.y + dp(3) + bounce * dp(11))
            self._dot_e[i].size = (d, d)


class NumeracyApp(App):
    title = "Numeracy Drill"

    def build(self):
        cleanup_old_apk()               # remove the update file left from the last install
        self.core_srv = None
        self.host = None
        self._blocking = False          # True while an update popup is on screen
        self.sm = ScreenManager()
        for name in ("home", "student", "tlogin", "trun"):
            self.sm.add_widget(Screen(name=name))
        self.show_home()
        Window.bind(on_keyboard=self.on_key)
        # start the update check once the window is up (a popup can't open during build())
        Clock.schedule_once(lambda dt: self.check_update(), 0.5)
        return self.sm

    # ---- screens
    def set_screen(self, name, widget):
        scr = self.sm.get_screen(name)
        scr.clear_widgets()
        scr.add_widget(widget)
        self.sm.current = name

    def show_home(self):
        b = box()
        b.add_widget(Label(size_hint_y=0.1))
        b.add_widget(text("Guadalupe NHS", 30, BLUE, True))
        b.add_widget(text("Numeracy Drill", 18, MUTED))
        b.add_widget(Label(size_hint_y=0.1))
        b.add_widget(text("Who is using this app?", 20, INK, True))
        b.add_widget(big_button("I am the TEACHER (PIN)", BLUE, self.show_teacher_login))
        b.add_widget(big_button("I am a STUDENT", GREEN, self.show_student))
        b.add_widget(text("Teacher: this phone runs the drill for the class.\nStudent: join the teacher's drill.", 13, MUTED))
        b.add_widget(text("v" + __version__, 12, MUTED))
        b.add_widget(Label())
        self.set_screen("home", b)

    def _last_addr_file(self):
        return os.path.join(self.user_data_dir, "last_address.txt")

    def show_student(self):
        last = ""
        try:
            last = open(self._last_addr_file()).read().strip()
        except Exception:
            pass
        b = box()
        b.add_widget(text("Join the teacher's drill", 22, INK, True))
        status = text("Searching for your teacher...", 14, MUTED)
        b.add_widget(status)
        found = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        found.bind(minimum_height=found.setter("height"))
        b.add_widget(found)

        def join_url(url):
            try:
                open(self._last_addr_file(), "w").write(url)
            except Exception:
                pass
            open_webview(url)

        def show(res, *_):
            found.clear_widgets()
            if res:
                status.text = "Tap your teacher to join:"
                for name, url in res:
                    found.add_widget(big_button("%s  (%s)" % (name, url.replace("http://", "")), GREEN,
                                                lambda u=url: join_url(u), 56))
            else:
                status.text = "No teacher found. Same Wi-Fi? Search again, or type the address."

        def scan():
            found.clear_widgets()
            status.text = "Searching for your teacher..."

            def work():
                multicast_lock(True)
                try:
                    res = core.discover(4.0)
                finally:
                    multicast_lock(False)
                Clock.schedule_once(lambda dt: show(res), 0)
            threading.Thread(target=work, daemon=True).start()
        b.add_widget(big_button("Search again", BLUE, scan, 52))
        b.add_widget(text("Or type the address:", 13, MUTED))
        e = field("192.168.1.5:8000", value=last.replace("http://", "") or "192.168.")
        b.add_widget(e)
        err = text("", 14, RED)
        b.add_widget(err)

        def join():
            url = core.clean_address(e.text)
            if not url or url.endswith("192.168.:8000"):
                err.text = "Please type the full address."
                return
            join_url(url)
        e.bind(on_text_validate=lambda *_: join())
        b.add_widget(big_button("Join", GREEN, join, 56))
        b.add_widget(big_button("Back", GREY, self.show_home, 48))
        b.add_widget(Label())
        self.set_screen("student", b)
        scan()

    def show_teacher_login(self):
        try:
            if self.core_srv is None:
                self.core_srv = core.load_server(self.user_data_dir)
            first = not core.has_saved_pin(self.core_srv)
        except Exception as ex:
            traceback.print_exc()
            self.popup_error("Could not start the drill:\n%s" % ex)
            return
        b = box()
        b.add_widget(text("Create your teacher PIN" if first else "Teacher PIN", 22, INK, True))
        if first:
            b.add_widget(text("First time: choose a PIN (at least 4 characters).", 14, MUTED))
        e1 = field("PIN", password=True)
        b.add_widget(e1)
        e2 = None
        if first:
            e2 = field("Type it again", password=True)
            b.add_widget(e2)
        err = text("", 14, RED)
        b.add_widget(err)

        def go():
            pin = e1.text
            if first:
                if len(pin) < 4:
                    err.text = "At least 4 characters."
                    return
                if pin != e2.text:
                    err.text = "The two PINs do not match."
                    return
                core.create_pin(self.core_srv, pin)
            elif not core.check_pin(self.core_srv, pin):
                err.text = "Wrong PIN."
                return
            self.start_host()
        b.add_widget(big_button("Start", BLUE, go))
        b.add_widget(big_button("Back", GREY, self.show_home, 52))
        b.add_widget(Label())
        self.set_screen("tlogin", b)

    def start_host(self):
        try:
            if self.host is None:
                self.host = core.Host(self.core_srv, ips_func=get_ips)
        except Exception as ex:
            traceback.print_exc()
            self.popup_error("Could not start the server:\n%s" % ex)
            return
        keep_screen_on()
        self.show_running()
        open_webview(self.host.teacher_url())

    def show_running(self):
        urls = self.host.join_urls()
        b = box()
        b.add_widget(text("Drill is running", 24, GREEN, True))
        b.add_widget(text("Students type this address\n(same Wi-Fi or this phone's hotspot):", 14, MUTED))
        for u in urls[:3]:
            b.add_widget(text(u, 22, INK, True))
        b.add_widget(text("Keep this app open while the class is working.", 13, MUTED))
        b.add_widget(big_button("Open TEACHER dashboard", BLUE, lambda: open_webview(self.host.teacher_url())))
        b.add_widget(big_button("Open Pre / Post test (teacher)", PURPLE, lambda: open_webview(self.host.test_url())))
        b.add_widget(big_button("Stop the drill", RED, self.stop_host, 56))
        b.add_widget(Label())
        self.set_screen("trun", b)

    def stop_host(self):
        if self.host is not None:
            self.host.stop()
            self.host = None
        close_webview()
        self.show_home()

    # ---- updates
    def check_update(self):
        self._scan_popup = VibrantDialog(CHECKING_TEXT)
        self._blocking = True
        self._scan_popup.open()

        def work():
            t0 = time.time()
            info = updater.check(__version__)
            left = SCAN_SECONDS - (time.time() - t0)
            if left > 0:
                time.sleep(left)          # student waits the full scan time
            Clock.schedule_once(lambda dt: self.scan_done(info), 0)
        threading.Thread(target=work, daemon=True).start()

    def scan_done(self, info):
        self._scan_popup.dismiss()
        self._blocking = False
        if info:
            self.offer_update(info)
        elif DEBUG_UPDATER:
            self.popup_error("Update check (debug)\nThis app: %s\nLatest on GitHub: %s\nError: %s"
                             % (__version__, updater.last_tag or "?", updater.last_error or "none"))

    def offer_update(self, info):
        from kivy.uix.popup import Popup
        self._upd = {"id": None, "ev": None, "state": "idle", "info": info}
        b = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        self._upd_msg = text("Version %s is available.\nThis tablet has %s.\n\nUpdating automatically..."
                             % (info["version"], __version__), 16, WHITE)
        b.add_widget(self._upd_msg)
        self._upd_btn = big_button("Update now", GREEN, lambda: self.update_tap(info), 56)
        b.add_widget(self._upd_btn)
        # no Later button: the popup stays open until the new version is installed
        p = Popup(title="Update available", content=b, size_hint=(0.9, 0.5), auto_dismiss=False)
        self._blocking = True
        p.open()
        # start the download by itself, no tap needed
        Clock.schedule_once(lambda dt: self.begin_update(info), 0.5)

    def update_tap(self, info):
        st = self._upd["state"]
        if st == "downloading":
            return
        if st == "ready":
            self.install_update()
            return
        self.begin_update(info)

    def begin_update(self, info):
        if not ANDROID:
            open_url(info["url"])
            return
        if not can_install_apks():
            self._upd_msg.text = ("One-time step: turn ON \"Allow from this source\" for this app, "
                                  "then come back and tap Update now.")
            self._upd["state"] = "need_permission"
            open_install_permission_settings()
            return
        try:
            cleanup_old_apk()
            self._upd["id"] = start_apk_download(info["url"])
        except Exception as ex:
            traceback.print_exc()
            self._upd_msg.text = "Could not start the download:\n%s" % ex
            return
        self._upd["state"] = "downloading"
        self._upd_btn.disabled = True
        self._upd_btn.text = "Downloading..."
        self._upd_msg.text = UPDATING_TEXT + "\n0%"
        self._upd["ev"] = Clock.schedule_interval(lambda dt: self.poll_update(info), 0.5)

    def poll_update(self, info):
        try:
            status, done, total = download_progress(self._upd["id"])
        except Exception:
            traceback.print_exc()
            status, done, total = "failed", 0, 0
        if status == "running":
            pct = int(done * 100 / total) if total > 0 else 0
            self._upd_msg.text = "%s\n%d%%" % (UPDATING_TEXT, pct)
            return None
        self._upd["ev"].cancel()
        self._upd_btn.disabled = False
        if status == "done":
            self._upd["state"] = "ready"
            self._upd_btn.text = "Install now"
            self._upd_msg.text = UPDATING_TEXT
            self.install_update()
        else:
            self._upd["state"] = "failed"
            self._upd_btn.text = "Try again"
            self._upd_msg.text = "Download failed. Check the Wi-Fi or data connection, then try again."
        return False

    def install_update(self):
        try:
            install_downloaded_apk(self._upd["id"])
            # If the installer rejects the APK (for example it was signed with a different key),
            # Android shows "App not installed" and this popup stays. Tell the user what to do.
            self._upd_msg.text = ("If Android says \"App not installed\", delete Numeracy Drill, "
                                  "then install the new version from the teacher's link once.")
        except Exception as ex:
            traceback.print_exc()
            self._upd_msg.text = "Could not open the installer:\n%s" % ex

    def popup_error(self, msg):
        from kivy.uix.popup import Popup
        p = Popup(title="Numeracy Drill", content=text(msg, 15, WHITE), size_hint=(0.9, 0.4))
        p.open()

    # ---- phone Back button
    def on_key(self, window, key, *args):
        if key != 27:
            return False
        if self._blocking:
            return True  # an update popup is open: Back does nothing
        if _wv.get("view") is not None:
            webview_back()
            return True
        if self.sm.current == "trun":
            return True  # do not leave the running screen by accident; use "Stop the drill"
        if self.sm.current != "home":
            self.show_home()
            return True
        return False

    def on_pause(self):
        return True  # keep the server alive when the phone is switched to another app

    def on_resume(self):
        # back from the "Install unknown apps" settings screen: continue the update by itself
        u = getattr(self, "_upd", None)
        if u and u["state"] == "need_permission" and can_install_apks():
            self.begin_update(u["info"])

    def on_stop(self):
        if self.host is not None:
            self.host.stop()


if __name__ == "__main__":
    NumeracyApp().run()
