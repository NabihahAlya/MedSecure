"""Build the Colab notebook from core.py + experiment cells.

Usage: python tools/build_notebook.py <out.ipynb> <flat_test.py>
The flat script is the same code without '!pip' lines, used to test locally.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
core = (ROOT / "core.py").read_text()

# ---- split core.py into sections on the "# ---...\n# Title\n# ---..." markers
parts = re.split(r"\n# -{70,}\n# (.+)\n# -{70,}\n", core)
preamble, sections = parts[0], dict(zip(parts[1::2], parts[2::2]))
imports = preamble.split('"""', 2)[2]          # code after the module docstring
imports = "\n".join(l for l in imports.splitlines() if "__future__" not in l)
imports = re.sub(r"\n\s*\n", "\n", imports).strip()

cells = []
def md(s): cells.append(("markdown", s.strip("\n")))
def code(s): cells.append(("code", s.strip("\n")))

md("""
# MedSecure-XR — Kriptografi + Watermarking pada Citra Rontgen Dada
**Tugas Akhir Keamanan Data · Capstone 2026 cabang Kriptografi dan Keamanan Data**

Dua metode yang digabung:
1. **Watermarking**: watermark *fragile* LSB yang disisipkan **hanya di RONI** (latar gelap), sehingga area diagnosis (ROI) tidak berubah sama sekali.
2. **Kriptografi**: AES-256-GCM (kerahasiaan EPR), HMAC-SHA256 per blok (lokalisasi manipulasi), Ed25519 (tanda tangan dokter), AES-256-SIV (enkripsi seluruh citra saat dikirim).

Alur pengirim: cover → deteksi RONI → [EPR terenkripsi | tag blok | tanda tangan] → sisip LSB di RONI → enkripsi AES-SIV.
Alur penerima: dekripsi AES-SIV → ekstraksi watermark → verifikasi tanda tangan → peta manipulasi → dekripsi EPR.

Jalankan dari atas ke bawah: **Runtime → Run all**.
""")

md("## 0. Install & import")
code("!pip install -q cryptography scikit-image openpyxl\n\n" + imports + """
import shutil, tracemalloc
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

pd.set_option("display.max_columns", 60)
pd.set_option("display.width", 220)
print("Import OK")
""")

md("""
## 1. Konfigurasi
Ukuran citra: tinggi 512 piksel, lebar mengikuti rasio asli (dibulatkan ke kelipatan 32), **tanpa center-crop**.
Center-crop sempat membuat paru menempel di tepi gambar sehingga terbaca sebagai latar (RONI) — kesalahan itu dihindari di sini.
""")
code(sections["Configuration"].strip() + """

MODE = "siv"     # "siv" (dipakai) | "ctr" | "cbc" (pembanding)
REPEAT = 5       # ulangan untuk rata-rata waktu proses
OUT_DIR = Path("output"); OUT_DIR.mkdir(exist_ok=True)

# Data EPR (data fiktif untuk pengujian). Urutan mengikuti tabel tugas.
FIELDS = [
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
# jumlah field untuk payload 1..10 (payload 4 menambah Nama Pasien + TTL)
FIELD_COUNTS = [1, 2, 3, 5, 6, 7, 8, 9, 10, 11]
""")

md("## 2. Upload citra rontgen (cover)")
code("""
try:
    from google.colab import files
    uploaded = files.upload()          # pilih file X-ray
    COVER_PATH = next(iter(uploaded))
except ImportError:
    COVER_PATH = "sample_xray.jpg"     # di luar Colab: isi path manual
print("Cover:", COVER_PATH)
""")

md("## 3. Library inti\n### 3.1 Kunci (AES-SIV, AES-GCM, HMAC, Ed25519)")
code(sections["Keys"])
md("### 3.2 Prapemrosesan & deteksi RONI otomatis")
code(sections["Preprocessing and RONI detection"])
md("### 3.3 Blok kriptografi: tag HMAC per blok, pesan tanda tangan, enkripsi citra")
code(sections["Cryptographic building blocks"])
md("### 3.4 Struktur payload watermark")
code(sections["Watermark payload"])
md("### 3.5 Pengirim: `protect()`")
code(sections["Sender: protect"])
md("### 3.6 Penerima: ekstraksi, verifikasi, peta manipulasi")
code(sections["Receiver: extract and verify"])
md("### 3.7 Paket transmisi (1 file)")
code(sections["Transport package (single file)"])
md("### 3.8 Metrik evaluasi")
code(sections["Metrics"])
md("### 3.9 Simulasi serangan & skor lokalisasi")
code(sections["Attack simulation"])
md("### 3.10 Helper visual")
code(sections["Visual helpers"])

