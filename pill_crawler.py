#!/usr/bin/env python3
import os, time
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE = "https://data.lhncbc.nlm.nih.gov/public/Pills/"
DISC_NO = 1
DISC_URL = urljoin(BASE, f"PillProjectDisc{DISC_NO}/")
ALLXML_URL = urljoin(BASE, "ALLXML/")
XML_NAME = f"MedicosConsultantsExport_{DISC_NO}.xml"

OUT_DIR = f"Pills_downloads/PillProjectDisc{DISC_NO}"
os.makedirs(OUT_DIR, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/127.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Referer": BASE,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TIMEOUT = 60
SLEEP = 0.25
RETRY = 3
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp")

def download(url: str, out_path: str, sess: requests.Session) -> bool:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    for i in range(RETRY):
        try:
            with sess.get(url, headers=HEADERS, stream=True, timeout=TIMEOUT) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"status={r.status_code}")
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(1024*64):
                        if chunk: f.write(chunk)
            return True
        except Exception as e:
            print(f"  [retry {i+1}/{RETRY}] {os.path.basename(out_path)} -> {e}")
            time.sleep(0.8 * (i + 1))
    return False

def list_links(url: str, sess: requests.Session):
    """พยายามลิสต์ไฟล์ในไดเรกทอรี (ลองทั้งตัวโฟลเดอร์และ index.html)"""
    tried = [url, urljoin(url, "index.html")]
    files = []
    for u in tried:
        try:
            r = sess.get(u, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code != 200 or not r.text:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("#") or href.startswith("?"): 
                    continue
                full = urljoin(url, href)
                files.append(full)
            if files:
                break
        except requests.RequestException:
            continue
    return files

def main():
    sess = requests.Session()

    # 1) ดาวน์โหลด XML (ลองที่โฟลเดอร์โครงการก่อน แล้วค่อย fallback ALLXML)
    xml_from_disc = urljoin(DISC_URL, XML_NAME)
    xml_from_allxml = urljoin(ALLXML_URL, XML_NAME)
    xml_out = os.path.join(OUT_DIR, XML_NAME)

    if not os.path.exists(xml_out):
        print(f"[XML] {XML_NAME}")
        if not download(xml_from_disc, xml_out, sess):
            print("  [warn] จากโฟลเดอร์โครงการไม่ได้ → ลอง ALLXML/")
            if not download(xml_from_allxml, xml_out, sess):
                print("  [ERR ] โหลด XML ไม่สำเร็จจากทั้งสองจุด")
        else:
            print("  [OK] ได้จากโฟลเดอร์โครงการ")
    else:
        print(f"[SKIP] {XML_NAME} มีแล้ว")

    # 2) ดาวน์โหลดภาพใน images/
    images_url = urljoin(DISC_URL, "images/")
    print(f"[IMAGES] {images_url}")
    links = list_links(images_url, sess)
    if not links:
        print("  [WARN] ลิสต์ images/ ไม่ได้ (ถูกบล็อกหรือไม่มี index)")
        return

    # กรองเฉพาะไฟล์ภาพ
    file_urls = [u for u in links if not u.endswith("/") and urlparse(u).path.lower().endswith(IMAGE_EXTS)]
    print(f"  -> พบไฟล์ภาพ {len(file_urls)} ไฟล์")
    os.makedirs(os.path.join(OUT_DIR, "images"), exist_ok=True)

    for u in file_urls:
        name = os.path.basename(urlparse(u).path)
        out_path = os.path.join(OUT_DIR, "images", name)
        if os.path.exists(out_path):
            print(f"  [SKIP] {name}")
            continue
        print(f"  [GET ] {name}")
        ok = download(u, out_path, sess)
        if not ok:
            print(f"  [ERR ] {name}")
        time.sleep(SLEEP)

    print("\n✅ เสร็จสิ้น — ดูไฟล์ที่:", os.path.abspath(OUT_DIR))

if __name__ == "__main__":
    main()