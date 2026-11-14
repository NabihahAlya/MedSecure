"""
MedSecure-XR — Streamlit demo.

Run:
    pip install -r requirements.txt
    streamlit run app.py
"""

import io
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

import core as C

APP_DIR = Path(__file__).resolve().parent
SAMPLE = APP_DIR / "sample_xray.jpg"

DEFAULT_EPR = [
    ("Nama RS", "RS UM Sejahtera"),
    ("Tanggal", "4 November 2026"),
    ("No. Rekam Medis", "RM-2026-001234"),
    ("Nama Pasien", "Nabihah Alya Az Zahidah"),
    ("TTL", "24 Januari 2026"),
    ("Jam", "21:57"),
    ("Jenis Kelamin", "Female"),
    ("Golongan Darah", "B"),
    ("Alamat Pasien", "Jalan Semarang"),
    ("Nama Dokter", "Taharo Hafwenia"),
    ("Jenis Pemeriksaan", "Rontgen Thorax PA"),
]
FIELD_COUNTS = [1, 2, 3, 5, 6, 7, 8, 9, 10, 11]

st.set_page_config(page_title="MedSecure-XR", page_icon="🩻", layout="wide")
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
        rows.append({"Field": k, "Isi": v})
    return pd.DataFrame(rows)


def fmt_db(x):
    return "∞ (tidak berubah)" if x == float("inf") else f"{x:.2f} dB"


def need_keys():
    if ss.kb is None:
        ss.kb = C.KeyBundle.generate()
    return ss.kb


def check_row(label, ok, detail=""):
    icon = "✅" if ok else "❌"
    st.markdown(f"{icon} **{label}** {detail}")


# ---------------------------------------------------------------- sidebar
st.sidebar.title("🩻 MedSecure-XR")
st.sidebar.caption("Watermarking RONI + Kriptografi untuk citra rontgen dada")
page = st.sidebar.radio("Menu", ["1. Kunci", "2. Pengirim (RS asal)", "3. Penerima (RS tujuan)",
                                 "4. Simulasi Serangan", "5. Evaluasi 10 Payload", "Tentang"])
keys = need_keys()
st.sidebar.markdown(f"**Kunci publik dokter**  \n`{keys.fingerprint()}`")
st.sidebar.caption("Demo: semua kunci dibuat di sesi ini. Pada sistem nyata kunci dikelola terpisah per peran.")


# ---------------------------------------------------------------- 1. keys
if page == "1. Kunci":
    st.header("1. Manajemen Kunci (demo)")
    st.markdown(
        "| Kunci | Algoritma | Fungsi |\n|---|---|---|\n"
        "| `k_img` | AES-256-SIV (512 bit) | Enkripsi seluruh citra saat dikirim + tag integritas |\n"
        "| `k_epr` | AES-256-GCM | Kerahasiaan data pasien (EPR) di dalam watermark |\n"
        "| `k_wm` | HMAC-SHA256 | Tag per blok 32×32 (lokalisasi manipulasi) + urutan penyisipan |\n"
        "| `sk/pk` | Ed25519 | Tanda tangan digital dokter |")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔑 Bangkitkan kunci baru"):
            ss.kb = C.KeyBundle.generate()
            ss.protected = ss.package = None
            st.success(f"Kunci baru dibuat. Fingerprint: {ss.kb.fingerprint()}")
        st.download_button("⬇️ Unduh kunci (JSON, RAHASIA)", ss.kb.to_json(), file_name="medsecure_keys.json",
                           mime="application/json")
    with c2:
        up = st.file_uploader("Muat kunci dari JSON", type=["json"])
        if up is not None:
            try:
                ss.kb = C.KeyBundle.from_json(up.getvalue().decode())
                st.success(f"Kunci dimuat. Fingerprint: {ss.kb.fingerprint()}")
            except Exception as e:  # noqa: BLE001
                st.error(f"File kunci tidak valid: {e}")
    st.warning("File kunci berisi kunci privat. Jangan diunggah ke repositori publik atau dibagikan.")