md("## Tahap A — Persiapan\n### A1. Load cover, deteksi RONI, kapasitas")
code("""
cover, orig_size = load_cover(COVER_PATH)
Image.fromarray(cover).save(OUT_DIR / "cover.png")      # lossless
MASK = roni_mask(cover)
ROI = ~MASK
N_PIXELS = cover.size
CAP_BITS = capacity_bits(MASK)
print(f"Ukuran asli {orig_size} -> cover {cover.shape[1]}x{cover.shape[0]} ({N_PIXELS} piksel)")
print(f"RONI: {CAP_BITS} piksel ({100*CAP_BITS/N_PIXELS:.1f}%) = kapasitas {CAP_BITS} bit")
print(f"Overhead tetap (header+nonce+tag GCM+tag blok+tanda tangan): {overhead_bytes(cover.shape)} byte")
print(f"Kapasitas maksimum EPR: {max_epr_bytes(cover)} byte")

fig, ax = plt.subplots(1, 2, figsize=(14, 5))
ax[0].imshow(cover, cmap="gray", vmin=0, vmax=255); ax[0].set_title("Cover"); ax[0].axis("off")
ax[1].imshow(overlay_mask(cover, MASK)); ax[1].set_title("RONI terdeteksi (biru) = area penyisipan"); ax[1].axis("off")
fig.tight_layout(); fig.savefig(OUT_DIR / "fig_roni.png", dpi=150); plt.show()
""")

md("### A2–A3. 10 payload EPR, ukuran & capacity (bpp)")
code("""
def build_payloads():
    return ["; ".join(f"{k}: {v}" for k, v in FIELDS[:n]) for n in FIELD_COUNTS]

payloads = build_payloads()
OVH = overhead_bytes(cover.shape)
rows_p = []
for i, p in enumerate(payloads, 1):
    epr_b = len(p.encode("utf-8"))
    total_bits = (OVH + epr_b) * 8
    rows_p.append({"payload": i, "fields": FIELD_COUNTS[i-1], "epr_bytes": epr_b, "epr_bits": epr_b * 8,
                   "total_embedded_bits": total_bits, "bpp_image": total_bits / N_PIXELS,
                   "roni_used_%": 100 * total_bits / CAP_BITS, "fits": total_bits <= CAP_BITS, "text": p})
df_payload = pd.DataFrame(rows_p)
assert df_payload["fits"].all(), "Ada payload yang tidak muat di RONI!"
df_payload.to_csv(OUT_DIR / "payloads.csv", index=False)
df_payload
""")

md("### A4. Kunci (demo: dibangkitkan sekali, simpan aman — jangan dibagikan)")
code("""
KEYS = KeyBundle.generate()
(OUT_DIR / "keys_DEMO_JANGAN_DIBAGIKAN.json").write_text(KEYS.to_json())
print("Fingerprint kunci publik dokter:", KEYS.fingerprint())
""")

