# -*- coding: utf-8 -*-
"""
重建正文字体子集（新增/修改诗词后运行一次）

用法：  python tools/build-font.py
依赖：  pip install fonttools brotli

流程：
  1. 从 poems_data.js 提取所有用到的汉字与标点
  2. 下载「文鼎 PL 简中楷」deb 包（清华镜像），取出 ukai.ttc 里的简体字面
  3. 子集化 → 按 ARPHIC Public License 要求改名 GushiKaiBook → fonts/gushi-kai.woff2
  4. 同时导出 fonts/ARPHICPL.txt 授权文本

拼音字体 fonts/gushi-pinyin.woff2 只在拼音字符集变化时才需要重建，
字符集固定（a-z + 声调元音），一般不用动。
"""
import gzip
import io
import json
import lzma
import pathlib
import struct
import subprocess
import sys
import tarfile
import urllib.request

from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = ROOT / "fonts"
CACHE = ROOT / "tools" / ".cache"
DEB_URL = ("https://mirrors.tuna.tsinghua.edu.cn/debian/pool/main/f/fonts-arphic-ukai/"
           "fonts-arphic-ukai_0.2.20080216.2-6_all.deb")

FAMILY, STYLE = "GushiKaiBook", "Regular"
LICENSE_TXT = (
    'Arphic Public License. This derived font has been modified (glyph subset) and renamed. '
    'The original copyright notice is retained. See fonts/ARPHICPL.txt.'
)


def poem_chars():
    src = (ROOT / "poems_data.js").read_text(encoding="utf-8")
    poems = json.loads(src[src.index("["): src.rindex("]") + 1])
    chars = set()
    for p in poems:
        chars |= set(p["text"]) | set(p["title"]) | set(p["author"]) | set(p["dynasty"])
    chars |= set("，。？！；：、“”《》·（）—…　 ")
    return "".join(sorted(c for c in chars if c.strip()))


def fetch_deb():
    CACHE.mkdir(parents=True, exist_ok=True)
    deb = CACHE / "ukai.deb"
    if not deb.exists():
        print("下载文鼎楷 ...")
        urllib.request.urlretrieve(DEB_URL, deb)
    return deb


def extract_assets(deb):
    """解析 ar 归档 → data.tar.xz → 取出 ukai.ttc 与授权文本"""
    data = deb.read_bytes()
    assert data[:8] == b"!<arch>\n", "不是 deb 包"
    off, payload = 8, None
    while off < len(data):
        hdr = data[off:off + 60]
        name = hdr[:16].decode().strip()
        size = int(hdr[48:58].decode().strip())
        if name.startswith("data.tar"):
            payload = data[off + 60:off + 60 + size]
        off += 60 + size + (size % 2)
    assert payload, "deb 内没有 data.tar"
    if payload[:6] == b"\xfd7zXZ\x00":
        payload = lzma.decompress(payload)
    elif payload[:2] == b"\x1f\x8b":
        payload = gzip.decompress(payload)

    ttf_path = CACHE / "ukai.ttc"
    lic_path = FONTS / "ARPHICPL.txt"
    with tarfile.open(fileobj=io.BytesIO(payload)) as tf:
        for m in tf.getmembers():
            if m.name.endswith("arphic/ukai.ttc"):
                ttf_path.write_bytes(tf.extractfile(m).read())
            elif m.name.endswith("license/english/ARPHICPL.TXT.gz"):
                lic_path.write_bytes(gzip.decompress(tf.extractfile(m).read()))
    print("已取出", ttf_path.name, "与授权文本")
    return ttf_path


def subset_and_rename(src_ttc, chars):
    tmp = CACHE / "subset.woff2"
    chars_file = CACHE / "chars.txt"
    chars_file.write_text(chars, encoding="utf-8")
    subprocess.run(
        [sys.executable, "-m", "fontTools.subset", str(src_ttc), "--font-number=0",
         f"--text-file={chars_file}", f"--output-file={tmp}",
         "--flavor=woff2", "--layout-features=*"],
        check=True,
    )

    f = TTFont(tmp)
    name = f["name"]
    full, ps = f"{FAMILY} {STYLE}", f"{FAMILY}-{STYLE}"
    copyright_txt = (
        'This font is derived from the "AR PL UKai CN" font. '
        '(c) Copyright 1994-1999, Arphic Technology Co., Ltd. '
        f'Subset and renamed to "{FAMILY}" for this project. '
        'Licensed under the Arphic Public License.'
    )
    for nid, val in ((0, copyright_txt), (1, FAMILY), (4, full), (6, ps),
                     (13, LICENSE_TXT), (14, "https://www.arphic.com.tw/")):
        name.setName(val, nid, 3, 1, 0x409)
        name.setName(val, nid, 1, 0, 0)
    for nid in (16, 17):
        name.removeNames(nameID=nid)

    out = FONTS / "gushi-kai.woff2"
    f.flavor = "woff2"
    f.save(out)
    print(f"已生成 {out.relative_to(ROOT)}  {out.stat().st_size // 1024} KB  "
          f"({len(f.getGlyphOrder())} 字形)")


def main():
    chars = poem_chars()
    print("诗词用字", len(chars), "个")
    subset_and_rename(extract_assets(fetch_deb()), chars)


if __name__ == "__main__":
    main()