# ---------------------------------------------------------------- 2. sender
elif page == "2. Pengirim (RS asal)":
    st.header("2. Pengirim — sisipkan EPR bertanda tangan, lalu enkripsi citra")
    up = st.file_uploader("Unggah citra rontgen dada (PNG/JPG)", type=["png", "jpg", "jpeg"])
    use_sample = SAMPLE.exists() and st.checkbox("Pakai citra contoh", value=up is None)
    src = up if up is not None else (str(SAMPLE) if use_sample else None)

    st.subheader("Data rekam medis (EPR)")
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
        st.caption(f"Ukuran asli {orig[0]}×{orig[1]} → {cover.shape[1]}×{cover.shape[0]} | "
                   f"RONI {cap} piksel ({100 * cap / cover.size:.1f}%) | kebutuhan {need} bit "
                   f"({100 * need / max(cap, 1):.1f}% RONI)")
        c1, c2 = st.columns(2)
        c1.image(cover, caption="Cover (grayscale)")
        c2.image(C.overlay_mask(cover, mask), caption="RONI terdeteksi otomatis (biru) = area penyisipan")

        if st.button("🔒 Lindungi & enkripsi", type="primary"):
            try:
                with st.spinner("Memproses..."):
                    res = C.protect(cover, epr_text, keys)
            except C.WatermarkError as e:
                st.error(str(e))
            else:
                ss.cover, ss.protected, ss.epr_text = cover, res, epr_text
                ss.package = C.pack_package(res["encrypted"], res["meta"], res["mode"])
                st.success("Citra berhasil dilindungi.")

        res = ss.protected
        if res is not None and ss.cover is not None and ss.cover.shape == cover.shape:
            wm, roi = res["watermarked"], ~res["mask"]
            m = st.columns(5)
            m[0].metric("PSNR seluruh citra", fmt_db(C.psnr(cover, wm)))
            m[1].metric("PSNR area diagnosis (ROI)", fmt_db(C.psnr_region(cover, wm, roi)))
            m[2].metric("SSIM", f"{C.ssim(cover, wm):.6f}")
            m[3].metric("Bit disisipkan", f"{res['bits'].size}")
            m[4].metric("Waktu total", f"{1000 * sum(res['times'].values()):.1f} ms")
            c1, c2, c3 = st.columns(3)
            c1.image(wm, caption="Ber-watermark")
            diff = (np.abs(cover.astype(np.int16) - wm.astype(np.int16)) * 255).clip(0, 255).astype(np.uint8)
            c2.image(diff, caption="Selisih ×255 (hanya di RONI)")
            c3.image(res["encrypted"], caption="Terenkripsi AES-256-SIV (yang dikirim)")
            d1, d2 = st.columns(2)
            d1.download_button("⬇️ Unduh paket terenkripsi (.msx)", ss.package, file_name="xray_package.msx",
                               mime="application/octet-stream")
            d2.download_button("⬇️ Unduh citra ber-watermark (PNG)", C.to_png_bytes(wm), file_name="watermarked.png",
                               mime="image/png")
            st.dataframe(pd.DataFrame([{"tahap": k, "ms": round(1000 * v, 3)} for k, v in res["times"].items()]),
                         hide_index=True)
    else:
        st.info("Unggah citra rontgen untuk mulai.")