md("## Tahap B — Loop 10 payload")
code("""
def run_once(payload):
    p = protect(cover, payload, KEYS, MODE)
    v = receive(p["encrypted"], p["meta"], KEYS, KEYS.public_key, MODE)
    return p, v

def peak_memory_kb(payload):
    tracemalloc.start(); run_once(payload)
    _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    return peak / 1024

run_once(payloads[0])   # warm-up
STAGES_P = ["roni_mask", "epr_encrypt", "block_tags", "sign", "embed", "img_encrypt"]
STAGES_V = ["img_decrypt", "extract", "verify_sig", "tamper_check", "epr_decrypt"]

rows, results = [], {}
for i, payload in enumerate(payloads, 1):
    acc = {k: [] for k in STAGES_P + STAGES_V}
    for _ in range(REPEAT):
        p, v = run_once(payload)
        for k in STAGES_P: acc[k].append(p["times"][k])
        for k in STAGES_V: acc[k].append(v["times"][k])
    wm, enc = p["watermarked"], p["encrypted"]
    cp, cc = adjacent_correlation(wm), adjacent_correlation(enc)
    npcr_pc, uaci_pc = npcr_uaci(wm, enc)
    npcr_d, uaci_d = differential_test(wm, KEYS.k_img, MODE)
    row = {
        "payload": i, "epr_bytes": len(payload.encode()), "embedded_bits": int(p["bits"].size),
        "bpp_image": p["bits"].size / N_PIXELS, "roni_used_%": 100 * p["bits"].size / CAP_BITS,
        "changed_px": int(np.sum(cover != wm)), "changed_px_ROI": int(np.sum((cover != wm) & ROI)),
        "MSE": mse(cover, wm), "PSNR_dB": psnr(cover, wm), "PSNR_ROI_dB": psnr_region(cover, wm, ROI),
        "SSIM": ssim(cover, wm),
        "entropy_plain": entropy(wm), "entropy_cipher": entropy(enc),
        "corrH_plain": cp["H"], "corrV_plain": cp["V"], "corrD_plain": cp["D"],
        "corrH_cipher": cc["H"], "corrV_cipher": cc["V"], "corrD_cipher": cc["D"],
        "NPCR_plain_vs_cipher_%": npcr_pc, "UACI_plain_vs_cipher_%": uaci_pc,
        "NPCR_diff_1px_%": npcr_d, "UACI_diff_1px_%": uaci_d,
        "hash_match": sha256_img(v["image"]) == sha256_img(wm),
        "BER": ber(p["bits"], v["bits"]), "NC": nc(p["bits"], v["bits"]),
        "signature_ok": v["signature_ok"], "tampered_blocks": v["n_tampered"],
        "epr_match": v["epr"] == payload, "status": v["status"],
        **{f"t_{k}_ms": 1000 * np.mean(acc[k]) for k in STAGES_P + STAGES_V},
        "peak_mem_KB": peak_memory_kb(payload),
    }
    row["t_sender_ms"] = sum(row[f"t_{k}_ms"] for k in STAGES_P)
    row["t_receiver_ms"] = sum(row[f"t_{k}_ms"] for k in STAGES_V)
    rows.append(row)
    results[i] = {"p": p, "v": v}

    pdir = OUT_DIR / f"payload_{i:02d}"; pdir.mkdir(exist_ok=True)
    Image.fromarray(wm).save(pdir / "watermarked.png")
    Image.fromarray(enc).save(pdir / "encrypted_preview.png")
    (pdir / "package.msx").write_bytes(pack_package(enc, p["meta"], MODE))
    Image.fromarray(v["image"]).save(pdir / "decrypted.png")
    diff = (np.abs(cover.astype(np.int16) - wm.astype(np.int16)) * 255).clip(0, 255).astype(np.uint8)
    Image.fromarray(diff).save(pdir / "diff_x255.png")
    (pdir / "epr_extracted.txt").write_text(v["epr"], encoding="utf-8")
    print(f"[{i:02d}] EPR {row['epr_bytes']:3d} B | PSNR {row['PSNR_dB']:.2f} dB | PSNR_ROI {row['PSNR_ROI_dB']} | "
          f"SSIM {row['SSIM']:.6f} | H(c) {row['entropy_cipher']:.4f} | NPCR {npcr_d:.2f}% | BER {row['BER']:.0f} | {v['status']}")

df = pd.DataFrame(rows)
df.to_csv(OUT_DIR / "results.csv", index=False)
df.to_excel(OUT_DIR / "results.xlsx", index=False)
print("\\nSemua payload lolos:", bool(df["hash_match"].all() and df["epr_match"].all() and df["signature_ok"].all()))
""")

