"""
MedSecure-XR — Streamlit demo.

Run:
    pip install -r requirements.txt
    streamlit run app.py
"""

import base64
import hashlib  # BARU
import io
import time  # BARU
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image  # BARU
from scipy.ndimage import maximum_filter  # BARU

import core as C

APP_DIR = Path(__file__).resolve().parent
SAMPLE = APP_DIR / "sample_xray.jpg"
ICON = APP_DIR / "assets" / "icon.svg"
NAV_ICON_DIR = APP_DIR / "assets" / "icons"  # Lucide v0.468.0 (ISC), see assets/icons/LICENSE

DEFAULT_EPR = [
    ("Hospital Name", "UM Sejahtera Hospital"),
    ("Examination Date", "November 4, 2026"),
    ("Medical Record Number", "RM-2026-001234"),
    ("Patient Name", "Nabihah Alya Az Zahidah"),
    ("Date of Birth", "January 24, 2026"),
    ("Time", "21:57"),
    ("Sex", "Female"),
    ("Blood Type", "B"),
    ("Patient Address", "Jalan Semarang"),
    ("Doctor Name", "Taharo Hafwenia"),
    ("Examination Type", "PA Chest X-ray"),
]
FIELD_COUNTS = [1, 2, 3, 5, 6, 7, 8, 9, 10, 11]
# page key -> (nav label, Lucide icon file in NAV_ICON_DIR)
PAGES = {
    "1. Keys": ("Key Management", "key-round"),
    "2. Sender (origin hospital)": ("Sender", "send"),
    "3. Receiver (destination hospital)": ("Receiver", "inbox"),
    "4. Attack Simulation": ("Attack Simulation", "shield-alert"),
    "5. Evaluate 10 Payloads": ("Evaluation", "chart-line"),
    "6. Perbandingan Semua Payload": ("Perbandingan Payload", "layout-grid"),  # BARU
    "About": ("About", "info"),
}
STEP_DELAY = 0.35  # BARU: jeda tampilan per teks progres (detik); tidak ikut dihitung di `times`
WRONG_KEY_MSG = "Kunci Salah! Tanda Tangan Digital Tidak Valid. File Ditolak."  # BARU
# BARU: Auto Attack -> (kode serangan di core.ATTACKS, atau "crop" yang dibuat di app.py)
AUTO_ATTACKS = {
    "Crop": "crop",
    "Tambah Teks Palsu": "teks",
    "Naikkan Brightness": "terangkan",
    "Hapus Area": "hapus_lesi",
    "Copy-move": "copy_move",
    "Blur lokal": "blur",
    "Noise global": "noise",
    "Kompresi JPEG": "jpeg",
}
STATUS_ICON = {"SAFE": ":material/verified_user:", "REJECTED": ":material/gpp_bad:",
               "TAMPERED": ":material/gpp_maybe:"}

st.set_page_config(page_title="MedSecure-XR", page_icon=str(ICON), layout="wide")
# Sidebar open: icon + "MedSecure-XR" wordmark. Sidebar closed: icon only.
st.logo(str(APP_DIR / "assets" / "logo.svg"), size="large", icon_image=str(ICON))


def nav_icon_css():
    """One CSS mask per nav item, in PAGES order, so the icon takes the theme color."""
    rules = []
    for i, (_, icon) in enumerate(PAGES.values(), 1):
        uri = "data:image/svg+xml;base64," + base64.b64encode((NAV_ICON_DIR / f"{icon}.svg").read_bytes()).decode()
        rules.append(f'[data-testid="stSidebar"] [data-testid="stRadioOption"]:nth-child({i}) p::before '
                     f'{{ -webkit-mask-image: url("{uri}"); mask-image: url("{uri}"); }}')
    return "\n".join(rules)


# ---------------------------------------------------------------- theme
# Fonts and base colors live in .streamlit/config.toml. Do not set font-family on
# "*" here: that overrides Streamlit's Material Symbols icon font, and icons then
# render as plain text (e.g. "keyboard_double_arrow_left").
st.markdown(
    """
    <style>
    :root {
        --teal: #0f9d8a;
        --teal-dark: #08766a;
        --teal-soft: #dff6f1;
        --teal-pale: #f3fcfa;
        --surface: #ffffff;
        --border: #bde5dc;
        --text: #163c38;
        --muted: #4a6662;
    }
    .stApp, [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #f7fdfc 0%, #edf9f6 50%, #ffffff 100%);
        color: var(--text);
    }
    /* Transparent top bar: the page title (st.header) sits in that row instead of below it. */
    [data-testid="stHeader"] {
        background: transparent !important;
        border-bottom: none;
        pointer-events: none;
    }
    [data-testid="stHeader"] * { pointer-events: auto; }
    [data-testid="stHeader"] button,
    [data-testid="stToolbar"] button {
        color: var(--teal-dark) !important;
    }
    .block-container { padding-top: .55rem !important; padding-bottom: 3rem; }
    [data-testid="stMain"] h2 {
        font-size: 1.9rem !important;
        line-height: 2.6rem !important;
        padding: 0 9rem 0 0 !important;   /* right gap keeps clear of Deploy / menu */
    }
    /* Page title sticks to the top like a navbar; the shadow+clip trick makes its
       frosted background span the full width of the main area. */
    [data-testid="stMain"] [data-testid="stElementContainer"]:has(h2) {
        position: sticky;
        top: 0;
        z-index: 999;
        padding: .55rem 0 1.25rem;
        margin-top: -.55rem;
        margin-bottom: .75rem;
        background: rgba(247, 253, 252, .97);
        box-shadow: 0 0 0 100vmax rgba(247, 253, 252, .97), 0 8px 14px -8px rgba(8, 118, 106, .22);
        clip-path: inset(0 -100vmax -16px);
        backdrop-filter: blur(8px);
        border-bottom: 1px solid var(--border);
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #e9f8f5 0%, #ffffff 72%);
        border-right: 1px solid var(--border);
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1 {
        color: var(--teal) !important;
        font-size: 1.45rem;
    }
    h1, h2, h3 { color: var(--teal-dark) !important; letter-spacing: -.025em; }
    h1 { font-weight: 700 !important; }
    p, li, label, .stCaption { color: var(--muted) !important; }
    [data-testid="stSidebar"] .stCaption { line-height: 1.7; }
    /* Streamlit fades captions with opacity; keep them readable */
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {
        opacity: 1 !important;
        color: var(--muted) !important;
    }
    /* wider wordmark logo + less empty space above the sidebar content */
    [data-testid="stSidebarHeader"] img[data-testid="stSidebarLogo"],
    [data-testid="stSidebarHeader"] img { height: 2.4rem; max-width: 15rem; }
    [data-testid="stSidebarHeader"] { margin-bottom: .25rem; }
    [data-testid="stSidebarUserContent"] { padding-top: .25rem !important; }
    /* ---- sidebar navigation: the radio is restyled as a modern nav list ---- */
    [data-testid="stSidebar"] [data-testid="stRadio"] > [data-testid="stWidgetLabel"] p {
        font-size: .7rem;
        font-weight: 600;
        letter-spacing: .12em;
        text-transform: uppercase;
        color: #5f7d78 !important;
        margin: 1.75rem 0 .75rem;
    }
    [data-testid="stSidebar"] [data-testid="stRadioGroup"] { gap: 12px; width: 100%; }
    /* Fill the sidebar height and pin the doctor-key card to the bottom. */
    /* header 64px + padding atas 4px + padding bawah 16px + sisa 12px = 6rem, jadi tidak ada scroll */
    [data-testid="stSidebarUserContent"] { padding-bottom: 1rem !important; }
    [data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] {
        min-height: calc(100vh - 6rem);
    }
    [data-testid="stSidebar"] [data-testid="stElementContainer"]:has(code) {
        margin-top: auto;
        padding: 12px 14px;
        border: 1px solid var(--border);
        border-radius: 12px;
        background: rgba(255, 255, 255, .75);
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] {
        position: relative;
        box-sizing: border-box;
        align-self: stretch;
        width: 100%;
        margin: 0;
        padding: 13px 14px;
        border-radius: 10px;
        cursor: pointer;
        transition: background .18s ease, box-shadow .18s ease, transform .18s ease;
    }
    /* hide the radio circle */
    [data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div > div:not([data-testid="stMarkdownContainer"]) {
        display: none !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"] { margin: 0; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] p {
        display: flex;
        align-items: center;
        gap: 12px;
        margin: 0;
        font-size: .93rem;
        font-weight: 500;
        color: var(--text) !important;
        transition: color .18s ease;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] p::before {
        content: "";
        flex: none;
        width: 20px;
        height: 20px;
        background-color: var(--teal);
        -webkit-mask: no-repeat center / contain;
        mask: no-repeat center / contain;
        transition: background-color .18s ease, transform .18s ease;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"]:hover {
        background: var(--teal-soft);
        transform: translateX(3px);
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"]:hover p::before { transform: scale(1.1); }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] {
        background: linear-gradient(135deg, #14b39c 0%, var(--teal-dark) 100%);
        box-shadow: 0 6px 16px rgba(15, 157, 138, .28);
        transform: none;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p {
        color: #ffffff !important;
        font-weight: 600;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p::before { background-color: #ffffff; }
    /*NAV_ICONS*/
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-focus-visible="true"] {
        outline: 2px solid var(--teal);
        outline-offset: 2px;
    }
    [data-testid="stMetric"] {
        background: rgba(255, 255, 255, .92);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 12px;
    }
    [data-testid="stMetricValue"] { color: var(--teal-dark); }
    /* BARU: angka metrik lebih kecil supaya pas di kartu */
    [data-testid="stMetricValue"], [data-testid="stMetricValue"] * { font-size: 1.55rem !important; }
    .stButton button, .stDownloadButton button {
        background: var(--teal) !important;
        color: #ffffff !important;
        border: 1px solid var(--teal) !important;
        border-radius: 8px;
        font-weight: 700;
        box-shadow: 0 4px 10px rgba(15, 157, 138, .18);
    }
    .stButton button *, .stDownloadButton button * { color: #ffffff !important; }
    .stButton button:hover, .stDownloadButton button:hover {
        background: var(--teal-dark) !important;
        border-color: var(--teal-dark) !important;
        color: #ffffff !important;
    }
    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div,
    [data-testid="stFileUploaderDropzone"] {
        background: var(--surface) !important;
        border-color: var(--border) !important;
        color: var(--text) !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        border: 1px dashed var(--border) !important;
        border-radius: 10px !important;
    }
    [data-testid="stFileUploaderDropzone"] button {
        background: var(--teal-pale) !important;
        color: var(--teal-dark) !important;
        border: 1px solid var(--border) !important;
        box-shadow: none !important;
    }
    [data-testid="stFileUploaderDropzone"] button:hover {
        background: var(--teal-soft) !important;
        border-color: var(--teal) !important;
    }
    [data-baseweb="input"] input { color: var(--text) !important; }
    div[data-baseweb="select"] * { color: var(--text) !important; }
    [data-baseweb="input"] > div:focus-within,
    div[data-baseweb="select"] > div:focus-within {
        border-color: var(--teal) !important;
        box-shadow: 0 0 0 1px var(--teal) !important;
    }
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        border: 1px solid var(--border);
        border-radius: 10px;
        overflow: hidden;
    }
    [data-testid="stAlert"] {
        background: var(--teal-pale) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px;
        color: var(--text) !important;
    }
    [data-testid="stAlert"] * { color: var(--text) !important; }
    [data-testid="stProgressBar"] > div > div { background-color: var(--teal) !important; }
    [data-baseweb="checkbox"] input:checked + div,
    [data-baseweb="radio"] input:checked + div { background-color: var(--teal) !important; }
    [data-testid="stMarkdownContainer"] code {
        background: var(--teal-soft);
        color: var(--teal-dark);
        border-radius: 4px;
        padding: 2px 5px;
    }
    </style>
    """.replace("/*NAV_ICONS*/", nav_icon_css()),
    unsafe_allow_html=True,
)
ss = st.session_state
for k, v in {"kb": None, "cover": None, "protected": None, "package": None, "epr_text": None}.items():
    if k not in ss:
        ss[k] = v


