#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
from pathlib import Path

# ถ้าไม่ได้ใช้ virtualenv แนะนำให้อัปเดต pip/setuptools ก่อน:
# python -m pip install -U pip setuptools wheel
# pip install -U ultralytics

def main():
    parser = argparse.ArgumentParser(description="Train YOLOv12 for object detection (save only best).")
    parser.add_argument("--data", type=str, required=True,
                        help="Path to data.yaml (YOLO format).")
    parser.add_argument("--model", type=str, default="yolov12s.pt",
                        help="yolov12n/s/m/l/x .pt or path to your checkpoint.")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8,  # ใส่ "auto" ได้ถ้าอยากให้ลองหาอัตโนมัติ
                        help='Batch size (int) or "auto"')
    parser.add_argument("--device", type=str, default="0", help='GPU index or "cpu"')
    parser.add_argument("--project", type=str, default="./runs", help="Output root dir")
    parser.add_argument("--name", type=str, default="pill_yolov12", help="Run name")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--patience", type=int, default=30,
                        help="Early stopping patience (epochs without val improvement).")
    parser.add_argument("--resume", action="store_true",
                        help="Resume training from last checkpoint in the same run.")
    parser.add_argument("--cache", action="store_true",
                        help="Cache images in RAM/disk for faster training.")
    parser.add_argument("--workers", type=int, default=4, help="Dataloader workers.")
    args = parser.parse_args()

    # ป้องกัน tmp เต็มบนพาธ system: ชี้ TMPDIR ไปพาร์ทิชันใหญ่ได้ (ถ้าต้องการ)
    # os.environ.setdefault("TMPDIR", "/media/banky/New Volume/Phamatics/tmp")

    # ลด log noise ของ Torch (ตามชอบ)
    os.environ.setdefault("TORCH_SHOW_CPP_STACKTRACES", "1")

    from ultralytics import YOLO

    # โหลดโมเดล (รองรับทั้ง pretrained family และ checkpoint)
    model = YOLO(args.model)

    # ถ้าอยากให้ deterministic มากขึ้น
    # tip: การตั้งค่า deterministic จะช้าลงเล็กน้อย แต่ reproducible
    # from ultralytics.utils import torch_utils
    # torch_utils.set_seed(args.seed, deterministic=True)

    # การตั้งค่า train
    train_kwargs = dict(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        device=args.device,     # "0" หรือ "cpu"
        workers=args.workers,
        batch=args.batch,       # "auto" หรือ int
        project=args.project,
        name=args.name,
        seed=args.seed,
        patience=args.patience, # early stopping
        save_period=-1,         # << ไม่เซฟทุก epoch → จะเหลือเฉพาะ best.pt และ last.pt
        exist_ok=True,          # เขียนทับ run เดิม (ถ้าชื่อซ้ำ)
        verbose=True
    )

    if args.cache:
        train_kwargs["cache"] = True

    # เริ่มเทรน
    if args.resume:
        # resume=True จะอ่าน optimizer/scheduler state ด้วย (ต้องมี runs เดิม)
        results = model.train(resume=True, **train_kwargs)
    else:
        results = model.train(**train_kwargs)

    # หลังเทรน: สรุป path สำคัญ
    # โดยปกติ Ultralytics จะสร้าง:
    #   {project}/{task}/{name}/weights/best.pt
    #   {project}/{task}/{name}/weights/last.pt
    run_dir = Path(results.save_dir) if hasattr(results, "save_dir") else None
    if run_dir:
        weights = run_dir / "weights"
        print("\n=== Training finished ===")
        print(f"Run dir   : {run_dir}")
        print(f"Best model: {weights / 'best.pt'}")
        print(f"Last model: {weights / 'last.pt'}")
    else:
        print("\n=== Training finished ===")
        print("Check runs/ directory for outputs.")

if __name__ == "__main__":
    main()