md("## Tabel hasil")
code("""
cols = ["payload", "epr_bytes", "embedded_bits", "bpp_image", "changed_px", "changed_px_ROI", "MSE", "PSNR_dB",
        "PSNR_ROI_dB", "SSIM", "BER", "NC", "hash_match", "signature_ok", "epr_match"]
df[cols].round(6)
""")
code("""
df[["payload", "entropy_plain", "entropy_cipher", "corrH_plain", "corrH_cipher", "corrV_cipher", "corrD_cipher",
    "NPCR_plain_vs_cipher_%", "NPCR_diff_1px_%", "UACI_diff_1px_%"]].round(6)
""")
code("""
df[["payload", "epr_bytes"] + [f"t_{k}_ms" for k in STAGES_P + STAGES_V] + ["t_sender_ms", "t_receiver_ms", "peak_mem_KB"]].round(3)
""")

md("## Grafik per payload")
code("""
x = df["payload"]
fig, ax = plt.subplots(1, 3, figsize=(15, 4))
for a, col, title in zip(ax, ["PSNR_dB", "SSIM", "MSE"], ["PSNR seluruh citra (dB)", "SSIM", "MSE"]):
    a.plot(x, df[col], "o-"); a.set_title(title); a.set_xlabel("Payload ke-"); a.set_xticks(x); a.grid(alpha=.3)
fig.suptitle("Kualitas citra ber-watermark (PSNR area ROI = tak hingga untuk semua payload)")
fig.tight_layout(); fig.savefig(OUT_DIR / "fig_kualitas.png", dpi=150); plt.show()

fig, ax = plt.subplots(figsize=(7, 4))
ax.bar(x, df["epr_bytes"]); ax.set_xlabel("Payload ke-"); ax.set_ylabel("Ukuran EPR (byte)"); ax.set_xticks(x)
ax2 = ax.twinx(); ax2.plot(x, df["roni_used_%"], "o-", color="tab:red"); ax2.set_ylabel("RONI terpakai (%)")
ax.set_title("Ukuran payload & pemakaian kapasitas RONI"); fig.tight_layout()
fig.savefig(OUT_DIR / "fig_payload_capacity.png", dpi=150); plt.show()

fig, ax = plt.subplots(1, 2, figsize=(12, 4))
ax[0].plot(x, df["entropy_cipher"], "o-", label="cipher"); ax[0].plot(x, df["entropy_plain"], "s--", label="watermarked")
ax[0].axhline(8, color="gray", ls=":"); ax[0].set_title("Entropi (ideal 8)"); ax[0].legend()
ax[1].plot(x, df["NPCR_diff_1px_%"], "o-", label="NPCR"); ax[1].plot(x, df["UACI_diff_1px_%"], "s-", label="UACI")
ax[1].axhline(99.6094, color="gray", ls=":"); ax[1].axhline(33.4635, color="gray", ls=":")
ax[1].set_title("NPCR & UACI diferensial 1 piksel (%)"); ax[1].legend()
for a in ax: a.set_xlabel("Payload ke-"); a.set_xticks(x); a.grid(alpha=.3)
fig.tight_layout(); fig.savefig(OUT_DIR / "fig_enkripsi.png", dpi=150); plt.show()

fig, ax = plt.subplots(figsize=(9, 4)); bottom = np.zeros(len(df))
for k in STAGES_P + STAGES_V:
    ax.bar(x, df[f"t_{k}_ms"], bottom=bottom, label=k); bottom += df[f"t_{k}_ms"].values
ax.set_xlabel("Payload ke-"); ax.set_ylabel("ms"); ax.set_xticks(x); ax.set_title("Waktu proses per tahap")
ax.legend(fontsize=7, ncol=2); fig.tight_layout(); fig.savefig(OUT_DIR / "fig_waktu.png", dpi=150); plt.show()
""")