# ---------------------------------------------------------------- 3. receiver
elif page == "3. Penerima (RS tujuan)":
    st.header("3. Penerima — dekripsi, verifikasi, baca EPR")
    up = st.file_uploader("Unggah paket .msx", type=["msx"])
    data = up.getvalue() if up is not None else ss.package
    if data is None:
        st.info("Belum ada paket. Buat di menu Pengirim atau unggah file .msx.")
    else:
        st.caption("Sumber: file unggahan" if up is not None else "Sumber: paket terakhir dari menu Pengirim")
        if st.button("🔓 Dekripsi & verifikasi", type="primary"):
            try:
                enc, meta, mode = C.unpack_package(data)
            except ValueError as e:
                st.error(str(e))
            else:
                r = C.receive(enc, meta, keys, keys.public_key, mode)
                if r["status"] == "AMAN":
                    st.success(f"AMAN — {r['message']}")
                elif r["status"] == "DITOLAK":
                    st.error(f"DITOLAK — {r['message']}")
                else:
                    st.warning(f"DIMANIPULASI — {r['message']}")
                check_row("Integritas transmisi (tag AES-SIV)", r["transit_ok"])
                if r["transit_ok"]:
                    check_row("Watermark ditemukan di RONI", r["watermark_found"])
                    check_row("Tanda tangan dokter (Ed25519)", r["signature_ok"], f"— kunci `{keys.fingerprint()}`")
                    check_row("Semua blok citra utuh (HMAC per blok)", r["n_tampered"] == 0,
                              "" if r["n_tampered"] is None else f"— {r['n_tampered']} blok berubah")
                    check_row("EPR terdekripsi (AES-GCM)", r["epr_ok"])
                    c1, c2 = st.columns(2)
                    c1.image(r["image"], caption="Citra hasil dekripsi")
                    if r["tamper_map"] is not None:
                        c2.image(C.tamper_overlay(r["image"], r["tamper_map"]),
                                 caption="Peta manipulasi (merah = blok berubah)")
                    if r["epr_ok"]:
                        st.subheader("Data pasien")
                        st.dataframe(text_to_epr(r["epr"]), hide_index=True)
                st.dataframe(pd.DataFrame([{"tahap": k, "ms": round(1000 * v, 3)} for k, v in r["times"].items()]),
                             hide_index=True)


