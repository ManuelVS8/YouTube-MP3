# -*- coding: utf-8 -*-
"""
Descargador YouTube - app de escritorio para Windows
Descarga vídeo (alta / media / baja) o solo audio MP3 a partir de un enlace.
Motor: yt-dlp + deno + ffmpeg (imageio-ffmpeg). Todo gratuito.
Autor: Manuel J. Ventura Sánchez
"""
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog

# Con pythonw no hay consola: evitamos errores si algo intenta escribir
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

APP_NAME = "Descargador YouTube"
APP_VERSION = "1.2"
IS_WIN = os.name == "nt"
NO_WINDOW = 0x08000000 if IS_WIN else 0
SCRIPT = os.path.abspath(__file__)

CFG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "DescargadorYouTube")
CFG_FILE = os.path.join(CFG_DIR, "config.json")
PIP_PKGS = ["yt-dlp[default]", "deno", "imageio-ffmpeg"]

# Versión .exe (PyInstaller): ffmpeg y deno van incluidos en la carpeta "bin"
FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable if FROZEN else SCRIPT))
ENGINE_DIR = os.path.join(CFG_DIR, "motor")  # motor actualizado desde la app (.exe)


def _ver_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def _read(path, default=""):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return default


def activate_engine():
    """En el .exe, usa el motor descargado con «Actualizar motor» si es más nuevo que el incluido."""
    if not FROZEN:
        return
    newer = _read(os.path.join(ENGINE_DIR, "version.txt"))
    bundled = _read(os.path.join(BUNDLE_DIR, "motor_incluido.txt"), "0")
    if newer and _ver_tuple(newer) > _ver_tuple(bundled):
        sys.path.insert(0, ENGINE_DIR)


activate_engine()


def bundled_bin(name):
    path = os.path.join(BUNDLE_DIR, "bin", name + (".exe" if IS_WIN else ""))
    return path if os.path.exists(path) else None

YT_RE = re.compile(r"^(https?://)?([\w-]+\.)*(youtube\.com|youtu\.be|youtube-nocookie\.com)/", re.I)

QUALITIES = {
    "alta":  {"label": "Alta",  "height": 1080, "kbps": "320", "vdesc": "hasta 1080p", "adesc": "MP3 320 kbps"},
    "media": {"label": "Media", "height": 720,  "kbps": "192", "vdesc": "hasta 720p",  "adesc": "MP3 192 kbps"},
    "baja":  {"label": "Baja",  "height": 360,  "kbps": "128", "vdesc": "hasta 360p",  "adesc": "MP3 128 kbps"},
}

# Paleta
C = {
    "bg": "#F3F4F6", "card": "#FFFFFF", "text": "#1F2328", "muted": "#6B7280",
    "line": "#E5E7EB", "accent": "#E0322B", "accent_h": "#C1261F", "accent_soft": "#FDECEA",
    "chip": "#F3F4F6", "chip_h": "#E5E7EB", "ok": "#15803D", "ok_soft": "#DCFCE7",
    "err": "#B91C1C", "err_soft": "#FEE2E2", "info": "#1D4ED8", "info_soft": "#DBEAFE",
    "disabled": "#D1D5DB",
}
FONT = "Segoe UI" if IS_WIN else "DejaVu Sans"


# ----------------------------------------------------------------- utilidades
def default_folder():
    return os.path.join(os.path.expanduser("~"), "Downloads", "YouTube")


def load_cfg():
    cfg = {"folder": default_folder(), "mode": "video", "quality": "alta"}
    try:
        with open(CFG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    if cfg.get("quality") not in QUALITIES:
        cfg["quality"] = "alta"
    if cfg.get("mode") not in ("video", "audio"):
        cfg["mode"] = "video"
    return cfg


def save_cfg(cfg):
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(CFG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def python_console_exe():
    d, f = os.path.split(sys.executable)
    if f.lower() == "pythonw.exe" and os.path.exists(os.path.join(d, "python.exe")):
        return os.path.join(d, "python.exe")
    return sys.executable


def python_window_exe():
    d, f = os.path.split(sys.executable)
    if f.lower() == "python.exe" and os.path.exists(os.path.join(d, "pythonw.exe")):
        return os.path.join(d, "pythonw.exe")
    return sys.executable


def run_pip():
    cmd = [python_console_exe(), "-m", "pip", "install", "--disable-pip-version-check", "-U"] + PIP_PKGS
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
        return p.returncode == 0, (p.stdout + p.stderr)[-1500:]
    except Exception as e:
        return False, str(e)


def update_engine_files():
    """Actualiza yt-dlp en la versión .exe descargando las últimas versiones desde PyPI."""
    import io
    import shutil
    import urllib.request
    import zipfile

    def get_json(url):
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)

    def extract_wheel(data, dest):
        url = next(u["url"] for u in data["urls"] if u["packagetype"] == "bdist_wheel")
        with urllib.request.urlopen(url, timeout=180) as r:
            blob = r.read()
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            z.extractall(dest)

    tmp = ENGINE_DIR + "_nuevo"
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        ytd = get_json("https://pypi.org/pypi/yt-dlp/json")
        version = ytd["info"]["version"]
        extract_wheel(ytd, tmp)
        # yt-dlp-ejs en la versión exacta que pide esta versión de yt-dlp
        ejs_ver = None
        for req in ytd["info"].get("requires_dist") or []:
            m = re.match(r"yt-dlp-ejs\s*==\s*([\w.]+)", req)
            if m:
                ejs_ver = m.group(1)
                break
        ejs_url = f"https://pypi.org/pypi/yt-dlp-ejs/{ejs_ver}/json" if ejs_ver else "https://pypi.org/pypi/yt-dlp-ejs/json"
        extract_wheel(get_json(ejs_url), tmp)
        with open(os.path.join(tmp, "version.txt"), "w", encoding="utf-8") as f:
            f.write(version)
        shutil.rmtree(ENGINE_DIR, ignore_errors=True)
        os.replace(tmp, ENGINE_DIR)
        return True, version
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return False, str(e)


def run_update():
    return update_engine_files() if FROZEN else run_pip()


def deps_ok():
    try:
        import yt_dlp  # noqa: F401
        if not bundled_bin("ffmpeg"):
            import imageio_ffmpeg  # noqa: F401
        return True
    except Exception:
        return False


def restart_app():
    cmd = [sys.executable] if FROZEN else [python_window_exe(), SCRIPT]
    subprocess.Popen(cmd, creationflags=NO_WINDOW)


def fmt_duration(sec):
    if not sec:
        return ""
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_time(txt):
    """'90', '1:30', '1:02:30', '1.30' -> segundos (float). None si no es válido."""
    txt = (txt or "").strip().replace(".", ":").replace(",", ":").replace("'", ":")
    if not txt:
        return None
    parts = txt.split(":")
    if len(parts) > 3 or not all(p.strip().isdigit() for p in parts):
        return None
    total = 0
    for p in parts:
        total = total * 60 + int(p)
    return float(total)


def fmt_tag(sec):
    """Etiqueta para el nombre de archivo: 1m30s, 1h02m05s…"""
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def fmt_size(b):
    if not b:
        return ""
    for u in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.0f} {u}" if u in ("B", "KB") else f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"