md("## Visualisasi citra (payload ke-10)")
code("""
p10, v10 = results[10]["p"], results[10]["v"]
wm10 = p10["watermarked"]
diff = np.abs(cover.astype(np.int16) - wm10.astype(np.int16)) * 255
fig, ax = plt.subplots(1, 5, figsize=(25, 4.5))
panels = [(cover, "Cover"), (overlay_mask(cover, MASK), "RONI (biru)"), (diff, "Selisih x255 (hanya di RONI)"),
          (p10["encrypted"], "Terenkripsi AES-SIV"), (v10["image"], "Hasil dekripsi")]
for a, (im, t) in zip(ax, panels):
    a.imshow(im, cmap="gray", vmin=0, vmax=255); a.set_title(t); a.axis("off")
fig.tight_layout(); fig.savefig(OUT_DIR / "fig_citra.png", dpi=150); plt.show()

fig, ax = plt.subplots(1, 3, figsize=(15, 4))
for a, im, t in zip(ax, [cover, wm10, p10["encrypted"]], ["Cover", "Watermarked", "Encrypted"]):
    a.hist(im.ravel(), bins=256, range=(0, 256), color="k"); a.set_title(f"Histogram {t}")
fig.tight_layout(); fig.savefig(OUT_DIR / "fig_histogram.png", dpi=150); plt.show()

rng = np.random.default_rng(0)
ri = rng.integers(0, cover.shape[0], 3000); ci = rng.integers(0, cover.shape[1] - 1, 3000)
fig, ax = plt.subplots(1, 2, figsize=(10, 4.5))
for a, im, t in [(ax[0], wm10, "Watermarked"), (ax[1], p10["encrypted"], "Encrypted")]:
    a.scatter(im[ri, ci], im[ri, ci + 1], s=2, alpha=.5)
    a.set_title(f"Korelasi horizontal - {t}"); a.set_xlabel("p(x,y)"); a.set_ylabel("p(x,y+1)")
fig.tight_layout(); fig.savefig(OUT_DIR / "fig_korelasi.png", dpi=150); plt.show()
print("EPR hasil ekstraksi payload 10:\\n", v10["epr"])
""")

md("## Nilai tambah — Security\nKunci salah, ciphertext diubah, kunci dokter palsu, dan perbandingan mode AES (uji diferensial dengan key & IV sama).")
code("""
p10 = results[10]["p"]
tests = []
r_ = receive(p10["encrypted"], p10["meta"], KeyBundle.generate(), KEYS.public_key)
tests.append({"uji": "Dekripsi dengan kunci salah", "hasil": r_["status"], "keterangan": r_["message"]})
bad = p10["encrypted"].copy(); bad[0, 0] ^= 1
r_ = receive(bad, p10["meta"], KEYS, KEYS.public_key)
tests.append({"uji": "1 bit ciphertext diubah saat transmisi", "hasil": r_["status"], "keterangan": r_["message"]})
r_ = verify_image(p10["watermarked"], KEYS, KeyBundle.generate().public_key)
tests.append({"uji": "Verifikasi dengan kunci publik dokter lain", "hasil": r_["status"], "keterangan": r_["message"]})
fake = KeyBundle(KEYS.k_img, KEYS.k_epr, KEYS.k_wm, KeyBundle.generate().signing_key)
forged = protect(cover, payloads[-1].replace("Taharo Hafwenia", "Dokter Palsu"), fake)
r_ = verify_image(forged["watermarked"], KEYS, KEYS.public_key)
tests.append({"uji": "Pemalsu menandatangani ulang dengan kunci sendiri", "hasil": r_["status"], "keterangan": r_["message"]})
df_sec = pd.DataFrame(tests); df_sec.to_csv(OUT_DIR / "security_tests.csv", index=False)
display(df_sec)

cmp_rows = []
for m in ["siv", "ctr", "cbc"]:
    n_, u_ = differential_test(p10["watermarked"], KEYS.k_img, m)
    cmp_rows.append({"mode": f"AES-256-{m.upper()}", "NPCR_%": n_, "UACI_%": u_,
                     "integritas_bawaan": m == "siv"})
df_modes = pd.DataFrame(cmp_rows); df_modes.to_csv(OUT_DIR / "compare_modes.csv", index=False)
df_modes.round(4)
""")

