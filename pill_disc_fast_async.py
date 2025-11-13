#!/usr/bin/env python3
import asyncio, os, time, sys
from urllib.parse import urljoin, urlparse
from pathlib import Path

import aiohttp
from aiohttp import ClientSession, TCPConnector, ClientTimeout
from bs4 import BeautifulSoup

# ========= ปรับค่าได้ =========
BASE = "https://data.lhncbc.nlm.nih.gov/public/Pills/"
ALLXML_URL = urljoin(BASE, "ALLXML/")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/127.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Referer": BASE,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TIMEOUT = ClientTimeout(total=0, connect=30, sock_connect=30, sock_read=120)  # no global total timeout
CHUNK = 1024 * 256                       # 256KB/ชิ้น (ใหญ่ขึ้น = เร็วขึ้น)
CONC_IMAGE = 16                          # ดาว์นโหลดรูปพร้อมกันกี่ไฟล์ (แนะนำ 12–24)
RETRY = 3                                # ครั้งที่ retry ต่อไฟล์
PER_JOB_DELAY = 0.0                      # delay เล็กน้อยต่อไฟล์ (สุภาพกับ server)
IMAGE_EXTS = (".jpg",".jpeg",".png",".gif",".bmp",".tif",".tiff",".webp")
# เลือกโหลดชุดเดียวหรือช่วง
DISC = None                              # เช่น 7  (ตั้งค่านี้ หรือใช้ START/END ข้างล่าง)
START, END = 1, 110                      # ใช้ช่วงนี้ถ้า DISC=None
OUT_ROOT = Path("Pills_downloads")       # เก็บผลลัพธ์
# ==============================

def parse_args_from_cli():
    import argparse
    p = argparse.ArgumentParser(description="Async downloader for PillProjectDisc")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--disc", type=int, help="single disc number (e.g., 7)")
    g.add_argument("--range", nargs=2, type=int, metavar=("START","END"), help="disc range inclusive")
    p.add_argument("--out", default=str(OUT_ROOT), help="output root directory")
    p.add_argument("--concurrency", type=int, default=CONC_IMAGE, help="parallel image downloads")
    p.add_argument("--retry", type=int, default=RETRY, help="retries per file")
    p.add_argument("--chunk", type=int, default=CHUNK, help="chunk size in bytes")
    args = p.parse_args()
    return args

async def fetch_text(session: ClientSession, url: str) -> str | None:
    for i in range(RETRY):
        try:
            async with session.get(url) as r:
                if r.status != 200:
                    # list ผ่าน index.html เท่านั้น
                    await asyncio.sleep(0.4*(i+1))
                    continue
                return await r.text()
        except Exception:
            await asyncio.sleep(0.4*(i+1))
    return None

async def list_links(session: ClientSession, url: str) -> list[str]:
    # ทั้ง dir/ และ dir/index.html
    for candidate in (url, urljoin(url, "index.html")):
        html = await fetch_text(session, candidate)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("#") or href.startswith("?"):
                continue
            links.append(urljoin(url, href))
        if links:
            return links
    return []

async def download(session: ClientSession, url: str, out_path: Path, sem: asyncio.Semaphore) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    async with sem:
        for i in range(RETRY):
            try:
                async with session.get(url) as r:
                    if r.status != 200:
                        await asyncio.sleep(0.5*(i+1))
                        continue
                    # stream to file
                    with open(out_path, "wb") as f:
                        async for chunk in r.content.iter_chunked(CHUNK):
                            if chunk:
                                f.write(chunk)
                if PER_JOB_DELAY:
                    await asyncio.sleep(PER_JOB_DELAY)
                return True
            except Exception:
                await asyncio.sleep(0.5*(i+1))
    print(f"  [ERR ] {out_path.name} <- {url}")
    return False