# ---------------------------------------------------------------- 4. attacks
elif page == "4. Simulasi Serangan":
    st.header("4. Simulasi serangan pada citra ber-watermark")
    if ss.protected is None:
        st.info("Lindungi sebuah citra dulu di menu Pengirim.")
    else:
        wm = ss.protected["watermarked"]
        h, w = wm.shape
        kind = st.selectbox("Jenis serangan", list(C.ATTACKS), format_func=lambda k: C.ATTACKS[k])
        local = kind not in ("noise", "jpeg")
        bx, by, bw, bh = C.default_box(wm.shape)
        if local:
            c = st.columns(4)
            bx = c[0].slider("x", 0, w - 16, bx)
            by = c[1].slider("y", 0, h - 16, by)
            bw = c[2].slider("lebar", 8, w // 2, bw)
            bh = c[3].slider("tinggi", 8, h // 2, bh)
        if st.button("⚔️ Jalankan serangan", type="primary"):
            box = (bx, by, min(bw, w - bx), min(bh, h - by))
            a = C.attack(wm, kind, box)
            r = C.verify_image(a, keys, keys.public_key)
            gt = C.block_ground_truth(wm, a)
            (st.success if r["status"] == "AMAN" else st.warning)(f"{r['status']} — {r['message']}")
            c1, c2, c3 = st.columns(3)
            c1.image(wm, caption="Sebelum diserang")
            c2.image(a, caption="Sesudah diserang")
            if r["tamper_map"] is not None:
                c3.image(C.tamper_overlay(a, r["tamper_map"]), caption="Hasil deteksi (merah)")
                s = C.localization_scores(r["tamper_map"], gt)
                m = st.columns(4)
                m[0].metric("Piksel diubah", int(np.sum(a != wm)))
                m[1].metric("Blok benar-benar diubah", int(gt.sum()))
                m[2].metric("TPR (deteksi)", f"{s['TPR']:.3f}")
                m[3].metric("FPR (salah tuduh)", f"{s['FPR']:.3f}")
            else:
                c3.info("Watermark rusak total (serangan global). Citra dinyatakan tidak asli; "
                        "lokalisasi tidak tersedia karena watermark bersifat fragile.")


# ---------------------------------------------------------------- 5. evaluation
elif page == "5. Evaluasi 10 Payload":
    st.header("5. Evaluasi 10 payload (ketentuan tugas)")
    up = st.file_uploader("Citra uji (opsional, default: citra contoh)", type=["png", "jpg", "jpeg"])
    src = up if up is not None else (str(SAMPLE) if SAMPLE.exists() else None)
    if src is None:
        st.info("Unggah citra uji.")
    elif st.button("▶️ Jalankan evaluasi", type="primary"):
        cover, _ = C.load_cover(src)
        payloads = [epr_to_text(DEFAULT_EPR[:n]) for n in FIELD_COUNTS]
        rows = []
        prog = st.progress(0.0)
        for i, p in enumerate(payloads, 1):
            res = C.protect(cover, p, keys)
            r = C.receive(res["encrypted"], res["meta"], keys, keys.public_key)
            wm, enc, roi = res["watermarked"], res["encrypted"], ~res["mask"]
            n_, u_ = C.differential_test(wm, keys.k_img)
            rows.append({"payload": i, "epr_bytes": len(p.encode()), "bit_disisipkan": int(res["bits"].size),
                         "bpp": res["bits"].size / cover.size, "MSE": C.mse(cover, wm), "PSNR_dB": C.psnr(cover, wm),
                         "PSNR_ROI": "inf" if C.psnr_region(cover, wm, roi) == float("inf") else "berubah",
                         "SSIM": C.ssim(cover, wm), "entropi_cipher": C.entropy(enc),
                         "korelasiH_cipher": C.adjacent_correlation(enc)["H"], "NPCR_%": n_, "UACI_%": u_,
                         "BER": C.ber(res["bits"], r["bits"]), "NC": C.nc(res["bits"], r["bits"]),
                         "hash_cocok": C.sha256_img(r["image"]) == C.sha256_img(wm),
                         "EPR_cocok": r["epr"] == p, "status": r["status"],
                         "waktu_kirim_ms": 1000 * sum(res["times"].values()),
                         "waktu_terima_ms": 1000 * sum(r["times"].values())})
            prog.progress(i / len(payloads))
        df = pd.DataFrame(rows)
        st.dataframe(df.round(6), hide_index=True)
        c1, c2 = st.columns(2)
        c1.markdown("**PSNR seluruh citra (dB)**"); c1.line_chart(df.set_index("payload")["PSNR_dB"])
        c2.markdown("**SSIM**"); c2.line_chart(df.set_index("payload")["SSIM"])
        c1.markdown("**NPCR / UACI diferensial (%)**"); c1.line_chart(df.set_index("payload")[["NPCR_%", "UACI_%"]])
        c2.markdown("**Waktu proses (ms)**"); c2.bar_chart(df.set_index("payload")[["waktu_kirim_ms", "waktu_terima_ms"]])
        st.download_button("⬇️ Unduh hasil (CSV)", df.to_csv(index=False), file_name="evaluasi_10_payload.csv",
                           mime="text/csv")
        st.subheader("Perbandingan mode AES (uji diferensial, key & IV sama)")
        wm10 = C.protect(cover, payloads[-1], keys)["watermarked"]
        cmp_rows = []
        for m in ["siv", "ctr", "cbc"]:
            n_, u_ = C.differential_test(wm10, keys.k_img, m)
            cmp_rows.append({"mode": f"AES-256-{m.upper()}", "NPCR_%": round(n_, 4), "UACI_%": round(u_, 4)})
        st.dataframe(pd.DataFrame(cmp_rows), hide_index=True)
        st.caption("Ideal citra 8-bit: NPCR ≈ 99,61%, UACI ≈ 33,46%. CTR/CBC dengan IV sama gagal menyebarkan perubahan.")


# ---------------------------------------------------------------- about
else:
    st.header("Tentang MedSecure-XR")
    st.markdown("""
**Masalah.** Citra rontgen dan identitas pasien termasuk data kesehatan (data pribadi spesifik, UU 27/2022 Pasal 4).
Saat dipertukarkan antar-fasilitas, citra bisa disadap, ditukar pemiliknya, atau diedit di area diagnosis.

**Solusi (2 metode).**
1. **Watermarking** fragile LSB hanya di **RONI** (latar gelap yang dideteksi otomatis) → area diagnosis tidak diubah.
2. **Kriptografi**: AES-GCM (EPR), HMAC-SHA256 per blok (lokalisasi), Ed25519 (tanda tangan dokter), AES-SIV (citra).

**Batasan.** Watermark sengaja *fragile*: kompresi lossy dianggap manipulasi. Citra harus punya area latar.
Distribusi kunci di luar cakupan demo.
""")