def open_folder(path, select=None):
    try:
        if IS_WIN:
            if select and os.path.exists(select):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(select)])
            else:
                os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def create_shortcut():
    """Crea un acceso directo en el escritorio (lo llama el instalador)."""
    if not IS_WIN:
        return
    def q(s):  # cadena PowerShell entre comillas simples
        return "'" + s.replace("'", "''") + "'"
    target = python_window_exe()
    ps = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Descargador YouTube.lnk'));"
        f"$s.TargetPath={q(target)};"
        f"$s.Arguments=[char]34+{q(SCRIPT)}+[char]34;"
        f"$s.WorkingDirectory={q(os.path.dirname(SCRIPT))};"
        "$s.IconLocation='%SystemRoot%\\System32\\imageres.dll,18';"
        "$s.Description='Descargar vídeo o audio de YouTube';"
        "$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                   creationflags=NO_WINDOW)


def friendly_error(msg):
    m = (msg or "").lower()
    rules = [
        (("private video", "video privado"), "El vídeo es privado."),
        (("sign in to confirm your age", "age-restricted", "inappropriate for some users"),
         "El vídeo tiene restricción de edad y YouTube no permite descargarlo sin iniciar sesión."),
        (("not a bot", "confirm you"), "YouTube está pidiendo verificación. Espera un rato o pulsa «Actualizar motor»."),
        (("video unavailable", "not available", "has been removed", "no longer available"),
         "El vídeo no está disponible (borrado, bloqueado o restringido en tu país)."),
        (("members-only", "join this channel"), "Es un vídeo solo para miembros del canal."),
        (("live event", "premieres in", "is live"), "Es un directo o estreno que aún no ha terminado."),
        (("unsupported url", "is not a valid url"), "El enlace no es válido."),
        (("getaddrinfo", "network is unreachable", "timed out", "connection", "urlopen error"),
         "Problema de conexión. Revisa Internet e inténtalo de nuevo."),
        (("ffmpeg", "ffprobe"), "Falta ffmpeg. Pulsa «Actualizar motor»."),
        (("http error 403", "forbidden", "signature", "nsig", "javascript", "js runtime", "challenge"),
         "YouTube ha cambiado algo. Pulsa «Actualizar motor» y vuelve a intentarlo."),
        (("no space left",), "No queda espacio en el disco."),
        (("permission denied",), "No hay permiso para guardar en esa carpeta. Elige otra."),
    ]
    for keys, text in rules:
        if any(k in m for k in keys):
            return text
    return "No se pudo completar. Prueba «Actualizar motor» y repite la descarga."


def clean_msg(msg):
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(msg or ""))
    msg = msg.replace("ERROR: ", "").strip()
    return msg.splitlines()[0][:220] if msg else ""


# ------------------------------------------------------------ motor (yt-dlp)
class Cancelled(Exception):
    pass


class SilentLogger:
    def __init__(self):
        self.last_error = ""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.last_error = msg


def base_opts(logger):
    opts = {
        "quiet": True, "no_warnings": True, "noprogress": True, "logger": logger,
        "noplaylist": True, "windowsfilenames": True, "trim_file_name": 150,
        "overwrites": False, "continuedl": True, "retries": 5, "fragment_retries": 10,
        "concurrent_fragment_downloads": 4, "remote_components": ["ejs:github"],
    }
    ffmpeg = bundled_bin("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    deno_bin = bundled_bin("deno")
    if not deno_bin:
        try:
            import deno
            deno_bin = deno.find_deno_bin()
        except Exception:
            pass
    if deno_bin:
        opts["js_runtimes"] = {"deno": {"path": deno_bin}}
    return opts


def download_opts(mode, quality, folder, logger, section=None):
    q = QUALITIES[quality]
    opts = base_opts(logger)
    opts["paths"] = {"home": folder, "temp": folder}
    if mode == "audio":
        opts.update({
            "format": "bestaudio/best",
            "outtmpl": "%(title)s.%(ext)s",
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": q["kbps"]},
                {"key": "FFmpegMetadata"},
            ],
        })
    else:
        opts.update({
            "format": "bv*+ba/b",
            # Prioriza la resolución elegida y códecs compatibles con cualquier reproductor de Windows
            "format_sort": [f"res:{q['height']}", "vcodec:h264", "acodec:m4a"],
            "merge_output_format": "mp4",
            "outtmpl": "%(title)s%(height& [{}p]|)s.%(ext)s",
        })
    if section:
        from yt_dlp.utils import download_range_func
        start, end = section
        opts["download_ranges"] = download_range_func(None, [(start, end if end is not None else float("inf"))])
        opts["force_keyframes_at_cuts"] = True  # corte exacto en el segundo indicado
        tag = f" [tramo {fmt_tag(start)}-{fmt_tag(end) if end is not None else 'final'}]"
        opts["outtmpl"] = opts["outtmpl"].replace(".%(ext)s", tag + ".%(ext)s")
    return opts