async def download_xml(session: ClientSession, disc_no: int, out_dir: Path):
    xml_name = f"MedicosConsultantsExport_{disc_no}.xml"
    xml_from_disc = urljoin(urljoin(BASE, f"PillProjectDisc{disc_no}/"), xml_name)
    xml_from_all  = urljoin(ALLXML_URL, xml_name)
    out_path = out_dir / xml_name
    if out_path.exists():
        print(f"[SKIP] {xml_name}")
        return
    sem = asyncio.Semaphore(1)
    print(f"[XML ] {xml_name}")
    ok = await download(session, xml_from_disc, out_path, sem)
    if not ok:
        print("  [warn] จากโฟลเดอร์โครงการไม่ได้ → ลอง ALLXML/")
        ok2 = await download(session, xml_from_all, out_path, sem)
        if not ok2:
            print("  [ERR ] โหลด XML ไม่สำเร็จจากทั้งสองจุด")

async def download_images(session: ClientSession, disc_no: int, out_dir: Path):
    images_url = urljoin(urljoin(BASE, f"PillProjectDisc{disc_no}/"), "images/")
    links = await list_links(session, images_url)
    if not links:
        print("  [WARN] ลิสต์ images/ ไม่ได้ (ถูกบล็อกหรือไม่มี index)")
        return
    file_urls = [u for u in links
                 if not u.endswith("/")
                 and urlparse(u).path.lower().endswith(IMAGE_EXTS)]
    print(f"  [IMGS] พบ {len(file_urls)} ไฟล์ — concurrent={CONC_IMAGE}")
    sem = asyncio.Semaphore(CONC_IMAGE)
    tasks = []
    img_dir = out_dir / "images"
    for u in file_urls:
        name = os.path.basename(urlparse(u).path)
        dest = img_dir / name
        if dest.exists():
            continue
        tasks.append(download(session, u, dest, sem))
    done = 0
    for coro in asyncio.as_completed(tasks):
        await coro
        done += 1
        if done and done % 30 == 0:
            print(f"    [PROG] {done}/{len(tasks)}")

async def crawl_disc(session: ClientSession, disc_no: int, out_root: Path):
    out_dir = out_root / f"PillProjectDisc{disc_no}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n[DISC] {disc_no}")
    await download_xml(session, disc_no, out_dir)
    await download_images(session, disc_no, out_dir)

async def main_async(discs: list[int], out_root: Path, concurrency: int, chunk: int, retry: int):
    global CONC_IMAGE, CHUNK, RETRY
    CONC_IMAGE, CHUNK, RETRY = concurrency, chunk, retry

    connector = TCPConnector(limit=concurrency*2, ttl_dns_cache=300)
    async with aiohttp.ClientSession(headers=HEADERS, timeout=TIMEOUT, connector=connector) as session:
        t0 = time.time()
        for n in discs:
            await crawl_disc(session, n, out_root)
        dt = time.time() - t0
        print(f"\n เสร็จสิ้นทั้งหมด — ใช้เวลา {dt:.1f}s  | output: {out_root.resolve()}")

def resolve_discs():
    # จากค่าคงที่ด้านบน หรือจาก CLI
    if len(sys.argv) > 1:
        args = parse_args_from_cli()
        out = Path(args.out)
        if args.disc is not None:
            return [args.disc], out, args.concurrency, args.chunk, args.retry
        elif args.range:
            s, e = args.range
            return list(range(s, e+1)), out, args.concurrency, args.chunk, args.retry
        else:
            return ( [DISC] if DISC else list(range(START, END+1)),
                     out, args.concurrency, args.chunk, args.retry )
    else:
        # ใช้ค่าดีฟอลต์ในไฟล์
        discs = [DISC] if DISC else list(range(START, END+1))
        return discs, OUT_ROOT, CONC_IMAGE, CHUNK, RETRY

if __name__ == "__main__":
    discs, out_root, conc, chunk, retry = resolve_discs()
    asyncio.run(main_async(discs, out_root, conc, chunk, retry))
