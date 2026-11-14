"""
MedSecure-XR core library.

Chest X-ray protection that combines exactly two security methods:
  1. Watermarking  : fragile LSB watermark embedded ONLY in the Region of
                     Non-Interest (RONI, the dark background), so the
                     diagnostic region (ROI) is never modified.
  2. Cryptography  : AES-256-GCM  -> confidentiality of the patient record (EPR)
                     HMAC-SHA256  -> per-block tags for tamper localization
                     Ed25519      -> doctor's digital signature (authenticity)
                     AES-256-SIV  -> whole-image encryption for transmission

Pipeline (sender):   cover -> RONI mask -> [EPR ct | block tags | signature]
                     -> LSB embed in RONI -> AES-SIV encrypt -> package
Pipeline (receiver): package -> AES-SIV decrypt (transit integrity)
                     -> extract watermark -> verify signature
                     -> compare block tags (tamper map) -> decrypt EPR
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import struct
import time
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, AESSIV
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
TARGET_H = 512          # output height; width follows the original aspect ratio
RONI_BLOCK = 16         # block size used to detect background (RONI)
TAMPER_BLOCK = 32       # block size of the tamper-localization grid
BG_THRESHOLD = 40       # a RONI block has all pixels (LSB ignored) below this value
RONI_MARGIN = 1         # safety margin (in RONI blocks) between ROI and RONI
TAG_BYTES = 2           # truncated HMAC tag per tamper block (16 bit)
MAGIC = b"MSX1"
PKG_MAGIC = b"MSXP"
SIG_LEN = 64
SIV_TAG_LEN = 16
GCM_NONCE_LEN = 12
LEN_BITS = 32


class WatermarkError(Exception):
    """Watermark missing, damaged, or does not fit."""


# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------
@dataclass
class KeyBundle:
    k_img: bytes                 # 64 B, AES-256-SIV (image transport)
    k_epr: bytes                 # 32 B, AES-256-GCM (patient record)
    k_wm: bytes                  # 32 B, HMAC key (block tags + embedding order)
    signing_key: Ed25519PrivateKey  # doctor's private key

    @classmethod
    def generate(cls) -> "KeyBundle":
        return cls(AESSIV.generate_key(512), AESGCM.generate_key(256), os.urandom(32),
                   Ed25519PrivateKey.generate())

    @property
    def public_key(self) -> Ed25519PublicKey:
        return self.signing_key.public_key()

    def public_bytes(self) -> bytes:
        return self.public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    def fingerprint(self) -> str:
        return hashlib.sha256(self.public_bytes()).hexdigest()[:16]

    def to_json(self) -> str:
        sk = self.signing_key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                            serialization.NoEncryption())
        d = {"k_img": self.k_img, "k_epr": self.k_epr, "k_wm": self.k_wm, "ed25519_sk": sk,
             "ed25519_pk": self.public_bytes()}
        return json.dumps({k: base64.b64encode(v).decode() for k, v in d.items()}, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "KeyBundle":
        d = {k: base64.b64decode(v) for k, v in json.loads(text).items()}
        return cls(d["k_img"], d["k_epr"], d["k_wm"], Ed25519PrivateKey.from_private_bytes(d["ed25519_sk"]))


def load_public_key(raw: bytes) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(raw)


# --------------------------------------------------------------------------
# Preprocessing and RONI detection
# --------------------------------------------------------------------------
def load_cover(src, target_h: int = TARGET_H, grid: int = TAMPER_BLOCK):
    """Grayscale, resize keeping the aspect ratio (width rounded to a multiple of `grid`)."""
    img = Image.open(src).convert("L")
    w, h = img.size
    new_w = max(grid, int(round(w * target_h / h / grid)) * grid)
    arr = np.array(img.resize((new_w, target_h), Image.LANCZOS), dtype=np.uint8)
    return arr, (w, h)


def roni_mask(img: np.ndarray, block: int = RONI_BLOCK, thr: int = BG_THRESHOLD,
              margin: int = RONI_MARGIN) -> np.ndarray:
    """Boolean mask of RONI pixels.

    A block is background when every pixel (LSB ignored) is below `thr` and the
    dark region is connected to the image border (true air/collimation, not the
    lungs). Ignoring the LSB makes the mask identical before and after embedding.
    """
    h, w = img.shape
    base = img & 0xFE
    bmax = base.reshape(h // block, block, w // block, block).max(axis=(1, 3))
    lab, _ = ndimage.label(bmax < thr)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    roni_b = np.isin(lab, border[border > 0])
    if margin:
        roni_b = ~ndimage.binary_dilation(~roni_b, iterations=margin)
    return np.kron(roni_b, np.ones((block, block), dtype=bool)).astype(bool)


def canonical(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Image with RONI LSBs cleared: identical before and after embedding."""
    c = img.copy()
    c[mask] &= 0xFE
    return c


