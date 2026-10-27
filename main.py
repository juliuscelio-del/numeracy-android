"""Guadalupe NHS Numeracy Drill: Android app (Kivy).
Start screen: TEACHER (PIN, this phone runs the drill) or STUDENT (join the teacher's address).
The drill itself is a web page, shown inside a WebView."""
import os, sys, threading, traceback
from kivy.app import App
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.utils import get_color_from_hex as hexc

import app_core as core

try:
    from _version import __version__
except ImportError:
    __version__ = "0.0.0"
import updater

BLUE, GREEN, RED, PURPLE, GREY = "#2f6df6", "#1fc76a", "#ff5a5f", "#8b5cf6", "#7b8db3"
INK, MUTED, BG = "#12306b", "#5f78a8", "#e4f1ff"
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


class NumeracyApp(App):
    title = "Numeracy Drill"

    def build(self):
        self.core_srv = None
        self.host = None
        self.sm = ScreenManager()
        for name in ("home", "student", "tlogin", "trun"):
            self.sm.add_widget(Screen(name=name))
        self.show_home()
        self.check_update()
        Window.bind(on_keyboard=self.on_key)
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
        def work():
            info = updater.check(__version__)
            if info:
                Clock.schedule_once(lambda dt: self.offer_update(info), 0)
        threading.Thread(target=work, daemon=True).start()

    def offer_update(self, info):
        if self.host is not None or _wv.get("view") is not None:
            return  # never interrupt a running drill or an open page
        from kivy.uix.popup import Popup
        b = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        b.add_widget(text("Version %s is available.\nThis tablet has %s." % (info["version"], __version__), 16, INK))
        p = Popup(title="Update available", content=b, size_hint=(0.9, 0.45), auto_dismiss=False)
        b.add_widget(big_button("Update now", GREEN, lambda: (p.dismiss(), open_url(info["url"])), 56))
        b.add_widget(big_button("Later", GREY, p.dismiss, 48))
        p.open()

    def popup_error(self, msg):
        from kivy.uix.popup import Popup
        p = Popup(title="Numeracy Drill", content=text(msg, 15, INK), size_hint=(0.9, 0.4))
        p.open()

    # ---- phone Back button
    def on_key(self, window, key, *args):
        if key != 27:
            return False
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

    def on_stop(self):
        if self.host is not None:
            self.host.stop()


if __name__ == "__main__":
    NumeracyApp().run()
