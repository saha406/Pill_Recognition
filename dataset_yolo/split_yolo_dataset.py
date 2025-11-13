#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import random
import json
from pathlib import Path

# ========= CONFIG =========
DATA_ROOT   = Path("/media/banky/New Volume/Phamatics/dataset_yolo/dataset_medicines")

IMAGES_DIR  = DATA_ROOT / "images"   # ชั้นเดียว มีแต่รูป
LABELS_DIR  = DATA_ROOT / "labels"   # ชั้นเดียว มีแต่ .txt
CLASSES_TXT = DATA_ROOT / "classes.txt"
NOTES_JSON  = DATA_ROOT / "notes.json"   # (optional) {"categories":[{"id":0,"name":"..."},...]}

# อัตราส่วน (รวม ~1.0)
SPLIT = {"train": 0.8, "val": 0.1, "test": 0.1}

RANDOM_SEED = 42
FILE_MODE   = "copy"  # copy | symlink | hardlink
IMG_EXTS    = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}  # จะใช้ .lower() ตรวจ
DATA_YAML   = DATA_ROOT / "data.yaml"
# =========================

def list_images_flat(d: Path):
    return sorted([p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXTS])

def list_labels_flat(d: Path):
    return sorted([p for p in d.iterdir() if p.is_file() and p.suffix.lower() == ".txt"])

def load_class_names():
    # จาก classes.txt (บรรทัดละ 1 ชื่อ)
    if CLASSES_TXT.exists():
        names = [l.strip() for l in CLASSES_TXT.read_text(encoding="utf-8").splitlines() if l.strip()]
        if names:
            return names
    # จาก notes.json (categories[id,name])
    if NOTES_JSON.exists():
        try:
            data = json.loads(NOTES_JSON.read_text(encoding="utf-8"))
            cats = sorted(data.get("categories", []), key=lambda c: c.get("id", 0))
            names = [c.get("name", f"class_{i}") for i, c in enumerate(cats)]
            if names:
                return names
        except Exception:
            pass
    return []

def safe_put(src: Path, dst: Path, mode: str):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    if mode == "symlink":
        try:
            dst.symlink_to(src); return
        except Exception:
            pass
    if mode == "hardlink":
        try:
            os.link(src, dst); return
        except Exception:
            pass
    shutil.copy2(src, dst)

def write_yaml(names, has_test):
    lines = []
    lines.append(f'path: "{str(DATA_ROOT)}"')
    lines.append('train: "images/train"')
    lines.append('val: "images/val"')
    if has_test:
        lines.append('test: "images/test"')
    lines.append(f"nc: {len(names)}")
    lines.append("names:")
    for i, n in enumerate(names):
        n = n.replace('"', '\\"')
        lines.append(f'  {i}: "{n}"')
    DATA_YAML.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Wrote data.yaml -> {DATA_YAML}")

def main():
    random.seed(RANDOM_SEED)

    # 1) รวบรวมไฟล์ (ชั้นเดียว)
    imgs = list_images_flat(IMAGES_DIR)
    lbls = list_labels_flat(LABELS_DIR)

    # 2) จับคู่ด้วย stem (case-insensitive)
    img_map = {}
    for p in imgs:
        img_map.setdefault(p.stem.lower(), p)
    lbl_map = {}
    for p in lbls:
        lbl_map.setdefault(p.stem.lower(), p)

    img_stems = set(img_map.keys())
    lbl_stems = set(lbl_map.keys())

    matched_stems = sorted(img_stems & lbl_stems)
    only_images   = sorted(img_stems - lbl_stems)
    only_labels   = sorted(lbl_stems - img_stems)

    print(f"[INFO] images: {len(imgs)}, labels: {len(lbls)}")
    print(f"[INFO] matched pairs: {len(matched_stems)}")
    print(f"[INFO] only-images (no txt): {len(only_images)}")
    print(f"[INFO] only-labels (no img): {len(only_labels)}")

    # 3) สร้างคู่ (img, lbl)
    pairs = [(img_map[s], lbl_map[s]) for s in matched_stems]
    random.shuffle(pairs)

    # 4) split
    n = len(pairs)
    n_train = int(n * SPLIT.get("train", 0))
    n_val   = int(n * SPLIT.get("val", 0))
    n_test  = n - n_train - n_val if SPLIT.get("test", 0) > 0 else 0

    train_set = pairs[:n_train]
    val_set   = pairs[n_train:n_train+n_val]
    test_set  = pairs[n_train+n_val:] if n_test > 0 else []

    print(f"[SPLIT] train={len(train_set)}, val={len(val_set)}, test={len(test_set)}")

    # 5) สร้างโครงปลายทาง
    for split in ["train", "val"] + (["test"] if n_test > 0 else []):
        (DATA_ROOT / "images" / split).mkdir(parents=True, exist_ok=True)
        (DATA_ROOT / "labels" / split).mkdir(parents=True, exist_ok=True)

    # 6) คัดลอก/ลิงก์
    def place(split_name, items):
        img_out = DATA_ROOT / "images" / split_name
        lbl_out = DATA_ROOT / "labels" / split_name
        for img, lbl in items:
            safe_put(img, img_out / img.name, FILE_MODE)
            safe_put(lbl, lbl_out / lbl.name, FILE_MODE)

    place("train", train_set)
    place("val",   val_set)
    if test_set:
        place("test", test_set)

    # 7) เขียน data.yaml
    names = load_class_names()
    if names:
        write_yaml(names, has_test=(len(test_set) > 0))
    else:
        DATA_YAML.write_text(
            f'path: "{str(DATA_ROOT)}"\ntrain: "images/train"\nval: "images/val"\n'
            + ('test: "images/test"\n' if len(test_set) > 0 else '')
            + "nc: 0\nnames: []\n",
            encoding="utf-8"
        )
        print(f"[OK] Wrote data.yaml (empty names) -> {DATA_YAML}")

    print("[DONE] Split complete.")

if __name__ == "__main__":
    main()