def embedding_order(mask: np.ndarray, k_wm: bytes) -> np.ndarray:
    """Key-dependent pseudo-random order of RONI pixel indices."""
    idx = np.flatnonzero(mask.ravel())
    seed = int.from_bytes(hmac.new(k_wm, b"embed-order", hashlib.sha256).digest()[:8], "big")
    return idx[np.random.default_rng(seed).permutation(idx.size)]


# --------------------------------------------------------------------------
# Cryptographic building blocks
# --------------------------------------------------------------------------
def block_tags(canon: np.ndarray, k_wm: bytes, tb: int = TAMPER_BLOCK) -> bytes:
    h, w = canon.shape
    out = bytearray()
    for by in range(h // tb):
        for bx in range(w // tb):
            blk = canon[by * tb:(by + 1) * tb, bx * tb:(bx + 1) * tb]
            msg = struct.pack(">HHHH", by, bx, h, w) + blk.tobytes()
            out += hmac.new(k_wm, msg, hashlib.sha256).digest()[:TAG_BYTES]
    return bytes(out)


def signature_message(canon: np.ndarray, body_wo_sig: bytes) -> bytes:
    return b"MedSecure-XR/v1" + hashlib.sha256(canon.tobytes()).digest() + hashlib.sha256(body_wo_sig).digest()


def aes_encrypt(img: np.ndarray, key: bytes, mode: str = "siv", iv: bytes | None = None):
    pt = img.tobytes()
    if mode == "siv":
        out = AESSIV(key).encrypt(pt, None)
        meta, body = out[:SIV_TAG_LEN], out[SIV_TAG_LEN:]
    else:
        k = key[:32]
        iv = iv or os.urandom(16)
        m = modes.CTR(iv) if mode == "ctr" else modes.CBC(iv)
        enc = Cipher(algorithms.AES(k), m).encryptor()
        body = enc.update(pt) + enc.finalize()
        meta = iv
    return np.frombuffer(body, dtype=np.uint8).reshape(img.shape).copy(), meta


def aes_decrypt(cipher_img: np.ndarray, meta: bytes, key: bytes, mode: str = "siv") -> np.ndarray:
    body = cipher_img.tobytes()
    if mode == "siv":
        pt = AESSIV(key).decrypt(meta + body, None)  # raises InvalidTag
    else:
        m = modes.CTR(meta) if mode == "ctr" else modes.CBC(meta)
        dec = Cipher(algorithms.AES(key[:32]), m).decryptor()
        pt = dec.update(body) + dec.finalize()
    return np.frombuffer(pt, dtype=np.uint8).reshape(cipher_img.shape).copy()


# --------------------------------------------------------------------------
# Watermark payload
# --------------------------------------------------------------------------
def _header(h: int, w: int) -> bytes:
    return MAGIC + struct.pack(">BBBHH", 1, TAMPER_BLOCK, TAG_BYTES, h, w)


HEADER_LEN = len(MAGIC) + 7


def build_body(canon: np.ndarray, epr_text: str, keys: KeyBundle, times: dict | None = None) -> bytes:
    times = times if times is not None else {}
    h, w = canon.shape
    hdr = _header(h, w)

    s = time.perf_counter()
    nonce = os.urandom(GCM_NONCE_LEN)
    ct = AESGCM(keys.k_epr).encrypt(nonce, epr_text.encode("utf-8"), hdr)
    times["epr_encrypt"] = time.perf_counter() - s

    s = time.perf_counter()
    tags = block_tags(canon, keys.k_wm)
    times["block_tags"] = time.perf_counter() - s

    body = hdr + nonce + struct.pack(">H", len(ct)) + ct + tags
    s = time.perf_counter()
    sig = keys.signing_key.sign(signature_message(canon, body))
    times["sign"] = time.perf_counter() - s
    return body + sig


def body_to_bits(body: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(len(body).to_bytes(LEN_BITS // 8, "big") + body, dtype=np.uint8))


def parse_body(body: bytes) -> dict:
    if len(body) < HEADER_LEN + GCM_NONCE_LEN + 2 + SIG_LEN or body[:4] != MAGIC:
        raise WatermarkError("Watermark tidak ditemukan / rusak (magic tidak cocok)")
    ver, tb, tag_bytes, h, w = struct.unpack(">BBBHH", body[4:HEADER_LEN])
    p = HEADER_LEN
    nonce = body[p:p + GCM_NONCE_LEN]; p += GCM_NONCE_LEN
    (ct_len,) = struct.unpack(">H", body[p:p + 2]); p += 2
    ct = body[p:p + ct_len]; p += ct_len
    n_tags = (h // tb) * (w // tb)
    tags = body[p:p + n_tags * tag_bytes]; p += n_tags * tag_bytes
    sig = body[p:p + SIG_LEN]
    if len(sig) != SIG_LEN or len(tags) != n_tags * tag_bytes:
        raise WatermarkError("Struktur watermark tidak lengkap")
    return {"version": ver, "tb": tb, "tag_bytes": tag_bytes, "h": h, "w": w, "header": body[:HEADER_LEN],
            "nonce": nonce, "ct": ct, "tags": tags, "sig": sig, "body_wo_sig": body[:-SIG_LEN]}


def capacity_bits(mask: np.ndarray) -> int:
    return int(mask.sum())


def overhead_bytes(shape) -> int:
    h, w = shape
    n_tags = (h // TAMPER_BLOCK) * (w // TAMPER_BLOCK)
    return LEN_BITS // 8 + HEADER_LEN + GCM_NONCE_LEN + 2 + 16 + n_tags * TAG_BYTES + SIG_LEN


def max_epr_bytes(cover: np.ndarray) -> int:
    return capacity_bits(roni_mask(cover)) // 8 - overhead_bytes(cover.shape)


# --------------------------------------------------------------------------
# Sender: protect
# --------------------------------------------------------------------------
def protect(cover: np.ndarray, epr_text: str, keys: KeyBundle, mode: str = "siv") -> dict:
    """Embed signed+encrypted EPR in RONI, then encrypt the whole image."""
    t = {}
    s = time.perf_counter()
    mask = roni_mask(cover)
    canon = canonical(cover, mask)
    order = embedding_order(mask, keys.k_wm)
    t["roni_mask"] = time.perf_counter() - s

    body = build_body(canon, epr_text, keys, t)
    bits = body_to_bits(body)
    if bits.size > order.size:
        raise WatermarkError(f"Kapasitas RONI tidak cukup: butuh {bits.size} bit, tersedia {order.size} bit")

    s = time.perf_counter()
    flat = cover.ravel().copy()
    pos = order[:bits.size]
    flat[pos] = (flat[pos] & 0xFE) | bits
    wm = flat.reshape(cover.shape)
    t["embed"] = time.perf_counter() - s

    s = time.perf_counter()
    enc, meta = aes_encrypt(wm, keys.k_img, mode)
    t["img_encrypt"] = time.perf_counter() - s
    return {"watermarked": wm, "encrypted": enc, "meta": meta, "mode": mode, "mask": mask,
            "bits": bits, "body_len": len(body), "capacity_bits": int(order.size), "times": t}


# --------------------------------------------------------------------------
# Receiver: extract and verify
# --------------------------------------------------------------------------
def extract_body(img: np.ndarray, k_wm: bytes):
    mask = roni_mask(img)
    order = embedding_order(mask, k_wm)
    if order.size < LEN_BITS:
        raise WatermarkError("RONI tidak ditemukan pada citra")
    lsb = (img.ravel()[order] & 1).astype(np.uint8)
    n = int.from_bytes(np.packbits(lsb[:LEN_BITS]).tobytes(), "big")
    if n <= 0 or LEN_BITS + 8 * n > order.size:
        raise WatermarkError("Panjang watermark tidak valid (watermark rusak)")
    bits = lsb[:LEN_BITS + 8 * n]
    return np.packbits(bits[LEN_BITS:]).tobytes(), bits, mask


def verify_image(img: np.ndarray, keys: KeyBundle, public_key: Ed25519PublicKey) -> dict:
    """Verify a plaintext (decrypted) image: watermark, signature, tamper map, EPR."""
    t = {}
    r = {"watermark_found": False, "signature_ok": False, "epr_ok": False, "epr": None,
         "tamper_map": None, "n_tampered": None, "bits": None, "times": t}
    s = time.perf_counter()
    try:
        body, bits, mask = extract_body(img, keys.k_wm)
        p = parse_body(body)
    except WatermarkError as e:
        t["extract"] = time.perf_counter() - s
        r["message"] = str(e)
        r["status"] = "DIMANIPULASI"
        return r
    t["extract"] = time.perf_counter() - s
    r["watermark_found"] = True
    r["bits"] = bits

    canon = canonical(img, mask)
    s = time.perf_counter()
    try:
        public_key.verify(p["sig"], signature_message(canon, p["body_wo_sig"]))
        r["signature_ok"] = True
    except InvalidSignature:
        pass
    t["verify_sig"] = time.perf_counter() - s

    s = time.perf_counter()
    if p["tb"] == TAMPER_BLOCK and (p["h"], p["w"]) == img.shape:
        fresh = block_tags(canon, keys.k_wm)
        gh, gw = p["h"] // p["tb"], p["w"] // p["tb"]
        a = np.frombuffer(fresh, dtype=">u2").reshape(gh, gw)
        b = np.frombuffer(p["tags"], dtype=">u2").reshape(gh, gw)
        r["tamper_map"] = a != b
        r["n_tampered"] = int(r["tamper_map"].sum())
    t["tamper_check"] = time.perf_counter() - s

    s = time.perf_counter()
    try:
        r["epr"] = AESGCM(keys.k_epr).decrypt(p["nonce"], p["ct"], p["header"]).decode("utf-8")
        r["epr_ok"] = True
    except InvalidTag:
        pass
    t["epr_decrypt"] = time.perf_counter() - s

    if r["signature_ok"] and r["epr_ok"] and r["n_tampered"] == 0:
        r["status"], r["message"] = "AMAN", "Citra asli, tanda tangan dokter valid, EPR utuh"
    elif r["n_tampered"]:
        r["status"] = "DIMANIPULASI"
        r["message"] = f"{r['n_tampered']} blok {TAMPER_BLOCK}x{TAMPER_BLOCK} piksel terdeteksi diubah"
    else:
        r["status"] = "DIMANIPULASI"
        r["message"] = "Tanda tangan / data watermark tidak valid"
    return r


def receive(cipher_img: np.ndarray, meta: bytes, keys: KeyBundle, public_key: Ed25519PublicKey,
            mode: str = "siv") -> dict:
    s = time.perf_counter()
    try:
        dec = aes_decrypt(cipher_img, meta, keys.k_img, mode)
    except InvalidTag:
        return {"status": "DITOLAK", "transit_ok": False, "image": None,
                "message": "Dekripsi AES-SIV gagal: kunci salah atau ciphertext diubah saat transmisi",
                "times": {"img_decrypt": time.perf_counter() - s}}
    t_dec = time.perf_counter() - s
    r = verify_image(dec, keys, public_key)
    r["times"] = {"img_decrypt": t_dec, **r["times"]}
    r["transit_ok"] = True
    r["image"] = dec
    return r


# --------------------------------------------------------------------------
# Transport package (single file)
# --------------------------------------------------------------------------
_MODES = {"siv": 0, "ctr": 1, "cbc": 2}


def pack_package(enc: np.ndarray, meta: bytes, mode: str = "siv") -> bytes:
    h, w = enc.shape
    return PKG_MAGIC + struct.pack(">BBHHB", 1, _MODES[mode], h, w, len(meta)) + meta + enc.tobytes()


def unpack_package(data: bytes):
    if data[:4] != PKG_MAGIC:
        raise ValueError("Bukan file paket MedSecure-XR")
    ver, m, h, w, ml = struct.unpack(">BBHHB", data[4:11])
    meta = data[11:11 + ml]
    body = data[11 + ml:]
    if len(body) != h * w:
        raise ValueError("Ukuran paket tidak sesuai")
    mode = {v: k for k, v in _MODES.items()}[m]
    return np.frombuffer(body, dtype=np.uint8).reshape(h, w).copy(), meta, mode


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------
def mse(a, b):
    return float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))


def psnr(a, b):
    return float("inf") if mse(a, b) == 0 else float(peak_signal_noise_ratio(a, b, data_range=255))


def psnr_region(a, b, mask):
    d = (a.astype(np.float64) - b.astype(np.float64))[mask]
    m = float(np.mean(d ** 2)) if d.size else 0.0
    return float("inf") if m == 0 else float(10 * np.log10(255 ** 2 / m))


def ssim(a, b):
    return float(structural_similarity(a, b, data_range=255))


def entropy(img):
    h = np.bincount(img.ravel(), minlength=256).astype(np.float64)
    p = h[h > 0] / h.sum()
    return float(-np.sum(p * np.log2(p)))


def adjacent_correlation(img):
    x = img.astype(np.float64)
    pairs = {"H": (x[:, :-1], x[:, 1:]), "V": (x[:-1, :], x[1:, :]), "D": (x[:-1, :-1], x[1:, 1:])}
    return {k: float(np.corrcoef(a.ravel(), b.ravel())[0, 1]) for k, (a, b) in pairs.items()}


def npcr_uaci(c1, c2):
    a, b = c1.astype(np.int16), c2.astype(np.int16)
    return float(100 * np.mean(a != b)), float(100 * np.mean(np.abs(a - b) / 255))


def differential_test(img, key: bytes, mode: str = "siv"):
    """Change one pixel (+1 mod 256); encrypt both with the SAME key and SAME IV."""
    img2 = img.copy()
    r, c = img.shape[0] // 2, img.shape[1] // 2
    img2[r, c] = (int(img2[r, c]) + 1) % 256
    iv = os.urandom(16)
    c1, _ = aes_encrypt(img, key, mode, iv)
    c2, _ = aes_encrypt(img2, key, mode, iv)
    return npcr_uaci(c1, c2)


def ber(a, b):
    n, m = max(a.size, b.size), min(a.size, b.size)
    return (int(np.sum(a[:m] != b[:m])) + (n - m)) / n if n else 0.0


def nc(a, b):
    a, b = a.astype(np.float64), b.astype(np.float64)
    m = min(a.size, b.size)
    a, b = a[:m], b[:m]
    den = np.sqrt(np.sum(a * a) * np.sum(b * b))
    return float(np.sum(a * b) / den) if den else 0.0


def sha256_img(img) -> str:
    return hashlib.sha256(img.tobytes()).hexdigest()


# --------------------------------------------------------------------------
# Attack simulation
# --------------------------------------------------------------------------
ATTACKS = {
    "hapus_lesi": "Hapus lesi (isi area dengan rata-rata sekitar)",
    "copy_move": "Copy-move (tempel area paru lain)",
    "terangkan": "Terangkan area (+40)",
    "blur": "Blur lokal",
    "teks": "Tambah anotasi teks",
    "noise": "Noise Gaussian global (sigma 2)",
    "jpeg": "Kompresi JPEG global (Q=90)",
}


def default_box(shape, frac=0.12):
    h, w = shape
    bh, bw = int(h * frac), int(w * frac)
    return (int(w * 0.30), int(h * 0.45), bw, bh)  # x, y, w, h (left lung area)


def attack(img: np.ndarray, kind: str, box=None, seed: int = 0) -> np.ndarray:
    a = img.copy()
    x, y, bw, bh = box or default_box(img.shape)
    sl = (slice(y, y + bh), slice(x, x + bw))
    if kind == "hapus_lesi":
        ring = img[max(0, y - 8):y + bh + 8, max(0, x - 8):x + bw + 8]
        a[sl] = np.uint8(round(float(ring.mean())))
    elif kind == "copy_move":
        sx = min(img.shape[1] - bw, x + int(img.shape[1] * 0.35))
        a[sl] = img[y:y + bh, sx:sx + bw]
    elif kind == "terangkan":
        a[sl] = np.clip(a[sl].astype(int) + 40, 0, 255).astype(np.uint8)
    elif kind == "blur":
        pil = Image.fromarray(a)
        region = pil.crop((x, y, x + bw, y + bh)).filter(ImageFilter.GaussianBlur(4))
        pil.paste(region, (x, y))
        a = np.array(pil)
    elif kind == "teks":
        pil = Image.fromarray(a)
        ImageDraw.Draw(pil).text((x, y), "NORMAL", fill=255)
        a = np.array(pil)
    elif kind == "noise":
        rng = np.random.default_rng(seed)
        a = np.clip(a.astype(float) + rng.normal(0, 2, a.shape), 0, 255).astype(np.uint8)
    elif kind == "jpeg":
        buf = io.BytesIO()
        Image.fromarray(a).save(buf, "JPEG", quality=90)
        a = np.array(Image.open(io.BytesIO(buf.getvalue())).convert("L"))
    else:
        raise ValueError(kind)
    return a


def block_ground_truth(orig: np.ndarray, attacked: np.ndarray, tb: int = TAMPER_BLOCK) -> np.ndarray:
    h, w = orig.shape
    d = orig != attacked
    return d.reshape(h // tb, tb, w // tb, tb).any(axis=(1, 3))


def localization_scores(pred: np.ndarray, gt: np.ndarray) -> dict:
    tp = int(np.sum(pred & gt)); fp = int(np.sum(pred & ~gt))
    fn = int(np.sum(~pred & gt)); tn = int(np.sum(~pred & ~gt))
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "TPR": tp / (tp + fn) if tp + fn else float("nan"),
            "FPR": fp / (fp + tn) if fp + tn else 0.0}


# --------------------------------------------------------------------------
# Visual helpers
# --------------------------------------------------------------------------
def overlay_mask(img: np.ndarray, mask: np.ndarray, color=(0, 170, 255), alpha=0.45) -> np.ndarray:
    rgb = np.stack([img] * 3, axis=-1).astype(np.float64)
    c = np.array(color, dtype=np.float64)
    rgb[mask] = (1 - alpha) * rgb[mask] + alpha * c
    return rgb.clip(0, 255).astype(np.uint8)


def tamper_overlay(img: np.ndarray, tamper_map: np.ndarray, tb: int = TAMPER_BLOCK) -> np.ndarray:
    full = np.kron(tamper_map, np.ones((tb, tb), dtype=bool)).astype(bool)
    return overlay_mask(img, full, color=(255, 40, 40), alpha=0.5)


def to_png_bytes(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")
    return buf.getvalue()
