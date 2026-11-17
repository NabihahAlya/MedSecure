"""Exercise app.py without Streamlit installed, using a minimal stub of the st API.

Each "run" executes app.py top to bottom like a Streamlit rerun; session_state persists.
"""
import io
import runpy
import sys
import types
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1] / "app.py"
LOG = []
CTRL = {"page": None, "buttons": True, "select": 0, "upload": {}}


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
sys.modules["streamlit"] = st
sys.path.insert(0, str(APP.parent))


def run(page, **ctrl):
    LOG.clear()
    CTRL.update({"page": page, "buttons": True, "select": 0, "upload": {}}, **ctrl)
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
import core as C
for i, k in enumerate(C.ATTACKS):
    show(f"attack {k}", run("4. Attack Simulation", select=i), kinds=("success", "warning", "info", "metric"))
show("eval", run("5. Evaluate 10 Payloads"), kinds=("chart", "dataframe", "download"))
show("about", run("About"), kinds=("header",))
keys_json = st.session_state["kb"].to_json()
show("keys-load", run("1. Keys", buttons=False, upload={"json": Upload(keys_json.encode(), "k.json")}))
show("keys-generate-new then receiver (old pkg cleared)", run("1. Keys"))
show("receiver none", run("3. Receiver (destination hospital)"))
print("ALL STUB RUNS OK")
