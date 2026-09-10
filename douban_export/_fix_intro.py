# -*- coding: utf-8 -*-
"""通用：给指定 sid 写/覆盖简介（18 列 CSV 的 index15=简介）。
用法：python _fix_intro.py <sid> "<简介文本>" [--force]
默认只填空（已有非空简介则跳过）；--force 强制覆盖。
写后回读校验 index14/16/17（夸克/迅雷链接与提取码）未被改动。
"""
import csv, io, os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(_HERE, "..", "data", "movie_master.csv")
if len(sys.argv) < 3:
    sys.exit("用法：python _fix_intro.py <sid> \"<简介>\" [--force]")
sid, intro = sys.argv[1], sys.argv[2]
force = "--force" in sys.argv

rows = list(csv.reader(io.open(CSV, encoding="utf-8-sig", newline="")))
hit = 0
for r in rows[1:]:
    if len(r) < 18:
        r += [""] * (18 - len(r))
    if "subject/%s/" % sid in (r[10] if len(r) > 10 else ""):
        if (r[15] or "").strip() and not force:
            print("已有简介（%d 字），跳过。要覆盖请加 --force" % len(r[15]))
        else:
            r[15] = intro
            hit += 1

if hit:
    with open(CSV, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)

chk = list(csv.reader(io.open(CSV, encoding="utf-8-sig", newline="")))
for r in chk[1:]:
    if "subject/%s/" % sid in (r[10] if len(r) > 10 else ""):
        print("校验 %s | 简介%d字 | 百度:%s 码%s | 夸克:%s | 迅雷:%s 码%s"
              % (sid, len(r[15]), (r[12] or "")[:40], r[13] or "",
                 (r[14] or "")[:40], (r[16] or "")[:28], r[17] or ""))