# ------------------------------------------------------------ widgets propios
class FlatButton(tk.Label):
    def __init__(self, master, text, command, kind="primary", font_size=10, padx=16, pady=8, **kw):
        self.kind = kind
        self.command = command
        self.enabled = True
        self.colors = {
            "primary": (C["accent"], C["accent_h"], "#FFFFFF"),
            "ghost": (C["chip"], C["chip_h"], C["text"]),
            "link": (C["card"], C["card"], C["muted"]),
        }[kind]
        weight = "bold" if kind == "primary" else "normal"
        super().__init__(master, text=text, bg=self.colors[0], fg=self.colors[2],
                         font=(FONT, font_size, weight), padx=padx, pady=pady, cursor="hand2", **kw)
        self.bind("<Enter>", lambda e: self._paint(True))
        self.bind("<Leave>", lambda e: self._paint(False))
        self.bind("<Button-1>", self._click)

    def _paint(self, hover):
        if not self.enabled:
            return
        if self.kind == "link":
            self.config(fg=C["accent"] if hover else C["muted"])
        else:
            self.config(bg=self.colors[1] if hover else self.colors[0])

    def _click(self, _):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, on):
        self.enabled = on
        if on:
            self.config(bg=self.colors[0], fg=self.colors[2], cursor="hand2")
        else:
            bg = C["disabled"] if self.kind == "primary" else self.colors[0]
            self.config(bg=bg, fg="#FFFFFF" if self.kind == "primary" else C["disabled"], cursor="arrow")


class Segmented(tk.Frame):
    """Grupo de opciones tipo 'chips'."""
    def __init__(self, master, options, value, on_change=None):
        super().__init__(master, bg=C["card"])
        self.value = value
        self.on_change = on_change
        self.enabled = True
        self.items = {}
        for i, (key, title, sub) in enumerate(options):
            box = tk.Frame(self, bg=C["chip"], cursor="hand2", highlightthickness=2,
                           highlightbackground=C["chip"], highlightcolor=C["chip"])
            box.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            self.columnconfigure(i, weight=1, uniform="seg")
            t = tk.Label(box, text=title, bg=C["chip"], fg=C["text"], font=(FONT, 10, "bold"))
            t.pack(padx=10, pady=(8, 0))
            s = tk.Label(box, text=sub, bg=C["chip"], fg=C["muted"], font=(FONT, 8))
            s.pack(padx=10, pady=(0, 8))
            for w in (box, t, s):
                w.bind("<Button-1>", lambda e, k=key: self.select(k))
            self.items[key] = (box, t, s)
        self.refresh()

    def set_sub(self, key, text):
        self.items[key][2].config(text=text)

    def select(self, key):
        if not self.enabled or key == self.value:
            return
        self.value = key
        self.refresh()
        if self.on_change:
            self.on_change(key)

    def set_enabled(self, on):
        self.enabled = on
        self.refresh()

    def refresh(self):
        for key, (box, t, s) in self.items.items():
            sel = key == self.value
            bg = C["accent_soft"] if sel else C["chip"]
            border = C["accent"] if sel else C["chip"]
            fg = C["accent"] if sel else C["text"]
            if not self.enabled:
                fg = C["muted"]
            box.config(bg=bg, highlightbackground=border, highlightcolor=border,
                       cursor="hand2" if self.enabled else "arrow")
            t.config(bg=bg, fg=fg)
            s.config(bg=bg)