md("## Nilai tambah — Simulasi serangan & lokalisasi manipulasi\nSerangan lokal dilakukan di area paru (ROI). TPR/FPR dihitung per blok 32×32 terhadap ground truth piksel yang benar-benar berubah.")
code("""
att_rows, att_imgs = [], {}
for k, desc in ATTACKS.items():
    a = attack(p10["watermarked"], k)
    vv = verify_image(a, KEYS, KEYS.public_key)
    gt = block_ground_truth(p10["watermarked"], a)
    row = {"serangan": desc, "piksel_berubah": int(np.sum(a != p10["watermarked"])),
           "status": vv["status"], "watermark_terbaca": vv["watermark_found"],
           "tanda_tangan_valid": vv["signature_ok"], "keterangan": vv["message"]}
    if vv["tamper_map"] is not None:
        row.update(localization_scores(vv["tamper_map"], gt))
    att_rows.append(row); att_imgs[k] = (a, vv)
df_att = pd.DataFrame(att_rows); df_att.to_csv(OUT_DIR / "attacks.csv", index=False)
display(df_att)

local = [k for k in ATTACKS if att_imgs[k][1]["tamper_map"] is not None]
fig, ax = plt.subplots(1, len(local), figsize=(5 * len(local), 4))
for a, k in zip(np.atleast_1d(ax), local):
    img_a, vv = att_imgs[k]
    a.imshow(tamper_overlay(img_a, vv["tamper_map"])); a.set_title(ATTACKS[k], fontsize=9); a.axis("off")
fig.suptitle("Peta manipulasi (merah = blok terdeteksi diubah)"); fig.tight_layout()
fig.savefig(OUT_DIR / "fig_serangan.png", dpi=150); plt.show()
""")

md("## Nilai tambah — Capacity\nEPR acak dari kecil sampai kapasitas maksimum RONI.")
code("""
MAX_EPR = max_epr_bytes(cover)
cap_rows = []
for frac in [0.1, 0.25, 0.5, 0.75, 1.0]:
    n = int(MAX_EPR * frac)
    txt = "X" * n
    p = protect(cover, txt, KEYS)
    v = verify_image(p["watermarked"], KEYS, KEYS.public_key)
    cap_rows.append({"epr_bytes": n, "roni_used_%": 100 * p["bits"].size / CAP_BITS,
                     "PSNR_dB": psnr(cover, p["watermarked"]), "SSIM": ssim(cover, p["watermarked"]),
                     "PSNR_ROI_dB": psnr_region(cover, p["watermarked"], ROI), "status": v["status"]})
try:
    protect(cover, "X" * (MAX_EPR + 1), KEYS); over = "muat (tidak terduga)"
except WatermarkError as e:
    over = f"ditolak: {e}"
df_cap = pd.DataFrame(cap_rows); df_cap.to_csv(OUT_DIR / "capacity.csv", index=False)
print("EPR melebihi kapasitas ->", over)
df_cap.round(4)
""")

md("## Simpan & download semua output (zip)")
code("""
shutil.make_archive("hasil_medsecure", "zip", OUT_DIR)
try:
    from google.colab import files
    files.download("hasil_medsecure.zip")
except ImportError:
    print("Tersimpan: hasil_medsecure.zip")
""")

# ---- write notebook
nb = {"nbformat": 4, "nbformat_minor": 5,
      "metadata": {"colab": {"provenance": []}, "kernelspec": {"name": "python3", "display_name": "Python 3"},
                   "language_info": {"name": "python"}}, "cells": []}
for i, (t, s) in enumerate(cells):
    c = {"cell_type": t, "metadata": {}, "source": s.splitlines(keepends=True), "id": f"c{i:02d}"}
    if t == "code":
        c["execution_count"] = None; c["outputs"] = []
    nb["cells"].append(c)
Path(sys.argv[1]).write_text(json.dumps(nb, indent=1, ensure_ascii=False))

# ---- flat script for local testing
flat = ["import matplotlib; matplotlib.use('Agg')", "from IPython.display import display" if False else
        "display = print"]
for t, s in cells:
    if t != "code":
        continue
    lines = [l for l in s.splitlines() if not l.startswith("!pip")]
    last = lines[-1] if lines else ""
    if last and re.match(r"^(df\w*|df\[.*\])(\.round\(\d\))?$", last.strip()):
        lines[-1] = f"print({last})"
    flat.append("\n".join(lines))
Path(sys.argv[2]).write_text("\n\n".join(flat) + "\n")
print(f"{len(cells)} cells written")