# ---------------------------------------------------------------- helpers
def epr_to_text(pairs):
    return "; ".join(f"{k}: {v}" for k, v in pairs if str(v).strip())


def text_to_epr(text):
    rows = []
    for part in (text or "").split("; "):
        k, _, v = part.partition(": ")
        rows.append({"Field": k, "Value": v})
    return pd.DataFrame(rows)


def fmt_db(x):
    return "∞ (unchanged)" if x == float("inf") else f"{x:.2f} dB"


def need_keys():
    if ss.kb is None:
        ss.kb = C.KeyBundle.generate()
    return ss.kb


def check_row(label, ok, detail=""):
    icon = ":green[:material/check_circle:]" if ok else ":red[:material/cancel:]"
    st.markdown(f"{icon} **{label}** {detail}")


def show_status(r):
    alert = {"SAFE": st.success, "REJECTED": st.error}.get(r["status"], st.warning)
    alert(f"{r['status']} — {r['message']}", icon=STATUS_ICON.get(r["status"], ":material/gpp_maybe:"))


# ---------------------------------------------------------------- BARU: helpers fitur tambahan
def png_data_url(arr):  # BARU
    return "data:image/png;base64," + base64.b64encode(C.to_png_bytes(arr)).decode()


def enhanced_diff(cover, wm):  # BARU
    """Peta selisih yang dipertajam: piksel berubah -> putih, lalu dipertebal 3x3 agar terlihat."""
    changed = (cover != wm).astype(np.uint8) * 255
    return maximum_filter(changed, size=3)


def amplified_diff(cover, wm, gain=50):  # BARU
    """Difference map: |asli - watermark| x gain (selisih LSB 0/1 -> 0/gain)."""
    d = np.abs(cover.astype(np.int16) - wm.astype(np.int16)) * gain
    return d.clip(0, 255).astype(np.uint8)