# -------------------------------------------------------------------- la app
class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_cfg()
        self.q = queue.Queue()
        self.busy = False
        self.cancel_flag = threading.Event()
        self.info = None
        self.info_url = ""
        self.last_file = None
        self.banner_job = None
        self.analyze_job = None

        root.title(APP_NAME)
        root.configure(bg=C["bg"])
        root.minsize(560, 600)
        self._icon()
        self._styles()

        if deps_ok():
            self._build_main()
        else:
            self._build_setup()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.poll)

    # ---- aspecto
    def _icon(self):
        try:
            n = 32
            img = tk.PhotoImage(width=n, height=n)
            rows = []
            for y in range(n):
                row = []
                for x in range(n):
                    circle = (x - 15.5) ** 2 + (y - 15.5) ** 2 <= 15.5 ** 2
                    stem = 14 <= x <= 17 and 6 <= y <= 17
                    head = 16 <= y <= 22 and abs(x - 15.5) <= (22 - y) + 0.5
                    base = 24 <= y <= 25 and 8 <= x <= 23
                    if circle:
                        row.append("#FFFFFF" if (stem or head or base) else C["accent"])
                    else:
                        row.append(C["bg"])
                rows.append("{" + " ".join(row) + "}")
            img.put(" ".join(rows))
            self.root.iconphoto(True, img)
            self._icon_img = img
        except Exception:
            pass

    def _styles(self):
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("Red.Horizontal.TProgressbar", troughcolor=C["line"], background=C["accent"],
                     bordercolor=C["line"], lightcolor=C["accent"], darkcolor=C["accent"], thickness=10)
        st.configure("Url.TEntry", padding=8, fieldbackground="#FFFFFF", bordercolor=C["line"],
                     lightcolor=C["line"], darkcolor=C["line"])
        st.map("Url.TEntry", bordercolor=[("focus", C["accent"])], lightcolor=[("focus", C["accent"])])

    def card(self, parent, **pack):
        f = tk.Frame(parent, bg=C["card"], highlightthickness=1, highlightbackground=C["line"],
                     highlightcolor=C["line"])
        f.pack(fill="x", **pack)
        inner = tk.Frame(f, bg=C["card"])
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        return inner

    def label(self, parent, text, size=10, bold=False, color=None, bg=None, **kw):
        return tk.Label(parent, text=text, bg=bg or C["card"], fg=color or C["text"],
                        font=(FONT, size, "bold" if bold else "normal"), **kw)

    def _header(self, parent):
        head = tk.Frame(parent, bg=C["bg"])
        head.pack(fill="x", pady=(0, 14))
        logo = tk.Canvas(head, width=40, height=40, bg=C["bg"], highlightthickness=0)
        logo.create_oval(2, 2, 38, 38, fill=C["accent"], outline="")
        logo.create_rectangle(18, 9, 22, 21, fill="#FFFFFF", outline="")
        logo.create_polygon(12, 19, 28, 19, 20, 27, fill="#FFFFFF")
        logo.create_rectangle(11, 29, 29, 31, fill="#FFFFFF", outline="")
        logo.pack(side="left")
        txt = tk.Frame(head, bg=C["bg"])
        txt.pack(side="left", padx=10)
        tk.Label(txt, text=APP_NAME, bg=C["bg"], fg=C["text"], font=(FONT, 16, "bold")).pack(anchor="w")
        tk.Label(txt, text="Pega un enlace y descarga el vídeo o el audio", bg=C["bg"], fg=C["muted"],
                 font=(FONT, 9)).pack(anchor="w")

    # ---- pantalla de instalación de componentes
    def _build_setup(self):
        wrap = tk.Frame(self.root, bg=C["bg"])
        wrap.pack(fill="both", expand=True, padx=22, pady=20)
        self._header(wrap)
        c = self.card(wrap)
        self.label(c, "Faltan componentes", 13, True).pack(anchor="w")
        self.label(c, "Para descargar hacen falta yt-dlp, ffmpeg y deno (gratuitos).\n"
                      "Se instalan una sola vez y tardan uno o dos minutos.",
                   9, color=C["muted"], justify="left").pack(anchor="w", pady=(4, 14))
        self.setup_btn = FlatButton(c, "Instalar ahora", self._install_deps)
        self.setup_btn.pack(anchor="w")
        self.setup_status = self.label(c, "", 9, color=C["muted"], justify="left", wraplength=480)
        self.setup_status.pack(anchor="w", pady=(12, 0))
        self.setup_bar = ttk.Progressbar(c, mode="indeterminate", style="Red.Horizontal.TProgressbar")

    def _install_deps(self):
        self.setup_btn.set_enabled(False)
        self.setup_status.config(text="Instalando… no cierres la ventana.", fg=C["muted"])
        self.setup_bar.pack(fill="x", pady=(10, 0))
        self.setup_bar.start(12)

        def work():
            ok, out = run_pip()
            self.q.put(("setup_done", ok, out))
        threading.Thread(target=work, daemon=True).start()

    # ---- pantalla principal
    def _build_main(self):
        wrap = tk.Frame(self.root, bg=C["bg"])
        wrap.pack(fill="both", expand=True, padx=22, pady=20)
        self._header(wrap)

        # Enlace
        c1 = self.card(wrap, pady=(0, 12))
        self.label(c1, "Enlace del vídeo", 10, True).pack(anchor="w")
        row = tk.Frame(c1, bg=C["card"])
        row.pack(fill="x", pady=(8, 0))
        self.url = tk.StringVar()
        self.entry = ttk.Entry(row, textvariable=self.url, style="Url.TEntry", font=(FONT, 10))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.start_download())
        self.url.trace_add("write", lambda *a: self._url_changed())
        FlatButton(row, "Pegar", self.paste, kind="ghost", pady=7).pack(side="left", padx=(8, 0))

        self.info_frame = tk.Frame(c1, bg=C["card"])
        self.info_frame.pack(fill="x")
        self.info_title = self.label(self.info_frame, "", 10, True, justify="left", wraplength=480, anchor="w")
        self.info_meta = self.label(self.info_frame, "", 9, color=C["muted"], anchor="w")

        # Opciones
        c2 = self.card(wrap, pady=(0, 12))
        self.label(c2, "Qué quieres descargar", 10, True).pack(anchor="w", pady=(0, 8))
        self.mode_seg = Segmented(c2, [("video", "🎬  Vídeo", "MP4 con sonido"),
                                       ("audio", "🎵  Solo audio", "MP3")],
                                  self.cfg["mode"], self._mode_changed)
        self.mode_seg.pack(fill="x")
        self.label(c2, "Calidad", 10, True).pack(anchor="w", pady=(14, 8))
        self.q_seg = Segmented(c2, [(k, v["label"], "") for k, v in QUALITIES.items()],
                               self.cfg["quality"], self._quality_changed)
        self.q_seg.pack(fill="x")
        self._update_quality_subs()

        # Tramo
        self.cut_on = False
        self.cut_chip = tk.Label(c2, text="", font=(FONT, 9, "bold"), cursor="hand2", padx=12, pady=6,
                                 anchor="w")
        self.cut_chip.pack(anchor="w", pady=(14, 0))
        self.cut_chip.bind("<Button-1>", lambda e: self.toggle_cut())
        self.cut_row = tk.Frame(c2, bg=C["card"])
        self.label(self.cut_row, "Desde", 9, color=C["muted"]).pack(side="left")
        self.cut_from = tk.StringVar(value="0:00")
        self.cut_from_e = ttk.Entry(self.cut_row, textvariable=self.cut_from, width=9, style="Url.TEntry",
                                    font=(FONT, 10), justify="center")
        self.cut_from_e.pack(side="left", padx=(6, 14))
        self.label(self.cut_row, "Hasta", 9, color=C["muted"]).pack(side="left")
        self.cut_to = tk.StringVar(value="")
        self.cut_to_e = ttk.Entry(self.cut_row, textvariable=self.cut_to, width=9, style="Url.TEntry",
                                  font=(FONT, 10), justify="center")
        self.cut_to_e.pack(side="left", padx=(6, 12))
        self.cut_hint = self.label(self.cut_row, "min:seg  ·  vacío = hasta el final", 8, color=C["muted"])
        self.cut_hint.pack(side="left")
        self.cut_len = self.label(c2, "", 8, color=C["muted"], anchor="w")
        for v in (self.cut_from, self.cut_to):
            v.trace_add("write", lambda *a: self._update_cut_len())
        self._paint_cut()

        self.label(c2, "Guardar en", 10, True).pack(anchor="w", pady=(14, 6))
        frow = tk.Frame(c2, bg=C["card"])
        frow.pack(fill="x")
        self.folder_lbl = self.label(frow, "", 9, color=C["muted"], anchor="w")
        self.folder_lbl.pack(side="left", fill="x", expand=True)
        FlatButton(frow, "Cambiar…", self.choose_folder, kind="ghost", font_size=9, pady=5, padx=12)\
            .pack(side="right")
        FlatButton(frow, "Abrir", lambda: self._open_out(), kind="ghost", font_size=9, pady=5, padx=12)\
            .pack(side="right", padx=(0, 6))
        self._show_folder()

        # Acción y progreso
        c3 = self.card(wrap)
        brow = tk.Frame(c3, bg=C["card"])
        brow.pack(fill="x")
        self.dl_btn = FlatButton(brow, "⬇  Descargar", self.start_download, font_size=12, pady=11)
        self.dl_btn.pack(side="left", fill="x", expand=True)
        self.cancel_btn = FlatButton(brow, "Cancelar", self.cancel, kind="ghost", pady=11)
        self.progress = ttk.Progressbar(c3, maximum=100, style="Red.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(14, 6))
        srow = tk.Frame(c3, bg=C["card"])
        srow.pack(fill="x")
        self.status = self.label(srow, "Listo.", 9, color=C["muted"], anchor="w")
        self.status.pack(side="left")
        self.stats = self.label(srow, "", 9, color=C["muted"], anchor="e")
        self.stats.pack(side="right")

        # Aviso integrado
        self.banner = tk.Frame(c3, bg=C["info_soft"])
        self.banner_lbl = tk.Label(self.banner, text="", bg=C["info_soft"], fg=C["info"], font=(FONT, 9),
                                   justify="left", anchor="w", wraplength=400)
        self.banner_lbl.pack(side="left", fill="x", expand=True, padx=12, pady=10)
        self.banner_lbl.bind("<Configure>", lambda e: self.banner_lbl.config(wraplength=max(e.width - 8, 120)))
        self.banner_btn = FlatButton(self.banner, "", None, kind="ghost", font_size=9, pady=4, padx=10)
        self.banner_x = tk.Label(self.banner, text="✕", bg=C["info_soft"], fg=C["muted"], cursor="hand2",
                                 font=(FONT, 10))
        self.banner_x.pack(side="right", padx=(0, 10), before=self.banner_lbl)
        self.banner_x.bind("<Button-1>", lambda e: self.hide_banner())

        # Pie
        foot = tk.Frame(wrap, bg=C["bg"])
        foot.pack(fill="x", side="bottom", pady=(10, 0))
        try:
            import yt_dlp
            ver = yt_dlp.version.__version__
        except Exception:
            ver = "?"
        tk.Label(foot, text=f"v{APP_VERSION} · motor yt-dlp {ver}", bg=C["bg"], fg=C["muted"],
                 font=(FONT, 8)).pack(side="left")
        self.upd_btn = FlatButton(foot, "↻ Actualizar motor", self.update_engine, kind="link", font_size=8,
                                  padx=0, pady=0)
        self.upd_btn.config(bg=C["bg"])
        self.upd_btn.colors = (C["bg"], C["bg"], C["muted"])
        self.upd_btn.pack(side="right")

        self.root.bind("<Control-v>", lambda e: None)
        self.entry.focus_set()

    # ---- tramo
    def _paint_cut(self):
        on = self.cut_on
        self.cut_chip.config(text=("☑" if on else "☐") + "  ✂  Descargar solo un tramo",
                             bg=C["accent_soft"] if on else C["chip"],
                             fg=C["accent"] if on else C["text"])
        if on:
            self.cut_row.pack(anchor="w", pady=(10, 0), after=self.cut_chip)
            self.cut_len.pack(anchor="w", pady=(4, 0), after=self.cut_row)
            self._update_cut_len()
        else:
            self.cut_row.pack_forget()
            self.cut_len.pack_forget()

    def toggle_cut(self):
        if self.busy:
            return
        self.cut_on = not self.cut_on
        self._paint_cut()
        if self.cut_on:
            self.cut_from_e.focus_set()
            self.cut_from_e.select_range(0, "end")

    def _get_section(self):
        """Devuelve (inicio, fin|None) o lanza ValueError con un mensaje para el usuario."""
        start = parse_time(self.cut_from.get()) if self.cut_from.get().strip() else 0.0
        if start is None:
            raise ValueError("El inicio del tramo no es válido. Escríbelo como min:seg, por ejemplo 1:30.")
        end_txt = self.cut_to.get().strip()
        end = parse_time(end_txt) if end_txt else None
        if end_txt and end is None:
            raise ValueError("El final del tramo no es válido. Escríbelo como min:seg, por ejemplo 2:45.")
        dur = (self.info or {}).get("duration") if self.info_url == self.url.get().strip() else None
        if dur and start >= dur:
            raise ValueError(f"El inicio es posterior al final del vídeo ({fmt_duration(dur)}).")
        if end is not None and dur and end > dur:
            end = None  # más allá del final = hasta el final
        if end is not None and end <= start:
            raise ValueError("El final del tramo debe ser posterior al inicio.")
        if start == 0 and end is None:
            return None  # es el vídeo completo
        return start, end

    def _update_cut_len(self):
        if not self.cut_on:
            return
        try:
            sec = self._get_section()
        except ValueError as e:
            self.cut_len.config(text=str(e), fg=C["err"])
            return
        if sec is None:
            self.cut_len.config(text="Se descargará el vídeo completo.", fg=C["muted"])
            return
        start, end = sec
        dur = (self.info or {}).get("duration") if self.info_url == self.url.get().strip() else None
        if end is None and dur:
            end = dur
        if end is not None:
            self.cut_len.config(text=f"Duración del tramo: {fmt_duration(end - start) or '0:00'}", fg=C["muted"])
        else:
            self.cut_len.config(text=f"Desde {fmt_duration(start)} hasta el final.", fg=C["muted"])

    # ---- helpers UI
    def _show_folder(self):
        f = self.cfg["folder"]
        short = f if len(f) <= 55 else "…" + f[-54:]
        self.folder_lbl.config(text=short)

    def _open_out(self):
        os.makedirs(self.cfg["folder"], exist_ok=True)
        open_folder(self.cfg["folder"])

    def _update_quality_subs(self):
        mode = self.mode_seg.value
        for k, v in QUALITIES.items():
            self.q_seg.set_sub(k, v["vdesc"] if mode == "video" else v["adesc"])

    def _mode_changed(self, key):
        self.cfg["mode"] = key
        save_cfg(self.cfg)
        self._update_quality_subs()
        self._show_info()

    def _quality_changed(self, key):
        self.cfg["quality"] = key
        save_cfg(self.cfg)
        self._show_info()

    def choose_folder(self):
        if self.busy:
            return
        d = filedialog.askdirectory(initialdir=self.cfg["folder"] if os.path.isdir(self.cfg["folder"])
                                    else os.path.expanduser("~"), title="Elige dónde guardar")
        if d:
            self.cfg["folder"] = os.path.normpath(d)
            save_cfg(self.cfg)
            self._show_folder()

    def paste(self):
        try:
            txt = self.root.clipboard_get().strip()
        except Exception:
            txt = ""
        if not txt:
            self.show_banner("El portapapeles está vacío. Copia primero el enlace del vídeo.", "err")
            return
        self.url.set(txt)
        self.entry.icursor("end")

    def show_banner(self, text, kind="info", action=None, auto_hide=None):
        bg, fg = {"info": (C["info_soft"], C["info"]), "ok": (C["ok_soft"], C["ok"]),
                  "err": (C["err_soft"], C["err"])}[kind]
        self.banner.config(bg=bg)
        self.banner_lbl.config(text=text, bg=bg, fg=fg)
        self.banner_x.config(bg=bg)
        self.banner_btn.pack_forget()
        if action:
            label, cmd = action
            self.banner_btn.config(text=label)
            self.banner_btn.command = cmd
            self.banner_btn.pack(side="right", padx=(0, 6), before=self.banner_lbl)
        self.banner.pack(fill="x", pady=(12, 0))
        if self.banner_job:
            self.root.after_cancel(self.banner_job)
            self.banner_job = None
        if auto_hide:
            self.banner_job = self.root.after(auto_hide, self.hide_banner)

    def hide_banner(self):
        self.banner.pack_forget()

    def set_busy(self, on):
        self.busy = on
        self.dl_btn.set_enabled(not on)
        self.mode_seg.set_enabled(not on)
        self.q_seg.set_enabled(not on)
        self.upd_btn.set_enabled(not on)
        self.entry.config(state="disabled" if on else "normal")
        for e in (self.cut_from_e, self.cut_to_e):
            e.config(state="disabled" if on else "normal")
        self.cut_chip.config(cursor="arrow" if on else "hand2")
        if on:
            self.cancel_btn.pack(side="left", padx=(8, 0))
        else:
            self.cancel_btn.pack_forget()

    # ---- análisis del enlace (título, duración…)
    def _url_changed(self):
        if self.analyze_job:
            self.root.after_cancel(self.analyze_job)
        url = self.url.get().strip()
        if url != self.info_url:
            self.info = None
            self._show_info()
        if YT_RE.match(url) and url != self.info_url:
            self.analyze_job = self.root.after(600, lambda: self.analyze(url))

    def analyze(self, url):
        self.analyze_job = None
        self.info_url = url
        self.info_title.config(text="Buscando el vídeo…", fg=C["muted"], font=(FONT, 9))
        self.info_title.pack(anchor="w", pady=(10, 0))
        self.info_meta.pack_forget()

        def work():
            try:
                import yt_dlp
                log = SilentLogger()
                opts = base_opts(log)
                opts["skip_download"] = True
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                self.q.put(("info", url, info, None))
            except Exception as e:
                self.q.put(("info", url, None, clean_msg(e)))
        threading.Thread(target=work, daemon=True).start()

    def _show_info(self):
        if not self.info:
            if not (self.info_url and self.info_url == self.url.get().strip()):
                self.info_title.pack_forget()
                self.info_meta.pack_forget()
            return
        info = self.info
        if info.get("_type") == "playlist":
            self.info_title.config(text=f"Lista de reproducción: {info.get('title') or ''}",
                                   fg=C["err"], font=(FONT, 10, "bold"))
            self.info_meta.config(text="Pega el enlace de un vídeo concreto, no de la lista.")
        else:
            heights = [f.get("height") for f in info.get("formats") or [] if f.get("height")
                       and f.get("vcodec") not in (None, "none")]
            maxh = max(heights) if heights else None
            parts = [info.get("uploader") or info.get("channel") or "", fmt_duration(info.get("duration"))]
            if maxh:
                parts.append(f"máx. {maxh}p")
            meta = "  ·  ".join(p for p in parts if p)
            want = QUALITIES[self.q_seg.value]["height"]
            if self.mode_seg.value == "video" and maxh and maxh < want:
                meta += f"   (se descargará a {maxh}p)"
            self.info_title.config(text=info.get("title") or "", fg=C["text"], font=(FONT, 10, "bold"))
            self.info_meta.config(text=meta)
        self.info_title.pack(anchor="w", pady=(10, 0))
        self.info_meta.pack(anchor="w", pady=(2, 0))
        self._update_cut_len()

    # ---- descarga
    def start_download(self):
        if self.busy:
            return
        url = self.url.get().strip()
        if not url:
            self.show_banner("Pega primero el enlace del vídeo.", "err")
            return
        if not YT_RE.match(url):
            self.show_banner("Ese enlace no parece de YouTube. Debe empezar por youtube.com o youtu.be.", "err")
            return
        if self.info and self.info_url == url and self.info.get("_type") == "playlist":
            self.show_banner("Es una lista de reproducción. Pega el enlace de un vídeo concreto.", "err")
            return
        section = None
        if self.cut_on:
            try:
                section = self._get_section()
            except ValueError as e:
                self.show_banner(str(e), "err")
                return
        folder = self.cfg["folder"]
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception:
            self.show_banner("No se puede usar esa carpeta. Elige otra con «Cambiar…».", "err")
            return
        self.hide_banner()
        self.cancel_flag.clear()
        self.set_busy(True)
        self.progress.config(mode="determinate", value=0)
        self.status.config(text="Preparando…", fg=C["muted"])
        self.stats.config(text="")
        mode, quality = self.mode_seg.value, self.q_seg.value
        threading.Thread(target=self._worker, args=(url, mode, quality, folder, section), daemon=True).start()

    def _worker(self, url, mode, quality, folder, section=None):
        import yt_dlp
        log = SilentLogger()
        state = {"part": 0, "tmp": set(), "final": None, "last": 0.0}
        n_parts = 1

        def hook(d):
            if self.cancel_flag.is_set():
                raise Cancelled()
            if d.get("tmpfilename"):
                state["tmp"].add(d["tmpfilename"])
            if d["status"] == "downloading":
                now = time.time()
                if now - state["last"] < 0.15:
                    return
                state["last"] = now
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                pct = (done / total * 100) if total else 0
                self.q.put(("progress", state["part"], n_parts, pct, d.get("speed"), d.get("eta"), total))
            elif d["status"] == "finished":
                state["part"] += 1

        def pphook(d):
            if d["status"] == "started":
                self.q.put(("phase", d.get("postprocessor")))
            elif d["status"] == "finished":
                fp = (d.get("info_dict") or {}).get("filepath")
                if fp:
                    state["final"] = fp

        opts = download_opts(mode, quality, folder, log, section)
        opts["progress_hooks"] = [hook]
        opts["postprocessor_hooks"] = [pphook]
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info.get("_type") == "playlist":
                    self.q.put(("error", "Es una lista de reproducción. Pega el enlace de un vídeo concreto.", ""))
                    return
                n_parts = 1 if section else (len(info.get("requested_formats") or []) or 1)
                self.q.put(("title", info.get("title") or ""))
                info = ydl.process_ie_result(info, download=True)
            final = state["final"]
            if not final:
                rd = info.get("requested_downloads") or []
                final = (rd[0].get("filepath") if rd else None) or info.get("filepath")
            self.q.put(("done", final, info.get("title") or ""))
        except Cancelled:
            self._cleanup(state["tmp"])
            self.q.put(("cancelled",))
        except Exception as e:
            if self.cancel_flag.is_set() or isinstance(getattr(e, "exc_info", [None, None])[1], Cancelled):
                self._cleanup(state["tmp"])
                self.q.put(("cancelled",))
                return
            raw = clean_msg(log.last_error or e)
            self.q.put(("error", friendly_error(raw), raw))

    @staticmethod
    def _cleanup(paths):
        time.sleep(0.5)
        for p in list(paths):
            for cand in (p, p + ".part", p + ".ytdl"):
                try:
                    if os.path.exists(cand) and (cand.endswith(".part") or cand.endswith(".ytdl")):
                        os.remove(cand)
                except Exception:
                    pass

    def cancel(self):
        if self.busy:
            self.cancel_flag.set()
            self.status.config(text="Cancelando…")

    # ---- actualizar motor
    def update_engine(self):
        if self.busy:
            return
        self.set_busy(True)
        self.cancel_btn.pack_forget()
        self.progress.config(mode="indeterminate")
        self.progress.start(12)
        self.status.config(text="Actualizando el motor… (puede tardar un minuto)", fg=C["muted"])
        self.stats.config(text="")

        def work():
            ok, out = run_update()
            self.q.put(("updated", ok, out))
        threading.Thread(target=work, daemon=True).start()

    # ---- bucle de mensajes desde los hilos
    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                self.handle(msg)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def handle(self, msg):
        kind = msg[0]
        if kind == "setup_done":
            _, ok, out = msg
            self.setup_bar.stop()
            if ok:
                self.setup_status.config(text="¡Instalado! Abriendo el programa…", fg=C["ok"])
                self.root.after(900, lambda: (restart_app(), self.root.destroy()))
            else:
                self.setup_btn.set_enabled(True)
                self.setup_status.config(text="No se pudo instalar. Comprueba la conexión y vuelve a probar.\n"
                                              + clean_msg(out.strip().splitlines()[-1] if out.strip() else ""),
                                         fg=C["err"])
        elif kind == "info":
            _, url, info, err = msg
            if url != self.url.get().strip():
                return
            if info:
                self.info = info
                self._show_info()
            else:
                self.info = None
                self.info_title.config(text=friendly_error(err), fg=C["err"], font=(FONT, 9))
                self.info_title.pack(anchor="w", pady=(10, 0))
                self.info_meta.pack_forget()
        elif kind == "title":
            self.status.config(text="Descargando…")
        elif kind == "progress":
            _, part, n, pct, speed, eta, total = msg
            if not total:
                if str(self.progress.cget("mode")) != "indeterminate":
                    self.progress.config(mode="indeterminate")
                    self.progress.start(12)
                self.status.config(text="Descargando y recortando el tramo…")
                self.stats.config(text="")
                return
            overall = (part * 100 + pct) / max(n, 1)
            if n > 1:
                overall = overall * 0.97  # deja un hueco para la unión
            self.progress.config(value=min(overall, 100))
            label = "Descargando"
            if n > 1:
                label += " vídeo" if part == 0 else " audio"
            self.status.config(text=f"{label}… {overall:.0f}%")
            bits = []
            if total:
                bits.append(fmt_size(total))
            if speed:
                bits.append(f"{fmt_size(speed)}/s")
            if eta:
                bits.append(f"quedan {fmt_duration(eta)}")
            self.stats.config(text="  ·  ".join(bits))
        elif kind == "phase":
            name = msg[1] or ""
            text = {"Merger": "Uniendo vídeo y sonido…", "ExtractAudio": "Convirtiendo a MP3…",
                    "Metadata": "Guardando datos…"}.get(name)
            if text:
                self.progress.config(mode="indeterminate")
                self.progress.start(12)
                self.status.config(text=text)
                self.stats.config(text="")
        elif kind == "done":
            _, path, title = msg
            self.progress.stop()
            self.progress.config(mode="determinate", value=100)
            self.set_busy(False)
            self.last_file = path
            name = os.path.basename(path) if path else title
            self.status.config(text="¡Descarga completada!", fg=C["ok"])
            size = fmt_size(os.path.getsize(path)) if path and os.path.exists(path) else ""
            self.stats.config(text=size)
            self.show_banner(f"✔  {name}", "ok",
                             action=("Mostrar en carpeta", lambda: open_folder(self.cfg["folder"], self.last_file)))
        elif kind == "cancelled":
            self.progress.stop()
            self.progress.config(mode="determinate", value=0)
            self.set_busy(False)
            self.status.config(text="Descarga cancelada.", fg=C["muted"])
            self.stats.config(text="")
        elif kind == "error":
            _, text, raw = msg
            self.progress.stop()
            self.progress.config(mode="determinate", value=0)
            self.set_busy(False)
            self.status.config(text="Error en la descarga.", fg=C["err"])
            self.stats.config(text="")
            detail = f"\n{raw}" if raw and raw != text else ""
            self.show_banner(text + detail, "err", action=("Actualizar motor", self.update_engine)
                             if "Actualizar" in text else None)
        elif kind == "updated":
            _, ok, out = msg
            self.progress.stop()
            self.progress.config(mode="determinate", value=0)
            self.set_busy(False)
            if ok:
                self.status.config(text="Motor actualizado. Reiniciando…", fg=C["ok"])
                self.root.after(900, lambda: (restart_app(), self.root.destroy()))
            else:
                self.status.config(text="No se pudo actualizar.", fg=C["err"])
                self.show_banner("No se pudo actualizar el motor. Revisa la conexión a Internet.", "err")

    def on_close(self):
        if self.busy:
            self.cancel_flag.set()
        self.root.destroy()


def main():
    if "--crear-acceso" in sys.argv and not FROZEN:
        create_shortcut()
        return
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Siurot.DescargadorYouTube")
        except Exception:
            pass
    root = tk.Tk()
    App(root)
    root.update_idletasks()
    w, h = max(root.winfo_reqwidth(), 600), max(root.winfo_reqheight(), 640)
    x = (root.winfo_screenwidth() - w) // 2
    y = max((root.winfo_screenheight() - h) // 3, 0)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.mainloop()


if __name__ == "__main__":
    main()
