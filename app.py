"""
MedSecure-XR — Streamlit demo.

Run:
    pip install -r requirements.txt
    streamlit run app.py
"""

import base64
import io
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

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
    "About": ("About", "info"),
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
    [data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] {
        min-height: calc(100vh - 7.5rem);
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
    .stButton > button, .stDownloadButton > button {
        background: var(--teal) !important;
        color: #ffffff !important;
        border: 1px solid var(--teal) !important;
        border-radius: 8px;
        font-weight: 700;
        box-shadow: 0 4px 10px rgba(15, 157, 138, .18);
    }
    .stButton > button *, .stDownloadButton > button * { color: #ffffff !important; }
    .stButton > button:hover, .stDownloadButton > button:hover {
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


# ---------------------------------------------------------------- sidebar
st.sidebar.caption("RONI watermarking + cryptography for chest X-ray images")
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
    st.warning("This key file contains private keys. Do not upload it to a public repository or share it.",
               icon=":material/shield_lock:")


# ---------------------------------------------------------------- 2. sender
elif page == "2. Sender (origin hospital)":
    st.header("Sender")
    up = st.file_uploader("Upload chest X-ray image (PNG/JPG)", type=["png", "jpg", "jpeg"])
    use_sample = SAMPLE.exists() and st.checkbox("Use sample image", value=up is None)
    src = up if up is not None else (str(SAMPLE) if use_sample else None)

    st.subheader("Electronic patient record (EPR)")
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
        st.caption(f"Original size {orig[0]}×{orig[1]} → {cover.shape[1]}×{cover.shape[0]} | "
                   f"RONI {cap} pixels ({100 * cap / cover.size:.1f}%) | required {need} bits "
                   f"({100 * need / max(cap, 1):.1f}% RONI)")
        c1, c2 = st.columns(2)
        c1.image(cover, caption="Cover (grayscale)")
        c2.image(C.overlay_mask(cover, mask), caption="Automatically detected RONI (blue) = embedding area")

        if st.button("Protect & encrypt", type="primary", icon=":material/lock:"):
            try:
                with st.spinner("Processing..."):
                    res = C.protect(cover, epr_text, keys)
            except C.WatermarkError as e:
                st.error(str(e), icon=":material/error:")
            else:
                ss.cover, ss.protected, ss.epr_text = cover, res, epr_text
                ss.package = C.pack_package(res["encrypted"], res["meta"], res["mode"])
                st.success("Image protected successfully.", icon=":material/verified_user:")

        res = ss.protected
        if res is not None and ss.cover is not None and ss.cover.shape == cover.shape:
            wm, roi = res["watermarked"], ~res["mask"]
            st.markdown("**Image quality (cover vs watermarked)**")
            m = st.columns(5)
            m[0].metric("MSE", f"{C.mse(cover, wm):.6f}")
            m[1].metric("PSNR (full image)", fmt_db(C.psnr(cover, wm)))
            m[2].metric("PSNR (diagnostic ROI)", fmt_db(C.psnr_region(cover, wm, roi)))
            m[3].metric("SSIM", f"{C.ssim(cover, wm):.6f}")
            m[4].metric("SNR", fmt_db(C.snr(cover, wm)))
            m = st.columns(5)
            m[0].metric("Embedded bits", f"{res['bits'].size}")
            m[1].metric("Total time", f"{1000 * sum(res['times'].values()):.1f} ms")
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
                                 caption="Tamper map (red = changed block)")
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
        kind = st.selectbox("Attack type", list(C.ATTACKS), format_func=lambda k: C.ATTACKS[k])
        local = kind not in ("noise", "jpeg")
        bx, by, bw, bh = C.default_box(wm.shape)
        if local:
            c = st.columns(4)
            bx = c[0].slider("x", 0, w - 16, bx)
            by = c[1].slider("y", 0, h - 16, by)
            bw = c[2].slider("width", 8, w // 2, bw)
            bh = c[3].slider("height", 8, h // 2, bh)
        if st.button("Run attack", type="primary", icon=":material/bolt:"):
            box = (bx, by, min(bw, w - bx), min(bh, h - by))
            a = C.attack(wm, kind, box)
            r = C.verify_image(a, keys, keys.public_key)
            gt = C.block_ground_truth(wm, a)
            show_status(r)
            c1, c2, c3 = st.columns(3)
            c1.image(wm, caption="Before attack")
            c2.image(a, caption="After attack")
            if r["tamper_map"] is not None:
                c3.image(C.tamper_overlay(a, r["tamper_map"]), caption="Detection result (red)")
                s = C.localization_scores(r["tamper_map"], gt)
                m = st.columns(4)
                m[0].metric("Changed pixels", int(np.sum(a != wm)))
                m[1].metric("Actually changed blocks", int(gt.sum()))
                m[2].metric("TPR (detection)", f"{s['TPR']:.3f}")
                m[3].metric("FPR (false alarm)", f"{s['FPR']:.3f}")
            else:
                c3.info("Watermark fully damaged (global attack). The image is deemed inauthentic; "
                        "localization is unavailable because the watermark is fragile.", icon=":material/gpp_bad:")


# ---------------------------------------------------------------- 5. evaluation
elif page == "5. Evaluate 10 Payloads":
    st.header("Evaluate")
    up = st.file_uploader("Test image (optional; sample image by default)", type=["png", "jpg", "jpeg"])
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
        st.subheader("AES mode comparison (differential test; same key & IV)")
        wm10 = C.protect(cover, payloads[-1], keys)["watermarked"]
        cmp_rows = []
        for m in ["siv", "ctr", "cbc"]:
            n_, u_ = C.differential_test(wm10, keys.k_img, m)
            cmp_rows.append({"mode": f"AES-256-{m.upper()}", "NPCR_%": round(n_, 4), "UACI_%": round(u_, 4)})
        st.dataframe(pd.DataFrame(cmp_rows), hide_index=True)
        st.caption("Ideal 8-bit image: NPCR ≈ 99.61%, UACI ≈ 33.46%. CTR/CBC with the same IV do not diffuse changes.")


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