def roni_crop_box(cover, size=48):  # BARU
    """Kotak size x size di separuh kanan yang seluruhnya RONI dan paling hitam (paling kanan jika seri)."""
    mask = C.roni_mask(cover)
    h, w = cover.shape
    best = None
    for y in range(0, h - size + 1, 8):
        for x in range(w - size, w // 2, -8):
            if mask[y:y + size, x:x + size].all():
                score = (int(cover[y:y + size, x:x + size].max()), -x)
                if best is None or score < best[0]:
                    best = (score, y, x)
    if best is None:  # citra tanpa RONI penuh di kanan: pakai pojok kanan atas
        return 0, w - size, size
    return best[1], best[2], size


def zoom_crop(img, y, x, size, peak, factor=4):  # BARU
    """Crop, regangkan kontras (0..peak -> 0..255, skala sama untuk semua crop), zoom tanpa penghalusan."""
    c = img[y:y + size, x:x + size].astype(np.float64) * (255.0 / peak)
    pil = Image.fromarray(c.clip(0, 255).astype(np.uint8))
    return np.asarray(pil.resize((size * factor, size * factor), Image.NEAREST))


def metric_chart(df, col, fmt):  # BARU
    """Grafik garis satu metrik vs ukuran payload, dengan tooltip saat kursor diarahkan."""
    import altair as alt
    teal = "#0f9d8a"
    hover = alt.selection_point(fields=["Payload"], nearest=True, on="pointerover", empty=False)
    base = alt.Chart(df).encode(
        x=alt.X("Ukuran EPR (byte):Q", title="Ukuran EPR (byte)", scale=alt.Scale(zero=False)),
        y=alt.Y(f"{col}:Q", title=col, scale=alt.Scale(zero=False), axis=alt.Axis(format=fmt, tickCount=5)),
        tooltip=[alt.Tooltip("Payload:O"), alt.Tooltip("Ukuran EPR (byte):Q"),
                 alt.Tooltip(f"{col}:Q", format=fmt)])
    line = base.mark_line(color=teal, strokeWidth=2)
    dots = base.mark_point(color=teal, filled=True, size=64, opacity=1).add_params(hover)
    rule = base.mark_rule(color="#8aa6a1", strokeDash=[3, 3]).transform_filter(hover)
    return (rule + line + dots).properties(height=260, title=f"{col} vs payload").configure_axis(
        grid=True, gridColor="#e3f1ee", domainColor="#bde5dc", tickColor="#bde5dc",
        labelColor="#4a6662", titleColor="#4a6662").configure_view(stroke=None).configure_title(
        color="#163c38", anchor="start", fontSize=14)


def crop_attack(img, keep=0.85):  # BARU
    """Simulasi crop: bagian kanan & bawah di luar `keep` dibuang (diisi hitam), ukuran citra tetap."""
    a = img.copy()
    h, w = a.shape
    a[int(h * keep):, :] = 0
    a[:, int(w * keep):] = 0
    return a


def apply_brush(wm, strokes_url):  # BARU
    """Gabungkan coretan kuas (PNG RGBA dari kanvas) ke citra ber-watermark."""
    raw = base64.b64decode(strokes_url.split(",", 1)[1])
    layer = np.asarray(Image.open(io.BytesIO(raw)).convert("RGBA").resize(wm.shape[::-1]), dtype=np.float64)
    alpha = layer[..., 3] / 255.0
    out = wm.astype(np.float64) * (1 - alpha) + layer[..., 0] * alpha
    return np.round(out).clip(0, 255).astype(np.uint8)


def show_attack_result(wm, a):  # BARU: dipakai Manual Brush & Auto Attack (logika sama dengan versi lama)
    r = C.verify_image(a, keys, keys.public_key)
    gt = C.block_ground_truth(wm, a)
    show_status(r)
    # BARU: paket .msx dari citra hasil serangan, dienkripsi dengan kunci yang sama (aes_encrypt + pack_package
    # yang sudah ada), untuk diuji ulang di Receiver.
    enc_a, meta_a = C.aes_encrypt(a, keys.k_img, "siv")
    st.download_button("Download paket hasil serangan (.msx)", C.pack_package(enc_a, meta_a, "siv"),
                       file_name="xray_package_attacked.msx", mime="application/octet-stream",
                       icon=":material/download:",
                       help="Upload file ini di menu Receiver. Kuncinya benar, jadi dekripsi berhasil, "
                            "tapi sistem akan mendeteksi bahwa isi citranya sudah diubah.")
    c1, c2, c3 = st.columns(3)
    c1.image(wm, caption="Sebelum serangan")
    c2.image(a, caption="Sesudah serangan")
    if r["tamper_map"] is not None:
        c3.image(C.tamper_overlay(a, r["tamper_map"]), caption="Hasil deteksi")
        s = C.localization_scores(r["tamper_map"], gt)
        m = st.columns(4)
        m[0].metric("Changed pixels", int(np.sum(a != wm)))
        m[1].metric("Actually changed blocks", int(gt.sum()))
        m[2].metric("TPR (detection)", f"{s['TPR']:.3f}")
        m[3].metric("FPR (false alarm)", f"{s['FPR']:.3f}")
    else:
        c3.info("Watermark di RONI rusak total, jadi citra dinyatakan tidak autentik. Lokalisasi blok tidak "
                "tersedia karena watermark bersifat fragile.", icon=":material/gpp_bad:")


# BARU: kanvas kuas (komponen Streamlit v2, tanpa library tambahan). Mengirim lapisan coretan (PNG) ke Python.
BRUSH_CSS = """
.bw-tools { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:10px; font-size:.9rem; }
.bw-tools button { border:1px solid #bde5dc; background:#f3fcfa; color:#08766a; border-radius:8px;
  padding:6px 12px; cursor:pointer; font:inherit; }
.bw-tools button.on { background:#0f9d8a; color:#fff; border-color:#0f9d8a; }
.bw-tools label { color:#4a6662; display:flex; align-items:center; gap:6px; }
.bw-stage { position:relative; width:100%; border-radius:10px; overflow:hidden; border:1px solid #bde5dc; }
.bw-stage canvas { display:block; width:100%; height:auto; }
.bw-stage canvas.layer { position:absolute; inset:0; cursor:crosshair; touch-action:none; }
"""
BRUSH_JS = """
export default function (component) {
  const { data, parentElement, setStateValue } = component;
  let root = parentElement.querySelector('.bw-root');
  if (root && root.dataset.key === data.key) { root._set = setStateValue; return; }
  if (root) root.remove();
  root = document.createElement('div'); root.className = 'bw-root'; root.dataset.key = data.key;
  root._set = setStateValue;
  root.innerHTML = `
    <div class="bw-tools">
      <button data-c="#ffffff" class="on">Kuas putih</button>
      <button data-c="#000000">Kuas hitam</button>
      <label>Ukuran <input type="range" min="3" max="40" value="14"></label>
      <button class="clear">Hapus coretan</button>
    </div>
    <div class="bw-stage"><canvas class="base"></canvas><canvas class="layer"></canvas></div>`;
  parentElement.appendChild(root);
  const base = root.querySelector('canvas.base'), layer = root.querySelector('canvas.layer');
  base.width = layer.width = data.w; base.height = layer.height = data.h;
  const img = new Image();
  img.onload = () => base.getContext('2d').drawImage(img, 0, 0);
  img.src = data.img;
  const ctx = layer.getContext('2d');
  if (data.strokes) { const s = new Image(); s.onload = () => ctx.drawImage(s, 0, 0); s.src = data.strokes; }
  let color = '#ffffff', size = 14, drawing = false, last = null;
  root.querySelectorAll('button[data-c]').forEach(b => b.onclick = () => {
    root.querySelectorAll('button[data-c]').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); color = b.dataset.c;
  });
  root.querySelector('input[type=range]').oninput = e => size = +e.target.value;
  root.querySelector('button.clear').onclick = () => { ctx.clearRect(0, 0, layer.width, layer.height); root._set('strokes', null); };
  const pos = e => { const r = layer.getBoundingClientRect();
    return [(e.clientX - r.left) * layer.width / r.width, (e.clientY - r.top) * layer.height / r.height]; };
  const line = (p) => { ctx.strokeStyle = color; ctx.lineWidth = size; ctx.lineCap = ctx.lineJoin = 'round';
    ctx.beginPath(); ctx.moveTo(...(last || p)); ctx.lineTo(...p); ctx.stroke(); last = p; };
  layer.onpointerdown = e => { drawing = true; last = null; layer.setPointerCapture(e.pointerId); line(pos(e)); };
  layer.onpointermove = e => { if (drawing) line(pos(e)); };
  layer.onpointerup = layer.onpointercancel = () => {
    if (!drawing) return; drawing = false; last = null; root._set('strokes', layer.toDataURL('image/png'));
  };
}
"""
brush_canvas = st.components.v2.component("medsecure_brush", css=BRUSH_CSS, js=BRUSH_JS)  # BARU

# BARU: grid 10 payload + modal zoom (klik gambar). Semua interaksi zoom di browser, tanpa rerun.
GRID_CSS = """
.pg-grid { display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); gap:14px; }
@media (max-width: 900px) { .pg-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
.pg-card { background:#fff; border:1px solid #bde5dc; border-radius:10px; padding:6px; cursor:zoom-in;
  transition:box-shadow .15s ease, transform .15s ease; }
.pg-card:hover { box-shadow:0 6px 16px rgba(15,157,138,.22); transform:translateY(-2px); }
.pg-card img { width:100%; display:block; border-radius:6px; background:#000; }
.pg-card p { margin:6px 2px 2px; font-size:.74rem; line-height:1.35; color:#163c38; }
.pg-modal { position:fixed; inset:0; z-index:1000001; background:rgba(4,30,27,.96); display:none;
  flex-direction:column; padding:16px; box-sizing:border-box; }
.pg-modal.open { display:flex; }
.pg-bar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; color:#fff; margin-bottom:10px; font-size:.9rem; }
.pg-bar .t { flex:1; min-width:200px; font-weight:600; }
.pg-bar button { border:1px solid rgba(255,255,255,.35); background:rgba(255,255,255,.08); color:#fff;
  border-radius:8px; padding:6px 11px; cursor:pointer; font:inherit; }
.pg-bar button.on { background:#0f9d8a; border-color:#0f9d8a; }
.pg-view { flex:1; overflow:auto; border-radius:8px; background:#000; }
.pg-view img { display:block; image-rendering:pixelated; margin:auto; }
"""
GRID_JS = """
export default function (component) {
  const { data, parentElement } = component;
  let root = parentElement.querySelector('.pg-root');
  if (root && root.dataset.key === data.key) return;
  if (root) root.remove();
  root = document.createElement('div'); root.className = 'pg-root'; root.dataset.key = data.key;
  root.innerHTML = `<div class="pg-grid"></div>
    <div class="pg-modal"><div class="pg-bar"><span class="t"></span>
      <button data-z="1">1×</button><button data-z="2">2×</button><button data-z="4">4×</button><button data-z="8">8×</button>
      <button class="ab">Tampilkan citra asli</button><button class="x">Tutup ✕</button></div>
      <div class="pg-view"><img alt=""></div></div>`;
  parentElement.appendChild(root);
  const grid = root.querySelector('.pg-grid'), modal = root.querySelector('.pg-modal');
  const view = root.querySelector('.pg-view img'), title = root.querySelector('.t'), ab = root.querySelector('.ab');
  let cur = null, zoom = 1, showOrig = false;
  const render = () => {
    view.src = showOrig ? data.orig : cur.src;
    view.style.width = (data.w * zoom) + 'px';
    title.textContent = (showOrig ? 'Citra asli (tanpa watermark)' : cur.label);
    ab.classList.toggle('on', showOrig);
    root.querySelectorAll('button[data-z]').forEach(b => b.classList.toggle('on', +b.dataset.z === zoom));
  };
  data.items.forEach(it => {
    const card = document.createElement('div'); card.className = 'pg-card';
    card.innerHTML = `<img alt=""><p></p>`;
    card.querySelector('img').src = it.src; card.querySelector('img').alt = it.label;
    card.querySelector('p').textContent = it.label;
    card.onclick = () => { cur = it; zoom = 2; showOrig = false; render(); modal.classList.add('open'); };
    grid.appendChild(card);
  });
  root.querySelectorAll('button[data-z]').forEach(b => b.onclick = () => { zoom = +b.dataset.z; render(); });
  ab.onclick = () => { showOrig = !showOrig; render(); };
  const close = () => modal.classList.remove('open');
  root.querySelector('.x').onclick = close;
  modal.onclick = e => { if (e.target === modal) close(); };
  document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
}
"""
payload_grid = st.components.v2.component("medsecure_payload_grid", css=GRID_CSS, js=GRID_JS)  # BARU


# ---------------------------------------------------------------- BARU: Bukti Kriptografi (4 panel ilustrasi)
def crypto_panel_data(cover, wm, res, epr_text):  # BARU
    """Kumpulkan data asli untuk 4 panel. Tidak ada nilai contoh/dummy: semua dari hasil protect()."""
    body, _, _ = C.extract_body(wm, keys.k_wm)  # dibaca dari watermark yang benar-benar tersisip
    parsed = C.parse_body(body)
    plain = epr_text.encode("utf-8")
    # AES-GCM mengenkripsi per byte (keystream XOR), jadi byte pertama ciphertext = hasil enkripsi huruf pertama.
    ch_byte, ct_byte = plain[0], parsed["ct"][0]
    # Satu piksel RONI nyata yang bit terakhirnya berubah 0 -> 1 (dipilih yang nilainya paling terang
    # supaya ke-8 bitnya tidak semuanya nol).
    mask = res["mask"]
    cand = mask & ((cover & 1) == 0) & ((wm & 1) == 1)
    ys, xs = np.nonzero(cand)
    k = int(np.argmax(cover[ys, xs]))
    py, px = int(ys[k]), int(xs[k])
    before, after = int(cover[py, px]), int(wm[py, px])
    thumb = Image.fromarray(C.overlay_mask(cover, mask))
    thumb = np.asarray(thumb.resize((240, round(240 * cover.shape[0] / cover.shape[1]))))
    return {
        "key": hashlib.sha256(wm.tobytes() + plain).hexdigest()[:16],
        "epr": epr_text,
        "ch": chr(ch_byte) if ch_byte < 128 else f"0x{ch_byte:02x}",
        "plain_bits": f"{ch_byte:08b}", "cipher_bits": f"{ct_byte:08b}", "cipher_hex": f"{ct_byte:02x}",
        "ct_len": len(parsed["ct"]), "ct_hex20": parsed["ct"].hex()[:20],
        "sig_len": len(parsed["sig"]), "sig_hex20": parsed["sig"].hex()[:20],
        "px": {"x": px, "y": py, "before": before, "after": after,
               "before_bits": f"{before:08b}", "after_bits": f"{after:08b}"},
        "roni_url": png_data_url(thumb), "roni_pct": round(100 * float(mask.mean()), 1),
    }


CRYPTO_CSS = """
.cp-grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:14px; color:#163c38; }
@media (max-width: 1100px) { .cp-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .cp-grid { grid-template-columns:1fr; } }
.cp-card { background:#fff; border:1px solid #bde5dc; border-radius:14px; padding:14px 14px 12px;
  display:flex; flex-direction:column; gap:10px; transition:box-shadow .2s ease, border-color .2s ease; }
.cp-card:hover { box-shadow:0 8px 20px rgba(15,157,138,.16); border-color:#9fd9cc; }
.cp-card.key { border-color:#0f9d8a; box-shadow:0 0 0 1px #0f9d8a inset; }
.cp-head { display:flex; align-items:center; gap:8px; }
.cp-num { flex:none; width:24px; height:24px; border-radius:50%; background:#0f9d8a; color:#fff;
  font-size:.75rem; font-weight:700; display:grid; place-items:center; }
.cp-title { font-weight:700; font-size:.92rem; line-height:1.25; }
.cp-stage { height:150px; position:relative; display:grid; place-items:center; cursor:pointer; user-select:none; }
.cp-note { font-size:.74rem; line-height:1.45; color:#4a6662; margin:0; }
.cp-hint { font-size:.7rem; color:#0f9d8a; font-weight:600; text-align:center; margin:-4px 0 0; }
.cp-mono { font-family:"Source Code Pro", ui-monospace, monospace; font-size:.74rem; background:#dff6f1;
  color:#08766a; border-radius:5px; padding:2px 6px; word-break:break-all; }
.cp-btn { align-self:center; border:1px solid #0f9d8a; background:#0f9d8a; color:#fff; border-radius:8px;
  padding:6px 14px; font:inherit; font-size:.8rem; font-weight:600; cursor:pointer; }
.cp-btn:hover { background:#08766a; }
.cp-btn.ghost { background:#f3fcfa; color:#08766a; }

/* panel 1: amplop terbuka berisi surat */
.env { position:relative; width:150px; height:84px; margin-top:52px; }
.env .back { position:absolute; inset:0; background:#bfe8de; border-radius:4px 4px 8px 8px; }
.env .flap { position:absolute; left:0; top:-44px; width:0; height:0; border-left:75px solid transparent;
  border-right:75px solid transparent; border-bottom:44px solid #a9dfd2; }
.env .letter { position:absolute; left:12px; right:12px; top:-38px; height:96px; background:#fff;
  border:1px solid #bde5dc; border-radius:4px; padding:7px 8px; box-sizing:border-box; overflow:hidden;
  font-size:7.5px; line-height:1.4; color:#163c38; transition:transform .45s ease; z-index:1; }
.env .letter::after { content:""; position:absolute; left:0; right:0; bottom:0; height:26px;
  background:linear-gradient(transparent, #fff); }
.env .front { position:absolute; inset:0; background:#8fd3c4; border-radius:4px 4px 8px 8px; z-index:2;
  clip-path:polygon(0 0, 50% 52%, 100% 0, 100% 100%, 0 100%); }
.p1.open .env .letter { transform:translateY(-22px); }
.p1 .full { display:none; max-height:120px; overflow:auto; font-size:.74rem; line-height:1.45;
  background:#f3fcfa; border:1px solid #bde5dc; border-radius:8px; padding:8px; }
.p1.open .full { display:block; }

/* panel 2: amplop masuk gembok */
.lock { position:relative; width:110px; height:120px; margin-top:14px; }
.lock .shackle { position:absolute; left:23px; top:-6px; width:64px; height:56px; box-sizing:border-box;
  border:10px solid #9bb5b0; border-bottom:none; border-radius:34px 34px 0 0;
  transform:translateY(-16px); transition:transform .4s ease, border-color .4s ease; }
.lock .body { position:absolute; left:0; right:0; bottom:0; height:68px; border-radius:12px;
  background:linear-gradient(160deg, #9bb5b0, #6f8c87); transition:background .4s ease; overflow:hidden; }
.lock .hole { position:absolute; left:50%; top:22px; width:12px; height:12px; margin-left:-6px; border-radius:50%;
  background:#163c38; opacity:0; transition:opacity .3s ease .35s; }
.lock .hole::after { content:""; position:absolute; left:4px; top:9px; width:4px; height:12px; background:#163c38;
  border-radius:0 0 2px 2px; }
.mini-env { position:absolute; left:50%; top:24px; width:54px; height:34px; margin-left:-27px; background:#fff;
  border:1px solid #bde5dc; border-radius:3px; z-index:3; transition:transform .45s ease, opacity .45s ease; }
.mini-env::before { content:""; position:absolute; inset:0; background:linear-gradient(to bottom right,
  transparent 49%, #bde5dc 50%, transparent 52%), linear-gradient(to bottom left, transparent 49%, #bde5dc 50%,
  transparent 52%); background-size:50% 60%; background-repeat:no-repeat; background-position:left top, right top; }
.p2.locked .shackle { transform:translateY(0); border-color:#08766a; }
.p2.locked .body { background:linear-gradient(160deg, #14b39c, #08766a); }
.p2.locked .hole { opacity:1; }
.p2.locked .mini-env { transform:translateY(48px) scale(.55); opacity:0; }
.bits-wrap { display:flex; flex-direction:column; align-items:center; gap:4px; }
.bits-label { font-size:.7rem; color:#4a6662; }
.bits { display:flex; gap:3px; }
.bit { width:20px; height:22px; border-radius:4px; display:grid; place-items:center; font-size:.72rem;
  font-weight:700; border:1px solid #bde5dc; background:#f3fcfa; color:#163c38;
  transition:background .3s ease, color .3s ease, transform .3s ease; }
.bit.one { background:#dff6f1; }
.bits.cipher .bit { background:#eef3f2; color:#9bb5b0; }
.p2.locked .bits.cipher .bit { background:#0f9d8a; color:#fff; border-color:#0f9d8a; }
.p2.locked .bits.cipher .bit.same { background:#9fd9cc; border-color:#9fd9cc; color:#08766a; }
.arrow { font-size:.7rem; color:#0f9d8a; font-weight:700; }

/* panel 3: stempel */
.stamp-scene { position:relative; width:140px; height:140px; }
.stamp { position:absolute; left:50%; top:0; width:84px; margin-left:-42px; transition:transform .25s ease; z-index:2; }
.stamp .knob { width:34px; height:34px; margin:0 auto; border-radius:50%; background:linear-gradient(160deg,#14b39c,#08766a); }
.stamp .neck { width:16px; height:20px; margin:-4px auto 0; background:#08766a; }
.stamp .base { height:20px; border-radius:6px 6px 3px 3px; background:linear-gradient(160deg,#14b39c,#08766a); }
.stamp .pad { height:6px; margin:0 4px; border-radius:0 0 3px 3px; background:#163c38; }
.paper { position:absolute; left:6px; right:6px; bottom:0; height:44px; background:#fff; border:1px solid #bde5dc;
  border-radius:4px; display:grid; place-items:center; }
.imprint { width:64px; height:30px; border:2px solid #08766a; border-radius:6px; color:#08766a; font-size:.62rem;
  font-weight:700; letter-spacing:.04em; display:grid; place-items:center; transform:scale(1.6) rotate(-8deg);
  opacity:0; transition:opacity .25s ease .2s, transform .25s ease .2s; }
.p3.stamped .imprint { opacity:1; transform:scale(1) rotate(-8deg); }
.p3.pressing .stamp { transform:translateY(48px); }
.p3 .sig { display:none; }
.p3.stamped .sig { display:block; }

/* panel 4: satu piksel di-zoom */
.p4 .stage4 { display:flex; flex-direction:column; align-items:center; gap:8px; }
.swatch-row { display:flex; align-items:center; gap:10px; }
.swatch { width:46px; height:46px; border-radius:6px; border:2px solid #bde5dc;
  box-shadow:0 0 0 3px #fff, 0 0 0 4px #bde5dc; transition:background .4s ease; }
.swatch-info { font-size:.72rem; color:#4a6662; line-height:1.4; }
.swatch-info b { color:#163c38; font-size:.9rem; }
.p4 .bit.lsb { border:2px solid #e39a2d; background:#fff4e0; color:#8a5300; }
.p4 .bit.lsb.flip { animation:flip .5s ease; background:#e39a2d; color:#fff; }
@keyframes flip { 0% { transform:rotateX(0) } 50% { transform:rotateX(90deg) } 100% { transform:rotateX(0) } }
.bit-index { display:flex; gap:3px; }
.bit-index span { width:20px; text-align:center; font-size:.58rem; color:#8aa6a1; }
.roni-mini { display:flex; gap:8px; align-items:center; }
.roni-mini img { width:96px; border-radius:6px; border:1px solid #bde5dc; display:block; }
"""

CRYPTO_JS = """
export default function (component) {
  const { data, parentElement } = component;
  let root = parentElement.querySelector('.cp-root');
  if (root && root.dataset.key === data.key) return;
  if (root) root.remove();
  root = document.createElement('div'); root.className = 'cp-root'; root.dataset.key = data.key;
  root.innerHTML = `
  <div class="cp-grid">
    <section class="cp-card p1">
      <div class="cp-head"><span class="cp-num">1</span><span class="cp-title">Surat Asli</span></div>
      <div class="cp-stage s1"><div class="env"><div class="back"></div><div class="flap"></div>
        <div class="letter"></div><div class="front"></div></div></div>
      <p class="cp-hint h1">Klik amplop untuk membaca isinya</p>
      <div class="full"></div>
      <p class="cp-note">Ini data rekam medis (EPR) yang kamu isi di atas, masih bisa dibaca siapa saja.</p>
    </section>

    <section class="cp-card p2">
      <div class="cp-head"><span class="cp-num">2</span><span class="cp-title">Amplop Dikunci AES-256-GCM</span></div>
      <div class="cp-stage s2"><div class="lock"><div class="shackle"></div><div class="body"><div class="hole"></div></div>
        <div class="mini-env"></div></div></div>
      <button class="cp-btn b2">Kunci amplop</button>
      <div class="bits-wrap">
        <span class="bits-label l-plain"></span><div class="bits plain"></div>
        <span class="arrow">dienkripsi AES</span>
        <div class="bits cipher"></div><span class="bits-label l-cipher">sesudah: belum dikunci</span>
      </div>
      <p class="cp-note n2"></p>
    </section>

    <section class="cp-card p3">
      <div class="cp-head"><span class="cp-num">3</span><span class="cp-title">Distempel Ed25519</span></div>
      <div class="cp-stage s3"><div class="stamp-scene"><div class="stamp"><div class="knob"></div><div class="neck"></div>
        <div class="base"></div><div class="pad"></div></div><div class="paper"><div class="imprint">VALID</div></div></div></div>
      <p class="cp-hint h3">Klik stempel untuk menandatangani</p>
      <p class="cp-note sig"></p>
      <p class="cp-note">Stempel ini untuk memastikan file tidak diubah orang lain.</p>
    </section>

    <section class="cp-card p4 key">
      <div class="cp-head"><span class="cp-num">4</span><span class="cp-title">Diselipkan ke LSB RONI</span></div>
      <div class="stage4">
        <div class="swatch-row"><div class="swatch"></div><div class="swatch-info"></div></div>
        <div class="bits px"></div>
        <div class="bit-index"><span>1</span><span>2</span><span>3</span><span>4</span><span>5</span><span>6</span><span>7</span><span>8</span></div>
      </div>
      <button class="cp-btn b4">Lihat Perubahan</button>
      <p class="cp-note">Hanya 1 bit terakhir yang diubah, makanya foto tidak terlihat berubah.
        Dari sinilah nilai PSNR dan SSIM dihitung.</p>
      <div class="roni-mini"><img alt="Peta RONI"><p class="cp-note roni-note"></p></div>
    </section>
  </div>`;
  parentElement.appendChild(root);
  const $ = s => root.querySelector(s);
  const bitBoxes = (el, bits, cls = '') => {
    el.innerHTML = '';
    [...bits].forEach((b, i) => {
      const d = document.createElement('div');
      d.className = 'bit' + (b === '1' ? ' one' : '') + (typeof cls === 'function' ? cls(i) : cls);
      d.textContent = b; el.appendChild(d);
    });
  };

  // Panel 1: surat asli (teks dari input user, dipasang lewat textContent)
  $('.p1 .letter').textContent = data.epr;
  $('.p1 .full').textContent = data.epr;
  $('.s1').onclick = () => {
    const open = $('.p1').classList.toggle('open');
    $('.h1').textContent = open ? 'Klik lagi untuk menutup' : 'Klik amplop untuk membaca isinya';
  };

  // Panel 2: 1 huruf sebelum -> sesudah enkripsi
  $('.l-plain').textContent = `sebelum: huruf "${data.ch}"`;
  bitBoxes($('.bits.plain'), data.plain_bits);
  bitBoxes($('.bits.cipher'), '????????');
  $('.n2').innerHTML = '';
  const n2a = document.createElement('span');
  n2a.textContent = `Hasil lengkapnya ${data.ct_len} byte ciphertext, 20 karakter pertama: `;
  const n2b = document.createElement('span'); n2b.className = 'cp-mono'; n2b.textContent = data.ct_hex20 + '...';
  $('.n2').append(n2a, n2b);
  const lock = () => {
    const locked = $('.p2').classList.toggle('locked');
    $('.b2').textContent = locked ? 'Buka lagi' : 'Kunci amplop';
    $('.b2').classList.toggle('ghost', locked);
    if (locked) {
      bitBoxes($('.bits.cipher'), data.cipher_bits, i => data.cipher_bits[i] === data.plain_bits[i] ? ' same' : '');
      $('.l-cipher').textContent = `sesudah: byte 0x${data.cipher_hex}, acak dan tak bisa dibaca tanpa kunci ` +
        `(kotak terang = bit yang kebetulan sama)`;
    } else {
      bitBoxes($('.bits.cipher'), '????????');
      $('.l-cipher').textContent = 'sesudah: belum dikunci';
    }
  };
  $('.b2').onclick = lock; $('.s2').onclick = lock;

  // Panel 3: stempel, tanda tangan muncul setelah diklik
  $('.p3 .sig').innerHTML = '';
  const s1 = document.createElement('span'); s1.textContent = `Tanda tangan digital (${data.sig_len} byte): `;
  const s2 = document.createElement('span'); s2.className = 'cp-mono'; s2.textContent = data.sig_hex20 + '...';
  $('.p3 .sig').append(s1, s2);
  $('.s3').onclick = () => {
    const p = $('.p3');
    if (p.classList.contains('stamped')) { p.classList.remove('stamped'); $('.h3').textContent = 'Klik stempel untuk menandatangani'; return; }
    p.classList.add('pressing');
    setTimeout(() => { p.classList.remove('pressing'); p.classList.add('stamped'); }, 260);
    $('.h3').textContent = 'Klik lagi untuk mengulang';
  };

  // Panel 4: satu piksel RONI nyata, bit ke-8 berubah 0 -> 1
  const px = data.px; let changed = false;
  const showPixel = () => {
    const v = changed ? px.after : px.before;
    const bits = changed ? px.after_bits : px.before_bits;
    $('.swatch').style.background = `rgb(${v},${v},${v})`;
    $('.swatch-info').innerHTML = '';
    const b = document.createElement('b'); b.textContent = `Nilai ${v}`;
    const t = document.createElement('div');
    t.textContent = `piksel (x ${px.x}, y ${px.y}) ${changed ? 'sesudah' : 'sebelum'} disisipi`;
    $('.swatch-info').append(b, t);
    bitBoxes($('.bits.px'), bits, i => i === 7 ? ' lsb' + (changed ? ' flip' : '') : '');
    $('.b4').textContent = changed ? 'Kembalikan' : 'Lihat Perubahan';
    $('.b4').classList.toggle('ghost', changed);
  };
  $('.b4').onclick = () => { changed = !changed; showPixel(); };
  showPixel();
  $('.roni-mini img').src = data.roni_url;
  $('.roni-note').textContent = `Hanya area biru (RONI, latar gelap, ${data.roni_pct}% citra) yang dipakai. Area paru-paru tidak disentuh.`;
}
"""
crypto_panels = st.components.v2.component("medsecure_crypto_panels", css=CRYPTO_CSS, js=CRYPTO_JS)  # BARU


# ---------------------------------------------------------------- sidebar
st.sidebar.caption("Sistem Pengaman Citra Chest X-RAY")
page = st.sidebar.radio("Navigation", list(PAGES), format_func=lambda k: PAGES[k][0], width="stretch")
keys = need_keys()
st.sidebar.markdown(f":material/fingerprint: **Doctor public key**  \n`{keys.fingerprint()}`")


# ---------------------------------------------------------------- 1. keys
if page == "1. Keys":
    st.header("Key Management")
    st.markdown(
        "| Key | Algorithm | Purpose |\n|---|---|---|\n"
        "| `k_img` | AES-256-SIV (512 bit) | Encrypts the full image in transit + integrity tag |\n"
        "| `k_epr` | AES-256-GCM | Patient-record (EPR) confidentiality inside the watermark |\n"
        "| `k_wm` | HMAC-SHA256 | Per-32×32-block tag (tamper localization) + embedding order |\n"
        "| `sk/pk` | Ed25519 | Doctor's digital signature |")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Generate new keys", icon=":material/key:"):
            ss.kb = C.KeyBundle.generate()
            ss.protected = ss.package = None
            st.success(f"New keys generated. Fingerprint: {ss.kb.fingerprint()}", icon=":material/check_circle:")
        st.download_button("Download keys (JSON, CONFIDENTIAL)", ss.kb.to_json(), file_name="medsecure_keys.json",
                           mime="application/json", icon=":material/download:")
    with c2:
        up = st.file_uploader("Load keys from JSON", type=["json"])
        if up is not None:
            try:
                ss.kb = C.KeyBundle.from_json(up.getvalue().decode())
                st.success(f"Keys loaded. Fingerprint: {ss.kb.fingerprint()}", icon=":material/check_circle:")
            except Exception as e:  # noqa: BLE001
                st.error(f"Invalid key file: {e}", icon=":material/error:")
    

# ---------------------------------------------------------------- 2. sender
elif page == "2. Sender (origin hospital)":
    st.header("Sender")
    up = st.file_uploader("Upload chest X-ray image (PNG/JPG)", type=["png", "jpg", "jpeg"])
    use_sample = SAMPLE.exists() and st.checkbox("Use sample image", value=up is None)
    src = up if up is not None else (str(SAMPLE) if use_sample else None)

    st.subheader("Electronic Patient Record (EPR)")
    cols = st.columns(3)
    pairs = []
    for i, (k, v) in enumerate(DEFAULT_EPR):
        with cols[i % 3]:
            pairs.append((k, st.text_input(k, v, key=f"epr_{i}")))
    epr_text = epr_to_text(pairs)

    if src is not None:
        cover, orig = C.load_cover(src)
        mask = C.roni_mask(cover)
        cap = C.capacity_bits(mask)
        need = (C.overhead_bytes(cover.shape) + len(epr_text.encode())) * 8
        # BARU: ringkasan ukuran & kapasitas sebagai tabel (menggantikan caption satu baris)
        st.markdown(
            "| | Original size | Processed size | RONI pixels | Required bits |\n"
            "|---|---|---|---|---|\n"
            f"| **Value** | {orig[0]} × {orig[1]} | {cover.shape[1]} × {cover.shape[0]} | {cap:,} | {need:,} |\n"
            f"| **Share** | – | – | {100 * cap / cover.size:.1f}% of image | {100 * need / max(cap, 1):.1f}% of RONI |")
        c1, c2 = st.columns(2)
        c1.image(cover, caption="Cover")
        c2.image(C.overlay_mask(cover, mask), caption="Embedding area")

        step_mode = st.toggle("Mode Lihat Proses", value=True)  # BARU
        if st.button("Protect & encrypt", type="primary", icon=":material/lock:"):
            try:
                # BARU: Loading Step — teks progres muncul tepat saat tiap tahap protect() dimulai
                with st.status("Memproses...", expanded=True) as status:
                    def on_step(msg):
                        status.write(f":material/{'check_circle' if msg == 'Selesai!' else 'progress_activity'}: {msg}")
                        status.update(label=msg)
                        if msg != "Selesai!":
                            time.sleep(STEP_DELAY)
                    res = C.protect(cover, epr_text, keys, on_step=on_step)
                    status.update(label="Selesai!", state="complete", expanded=False)
            except C.WatermarkError as e:
                st.error(str(e), icon=":material/error:")
            else:
                ss.cover, ss.protected, ss.epr_text = cover, res, epr_text
                ss.package = C.pack_package(res["encrypted"], res["meta"], res["mode"])

        res = ss.protected
        if res is not None and ss.cover is not None and ss.cover.shape == cover.shape:
            wm, roi = res["watermarked"], ~res["mask"]

            # ---------------------------------------------------- BARU: Mode Lihat Proses (4 gambar berjajar)
            if step_mode:
                st.subheader("Lihat Proses")
                s1, s2, s3, s4 = st.columns(4)
                s1.image(ss.cover, caption="1. Citra asli")
                s2.image(C.overlay_mask(ss.cover, res["mask"]),
                         caption="2. Peta RONI")
                s3.image(wm, caption="3. Setelah watermark")
                s4.image(enhanced_diff(ss.cover, wm),
                         caption="4. Peta selisih.")

                # ------------------------------------------------ BARU: Bukti Kriptografi (teks saja)
                # Diambil dari watermark yang benar-benar tersisip (extract_body + parse_body yang sudah ada).
                # BARU: 4 panel ilustrasi interaktif (menggantikan 4 kotak teks)
                st.subheader("Ilustration")
                st.caption("Klik tiap panel untuk melihat apa yang terjadi pada data pasien.")
                crypto_panels(key="crypto_panels", data=crypto_panel_data(ss.cover, wm, res, ss.epr_text))

            st.markdown("**Image quality**")
            m = st.columns(5)
            m[0].metric("MSE", f"{C.mse(cover, wm):.6f}")
            m[1].metric("PSNR (full image)", fmt_db(C.psnr(cover, wm)))
            roi_psnr = C.psnr_region(cover, wm, roi)  # BARU: ∞ = area diagnostik tidak berubah sama sekali
            m[2].metric("PSNR (diagnostic ROI)", "∞ dB" if roi_psnr == float("inf") else f"{roi_psnr:.2f} dB",
                        help="∞ berarti MSE di area diagnostik = 0: tidak ada satu piksel pun di area paru-paru yang berubah, karena watermark hanya disisipkan di RONI.")
            m[3].metric("SSIM", f"{C.ssim(cover, wm):.6f}")
            m[4].metric("SNR", fmt_db(C.snr(cover, wm)))
            m = st.columns(5)
            m[0].metric("Embedded bits", f"{res['bits'].size}")
            m[1].metric("Total time", f"{1000 * sum(res['times'].values()):.1f} ms")
            if step_mode:  # BARU: watermark & selisih sudah tampil di Lihat Proses, tinggal citra terenkripsi
                st.image(res["encrypted"], caption="AES-256-SIV encrypted (transmitted image)", width=360)
            else:
                c1, c2, c3 = st.columns(3)
                c1.image(wm, caption="Watermarked image")
                diff = (np.abs(cover.astype(np.int16) - wm.astype(np.int16)) * 255).clip(0, 255).astype(np.uint8)
                c2.image(diff, caption="Difference ×255 (RONI only)")
                c3.image(res["encrypted"], caption="AES-256-SIV encrypted (transmitted image)")
            d1, d2 = st.columns(2)
            d1.download_button("Download encrypted package (.msx)", ss.package, file_name="xray_package.msx",
                               mime="application/octet-stream", icon=":material/download:")
            d2.download_button("Download watermarked image (PNG)", C.to_png_bytes(wm), file_name="watermarked.png",
                               mime="image/png", icon=":material/image:")
            st.dataframe(pd.DataFrame([{"stage": k, "ms": round(1000 * v, 3)} for k, v in res["times"].items()]),
                         hide_index=True)
    else:
        st.info("Upload a chest X-ray image to begin.", icon=":material/upload:")


# ---------------------------------------------------------------- 3. receiver
elif page == "3. Receiver (destination hospital)":
    st.header("Receiver")
    up = st.file_uploader("Upload .msx package", type=["msx"])
    data = up.getvalue() if up is not None else ss.package
    if data is None:
        st.info("No package available. Create one in Sender or upload an .msx file.", icon=":material/inbox:")
    else:
        st.caption("Source: uploaded file" if up is not None else "Source: latest package from Sender")
        if st.button("Decrypt & verify", type="primary", icon=":material/lock_open:"):
            try:
                enc, meta, mode = C.unpack_package(data)
            except ValueError as e:
                st.error(str(e), icon=":material/error:")
            else:
                r = C.receive(enc, meta, keys, keys.public_key, mode)
                # BARU: kunci salah -> dekripsi AES-SIV gagal (REJECTED). Tanda tangan tidak valid dengan
                # dekripsi berhasil berarti kuncinya benar tapi citranya diubah -> tetap TAMPERED, bukan kunci salah.
                if r["status"] == "REJECTED":
                    st.error(WRONG_KEY_MSG, icon=":material/gpp_bad:")
                    st.caption(f"Detail teknis: {r['message']}")
                else:
                    show_status(r)
                check_row("Transmission integrity (AES-SIV tag)", r["transit_ok"])
                if r["transit_ok"]:
                    check_row("Watermark found in RONI", r["watermark_found"])
                    check_row("Doctor signature (Ed25519)", r["signature_ok"], f"— key `{keys.fingerprint()}`")
                    check_row("All image blocks intact (per-block HMAC)", r["n_tampered"] == 0,
                              "" if r["n_tampered"] is None else f"— {r['n_tampered']} blocks changed")
                    check_row("EPR decrypted (AES-GCM)", r["epr_ok"])
                    c1, c2 = st.columns(2)
                    c1.image(r["image"], caption="Decrypted image")
                    if r["tamper_map"] is not None:
                        c2.image(C.tamper_overlay(r["image"], r["tamper_map"]),
                                 caption="Tamper map")
                    if r["epr_ok"]:
                        st.subheader("Patient data")
                        st.dataframe(text_to_epr(r["epr"]), hide_index=True)
                st.dataframe(pd.DataFrame([{"stage": k, "ms": round(1000 * v, 3)} for k, v in r["times"].items()]),
                             hide_index=True)


# ---------------------------------------------------------------- 4. attacks
elif page == "4. Attack Simulation":
    st.header("Attack simulation")
    if ss.protected is None:
        st.info("Protect an image in Sender first.", icon=":material/info:")
    else:
        wm = ss.protected["watermarked"]
        h, w = wm.shape
        # BARU: dua mode serangan
        mode = st.segmented_control("Mode serangan", ["Manual Brush", "Auto Attack"], default="Manual Brush",
                                    required=True) or "Manual Brush"

        if mode == "Manual Brush":  # BARU: coret gambar dengan kursor seperti kuas
            img_key = hashlib.sha256(wm.tobytes()).hexdigest()[:16]
            if ss.get("brush_key") != img_key:
                ss.brush_key, ss.brush_strokes = img_key, None
            st.caption("Coret area mana pun pada citra ber-watermark, lalu klik **Cek Manipulasi**.")
            res_brush = brush_canvas(key=f"brush_{img_key}",
                                     data={"key": img_key, "img": png_data_url(wm), "w": w, "h": h,
                                           "strokes": ss.brush_strokes},
                                     default={"strokes": None}, on_strokes_change=lambda: None)
            ss.brush_strokes = getattr(res_brush, "strokes", None)
            if st.button("Cek Manipulasi", type="primary", icon=":material/search:"):
                if not ss.brush_strokes:
                    st.info("Belum ada coretan. Coret dulu citranya dengan kuas.", icon=":material/brush:")
                else:
                    show_attack_result(wm, apply_brush(wm, ss.brush_strokes))

        else:  # BARU: Auto Attack — langsung dijalankan begitu jenis serangan dipilih
            label = st.selectbox("Jenis serangan", list(AUTO_ATTACKS))
            kind = AUTO_ATTACKS[label]
            bx, by, bw, bh = C.default_box(wm.shape)
            if kind not in ("noise", "jpeg", "crop"):
                with st.expander("Atur area serangan", icon=":material/tune:"):
                    c = st.columns(4)
                    bx = c[0].slider("x", 0, w - 16, bx)
                    by = c[1].slider("y", 0, h - 16, by)
                    bw = c[2].slider("width", 8, w // 2, bw)
                    bh = c[3].slider("height", 8, h // 2, bh)
            if kind == "crop":
                st.caption("Crop membuang 15% bagian kanan dan bawah citra (diisi hitam) dengan ukuran citra tetap.")
                a = crop_attack(wm)
            else:
                a = C.attack(wm, kind, (bx, by, min(bw, w - bx), min(bh, h - by)))
            show_attack_result(wm, a)


# ---------------------------------------------------------------- 5. evaluation
elif page == "5. Evaluate 10 Payloads":
    st.header("Evaluate")
    up = st.file_uploader("Test image", type=["png", "jpg", "jpeg"])
    src = up if up is not None else (str(SAMPLE) if SAMPLE.exists() else None)
    if src is None:
        st.info("Upload a test image.", icon=":material/upload:")
    elif st.button("Run evaluation", type="primary", icon=":material/play_arrow:"):
        cover, _ = C.load_cover(src)
        payloads = [epr_to_text(DEFAULT_EPR[:n]) for n in FIELD_COUNTS]
        rows = []
        prog = st.progress(0.0)
        for i, p in enumerate(payloads, 1):
            res = C.protect(cover, p, keys)
            r = C.receive(res["encrypted"], res["meta"], keys, keys.public_key)
            wm, enc, roi = res["watermarked"], res["encrypted"], ~res["mask"]
            n_, u_ = C.differential_test(wm, keys.k_img)
            rows.append({"payload": i, "epr_bytes": len(p.encode()), "embedded_bits": int(res["bits"].size),
                         "bpp": res["bits"].size / cover.size, "MSE": C.mse(cover, wm), "PSNR_dB": C.psnr(cover, wm),
                         "PSNR_ROI": "inf" if C.psnr_region(cover, wm, roi) == float("inf") else "changed",
                         "SSIM": C.ssim(cover, wm), "SNR_dB": C.snr(cover, wm), "cipher_entropy": C.entropy(enc),
                         "cipher_horizontal_correlation": C.adjacent_correlation(enc)["H"], "NPCR_%": n_, "UACI_%": u_,
                         "BER": C.ber(res["bits"], r["bits"]), "NC": C.nc(res["bits"], r["bits"]),
                         "hash_matches": C.sha256_img(r["image"]) == C.sha256_img(wm),
                         "EPR_matches": r["epr"] == p, "status": r["status"],
                         "sender_time_ms": 1000 * sum(res["times"].values()),
                         "receiver_time_ms": 1000 * sum(r["times"].values())})
            prog.progress(i / len(payloads))
        df = pd.DataFrame(rows)
        st.dataframe(df.round(6), hide_index=True)
        c1, c2 = st.columns(2)
        c1.markdown("**Full-image PSNR (dB)**"); c1.line_chart(df.set_index("payload")["PSNR_dB"])
        c2.markdown("**SSIM**"); c2.line_chart(df.set_index("payload")["SSIM"])
        c1.markdown("**Differential NPCR / UACI (%)**"); c1.line_chart(df.set_index("payload")[["NPCR_%", "UACI_%"]])
        c2.markdown("**Processing time (ms)**"); c2.bar_chart(df.set_index("payload")[["sender_time_ms", "receiver_time_ms"]])
        st.download_button("Download results (CSV)", df.to_csv(index=False), file_name="evaluasi_10_payload.csv",
                           mime="text/csv", icon=":material/download:")
        st.subheader("AES mode comparison")
        wm10 = C.protect(cover, payloads[-1], keys)["watermarked"]
        cmp_rows = []
        for m in ["siv", "ctr", "cbc"]:
            n_, u_ = C.differential_test(wm10, keys.k_img, m)
            cmp_rows.append({"mode": f"AES-256-{m.upper()}", "NPCR_%": round(n_, 4), "UACI_%": round(u_, 4)})
        st.dataframe(pd.DataFrame(cmp_rows), hide_index=True)
        st.caption("Ideal 8-bit image: NPCR ≈ 99.61%, UACI ≈ 33.46%. CTR/CBC with the same IV do not diffuse changes.")


# ---------------------------------------------------------------- BARU: 6. perbandingan semua payload
elif page == "6. Perbandingan Semua Payload":
    st.header("Perbandingan Semua Payload")
    up = st.file_uploader("Citra uji", type=["png", "jpg", "jpeg"])
    src = up if up is not None else (str(SAMPLE) if SAMPLE.exists() else None)
    if src is None:
        st.info("Upload citra uji dulu.", icon=":material/upload:")
    else:
        cover, _ = C.load_cover(src)
        grid_key = hashlib.sha256(cover.tobytes() + keys.fingerprint().encode()).hexdigest()[:16]
        if ss.get("payload_grid_key") != grid_key or ss.get("payload_stats_key") != grid_key:  # BARU: + stats
            payloads = [epr_to_text(DEFAULT_EPR[:n]) for n in FIELD_COUNTS]
            items = []
            stats, wm_keep = [], {}  # BARU: angka untuk grafik + citra Payload 1 & 10 untuk difference map/crop
            prog = st.progress(0.0, text="Menjalankan protect() untuk 10 payload...")
            for i, p in enumerate(payloads, 1):
                res = C.protect(cover, p, keys)  # gambar asli hasil protect(), bukan tiruan
                wm = res["watermarked"]
                psnr_txt = "∞" if C.psnr(cover, wm) == float("inf") else f"{C.psnr(cover, wm):.2f}"
                items.append({"src": png_data_url(wm),
                              "label": f"Payload {i} - {len(p.encode())} byte - PSNR: {psnr_txt} dB - "
                                       f"SSIM: {C.ssim(cover, wm):.3f} - BPP: {res['bits'].size / cover.size:.4f}"})
                stats.append({"Payload": i, "Ukuran EPR (byte)": len(p.encode()),  # BARU
                              "PSNR (dB)": C.psnr(cover, wm), "SSIM": C.ssim(cover, wm),
                              "BPP": res["bits"].size / cover.size, "Piksel berubah": int(np.sum(cover != wm))})
                if i in (1, len(payloads)):  # BARU
                    wm_keep[i] = wm
                prog.progress(i / len(payloads), text=f"Payload {i}/10 selesai")
            prog.empty()
            ss.payload_stats_key, ss.payload_stats, ss.payload_wm = grid_key, stats, wm_keep  # BARU
            ss.payload_grid_key = grid_key
            ss.payload_grid = {"key": grid_key, "items": items, "orig": png_data_url(cover),
                               "w": int(cover.shape[1])}
        st.caption("Payload 1 (terpendek) sampai Payload 10 (terpanjang). Klik gambar untuk zoom; di dalam zoom, "
                   "tombol **Tampilkan citra asli** bergantian menampilkan citra tanpa watermark untuk dibandingkan. "
                   "BPP = bit tersisip ÷ jumlah piksel.")
        payload_grid(key="payload_grid_view", data=ss.payload_grid)

        # ------------------------------------------------ BARU: 1. grafik PSNR / SSIM / BPP vs payload
        df_pl = pd.DataFrame(ss.payload_stats)
        st.subheader("Tren kualitas terhadap ukuran payload")
        st.caption("Data dari 10 pemanggilan protect() di atas. Tiap metrik punya grafik sendiri karena skalanya "
                   "berbeda jauh (PSNR puluhan dB, SSIM mendekati 1, BPP ratusan ribu kali lebih kecil).")
        g1, g2, g3 = st.columns(3)
        g1.altair_chart(metric_chart(df_pl, "PSNR (dB)", ".2f"), width="stretch")
        g2.altair_chart(metric_chart(df_pl, "SSIM", ".5f"), width="stretch")
        g3.altair_chart(metric_chart(df_pl, "BPP", ".4f"), width="stretch")
        with st.expander("Lihat tabel data grafik", icon=":material/table:"):
            st.dataframe(df_pl.round(6), hide_index=True)

        # ------------------------------------------------ BARU: 2. difference map Payload 1 vs Payload 10
        n_last = max(ss.payload_wm)
        st.subheader("Difference map Payload 1 vs Payload 10")
        gain = 50
        d1, d2 = st.columns(2)
        for col, i in ((d1, 1), (d2, n_last)):
            row = df_pl[df_pl["Payload"] == i].iloc[0]
            col.image(amplified_diff(cover, ss.payload_wm[i], gain),
                      caption=f"Difference Map Payload {i} (diperkuat {gain}x) - "
                              f"{int(row['Piksel berubah'])} piksel berubah")
        st.caption("Rumus: |citra asli - citra watermark| x 50. Selisih LSB bernilai 0 atau 1, jadi titik yang "
                   "berubah tampil abu-abu (nilai 50) di atas hitam. Semua titik berada di RONI (latar gelap), "
                   "area paru-paru tetap hitam. Klik ikon layar penuh di pojok gambar untuk melihat ukuran asli.")

        # ------------------------------------------------ BARU: 3. crop zoom 400% area hitam RONI
        y0, x0, s_ = roni_crop_box(cover)
        st.subheader("Crop zoom area hitam RONI (400%)")
        crops = {"Crop citra asli (tanpa watermark)": cover}
        crops.update({f"Crop Zoom RONI Payload {i}": ss.payload_wm[i] for i in (1, n_last)})
        peak = max(1, max(int(a[y0:y0 + s_, x0:x0 + s_].max()) for a in crops.values()))
        z = st.columns(3)
        for col, (label, arr) in zip(z, crops.items()):
            n_chg = int(np.sum(arr[y0:y0 + s_, x0:x0 + s_] != cover[y0:y0 + s_, x0:x0 + s_]))
            col.image(zoom_crop(arr, y0, x0, s_, peak), caption=f"{label} - {n_chg} piksel berubah")
        st.caption(f"Kotak {s_}x{s_} piksel di sisi kanan (x={x0}, y={y0}), dipilih otomatis sebagai area RONI yang "
                   f"paling hitam. Di area ini piksel asli bernilai 0 dan setelah watermark menjadi 0 atau 1. "
                   f"Beda 1 tingkat abu-abu tidak terlihat mata, jadi kontras ketiga crop diregangkan dengan skala "
                   f"yang sama (nilai {peak} ditampilkan putih), lalu diperbesar 400% tanpa penghalusan.")


# ---------------------------------------------------------------- about
else:
    st.header("About MedSecure-XR")
    st.markdown("""
**Problem.** Chest X-ray images and patient identities are health data (specific personal data under Article 4 of Indonesian Law 27/2022).
When exchanged between facilities, images can be intercepted, assigned to the wrong patient, or edited in the diagnostic area.

**Solution (2 methods).**
1. **Watermarking**: fragile LSB in **RONI** only (automatically detected dark background) → the diagnostic area is never modified.
2. **Cryptography**: AES-GCM (EPR), per-block HMAC-SHA256 (localization), Ed25519 (doctor signature), AES-SIV (image).

**Limitations.** The watermark is intentionally *fragile*: lossy compression is treated as tampering. The image must contain a background area.
Key distribution is outside this demo's scope.
""")
