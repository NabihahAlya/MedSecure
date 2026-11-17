"""Exercise app.py without Streamlit installed, using a minimal stub of the st API.

Each "run" executes app.py top to bottom like a Streamlit rerun; session_state persists.
"""
import io
import runpy
import sys
import types
from types import SimpleNamespace
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1] / "app.py"
LOG = []
CTRL = {"page": None, "buttons": True, "select": 0, "upload": {}, "mode": "Manual Brush", "strokes": None}


class SS(dict):
    __getattr__ = dict.__getitem__

    def __setattr__(self, k, v):
        self[k] = v


class Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Widget(Ctx):
    def _log(self, kind, *a):
        LOG.append((kind, a[:1]))

    def title(self, *a, **k): self._log("title", *a)
    header = subheader = caption = markdown = write = title

    def info(self, *a, **k): self._log("info", *a)

    def success(self, *a, **k): self._log("success", *a)

    def warning(self, *a, **k): self._log("warning", *a)

    def error(self, *a, **k): self._log("error", *a)

    def image(self, img, caption=None, **k):
        arr = np.asarray(img)
        assert arr.dtype == np.uint8 and arr.ndim in (2, 3), (arr.dtype, arr.shape)
        self._log("image", caption)

    def metric(self, label, value, **k):
        assert isinstance(value, (str, int, float)), type(value)
        self._log("metric", f"{label}={value}")

    def dataframe(self, df, **k):
        assert len(df) > 0
        self._log("dataframe", f"{df.shape}")

    def line_chart(self, data, **k): assert len(data) == 10; self._log("chart", "line")
    bar_chart = line_chart

    def progress(self, v=0.0, **k): return self

    def empty(self): return self

    def spinner(self, *a, **k): return Ctx()

    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [Widget() for _ in range(n)]

    def button(self, label, **k):
        self._log("button", label)
        return CTRL["buttons"]

    def download_button(self, label, data, file_name=None, **k):
        assert isinstance(data, (bytes, str)) and len(data) > 0
        self._log("download", file_name)
        return False

    def file_uploader(self, label, type=None, **k):
        for ext, val in CTRL["upload"].items():
            if type and ext in type:
                return val
        return None

    def text_input(self, label, value="", **k): return value

    def checkbox(self, label, value=False, **k): return value

    def selectbox(self, label, options, format_func=str, **k):
        options = list(options)
        [format_func(o) for o in options]
        return options[CTRL["select"]]

    def slider(self, label, lo, hi, value, **k):
        assert lo <= value <= hi, (label, lo, hi, value)
        return value

    def radio(self, label, options, **k):
        assert CTRL["page"] in options
        return CTRL["page"]

    def toggle(self, label, value=False, **k): return value

    def segmented_control(self, label, options, default=None, **k):
        assert CTRL["mode"] in options
        return CTRL["mode"]

    def status(self, *a, **k): return Status()

    def expander(self, *a, **k): return Widget()

    def altair_chart(self, chart, **k):
        chart.to_dict()  # forces Altair to validate the spec
        self._log("chart", "altair")


class Status(Widget):
    def write(self, *a, **k): self._log("status", *a)

    def update(self, **k): pass


class Upload(io.BytesIO):
    def __init__(self, data, name):
        super().__init__(data)
        self.name = name

    def getvalue(self):
        return super().getvalue()


st = types.ModuleType("streamlit")
w = Widget()
for name in dir(w):
    if not name.startswith("_"):
        setattr(st, name, getattr(w, name))
st.sidebar = Widget()
st.session_state = SS()
st.set_page_config = lambda **k: None
st.logo = lambda *a, **k: None


def _component(name, **kw):
    def mount(key=None, data=None, **k):
        LOG.append(("component", (name,)))
        if name == "medsecure_payload_grid":
            assert len(data["items"]) == 10 and all(i["src"].startswith("data:image/png") for i in data["items"])
            LOG.append(("label", (data["items"][0]["label"],)))
            LOG.append(("label", (data["items"][-1]["label"],)))
        return SimpleNamespace(strokes=CTRL["strokes"])
    return mount


st.components = SimpleNamespace(v2=SimpleNamespace(component=_component))
sys.modules["streamlit"] = st
sys.path.insert(0, str(APP.parent))


def run(page, **ctrl):
    LOG.clear()
    CTRL.update({"page": page, "buttons": True, "select": 0, "upload": {}, "mode": "Manual Brush",
                 "strokes": None}, **ctrl)
    runpy.run_path(str(APP), run_name="__main__")
    return list(LOG)


def show(tag, log, kinds=("success", "warning", "error", "info", "metric")):
    print(f"--- {tag}")
    for k, a in log:
        if k in kinds:
            print(f"   {k}: {a[0]}")


show("keys", run("1. Keys", buttons=False))
show("keys-generate", run("1. Keys"))
show("sender", run("2. Sender (origin hospital)"))
pkg = st.session_state["package"]
show("receiver (session pkg)", run("3. Receiver (destination hospital)"))
bad = bytearray(pkg); bad[-1] ^= 1
show("receiver (tampered pkg upload)", run("3. Receiver (destination hospital)", upload={"msx": Upload(bytes(bad), "x.msx")}))
show("receiver (junk upload)", run("3. Receiver (destination hospital)", upload={"msx": Upload(b"hello", "x.msx")}))
show("sender steps", [x for x in run("2. Sender (origin hospital)") if x[0] in ("status", "info")],
     kinds=("status", "info"))
import base64
from PIL import Image, ImageDraw
lay = Image.new("RGBA", (768, 512), (0, 0, 0, 0)); ImageDraw.Draw(lay).line((250, 250, 330, 280), fill=(255, 255, 255, 255), width=12)
buf = io.BytesIO(); lay.save(buf, "PNG")
strokes = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
show("attack manual brush (no strokes)", run("4. Attack Simulation"), kinds=("info",))
show("attack manual brush", run("4. Attack Simulation", strokes=strokes), kinds=("success", "warning", "info", "metric"))
for i, label in enumerate(["Crop", "Tambah Teks Palsu", "Naikkan Brightness", "Hapus Area", "Copy-move",
                            "Blur lokal", "Noise global", "Kompresi JPEG"]):
    show(f"auto {label}", run("4. Attack Simulation", mode="Auto Attack", select=i),
         kinds=("success", "warning", "info", "metric"))
show("eval", run("5. Evaluate 10 Payloads"), kinds=("chart", "dataframe", "download"))
show("payload grid", run("6. Perbandingan Semua Payload"), kinds=("component", "label", "chart", "image"))
show("about", run("About"), kinds=("header",))
keys_json = st.session_state["kb"].to_json()
show("keys-load", run("1. Keys", buttons=False, upload={"json": Upload(keys_json.encode(), "k.json")}))
show("keys-generate-new then receiver (old pkg cleared)", run("1. Keys"))
show("receiver none", run("3. Receiver (destination hospital)"))
show("receiver wrong key (old package, new keys)",
     run("3. Receiver (destination hospital)", upload={"msx": Upload(bytes(pkg), "x.msx")}), kinds=("error",))
print("ALL STUB RUNS OK")
