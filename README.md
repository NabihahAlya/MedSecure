<<<<<<< HEAD
# MedSecure-XR

Pengamanan citra rontgen dada dengan **watermarking fragile di RONI** + **kriptografi**
(AES-256-GCM untuk EPR, HMAC-SHA256 per blok, tanda tangan Ed25519, AES-256-SIV untuk citra).

## Isi

| Berkas | Fungsi |
|---|---|
| `core.py` | Library inti (dipakai notebook dan Streamlit) |
| `app.py` | Demo Streamlit 5 menu |
| `MedSecure_XR_Colab.ipynb` | Eksperimen TA: 10 payload, keamanan, serangan, kapasitas |
| `sample_xray.jpg` | Citra contoh (dataset Kaggle Chest X-Ray Images (Pneumonia)) |
| `tools/build_notebook.py` | Membangun ulang notebook dari `core.py` |
| `tools/stub_test.py` | Uji otomatis alur `app.py` tanpa membuka browser |

## Menjalankan Streamlit (Windows / PowerShell)

```powershell
cd medsecure
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Browser terbuka di `http://localhost:8501`. Alur demo: **Pengirim → Lindungi & enkripsi → Penerima → Dekripsi & verifikasi → Simulasi Serangan**.

## Deploy gratis (Streamlit Community Cloud)

1. Push folder ini ke repo GitHub (publik atau privat).
2. share.streamlit.io → *New app* → pilih repo, file utama `app.py`.

## Colab

Upload `MedSecure_XR_Colab.ipynb` → Runtime → Run all → pilih citra saat diminta. Hasil (CSV, XLSX, grafik) terunduh sebagai `hasil_medsecure.zip`.

## Catatan keamanan

- Kunci di demo dibangkitkan per sesi. File `*keys*.json` berisi kunci privat — jangan di-commit.
- Watermark sengaja *fragile*: kompresi JPEG dianggap manipulasi. Simpan citra sebagai PNG.
=======
# MedSecure
>>>>>>> d3a488e4bb55a595df9f26efc111cef29c916430
