# -*- coding: utf-8 -*-
"""临时：批量 rexxar 校验给定 sid，并检查是否已在 movie_master.csv 中。
用法：python _check_sids.py 25850640,26604456,26869684
"""
import csv, io, os, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from add_single import fetch_subject, fetch_intro

CSV = os.path.join(_HERE, "..", "data", "movie_master.csv")
sids = [s.strip() for s in sys.argv[1].split(",") if s.strip()]

have = {}
for r in csv.reader(io.open(CSV, encoding="utf-8-sig", newline="")):
    if len(r) > 16 and "subject/" in (r[10] if len(r) > 10 else ""):
        sid = r[10].rstrip("/").split("/")[-1]
        have[sid] = (r[14] or "")[:44] + (" |迅雷:" + r[16][:30] if len(r) > 16 and r[16] else "")

for sid in sids:
    print("=== %s ===" % sid)
    if sid in have:
        print("  ⚠️ 已在库！现有网盘：%s" % have[sid])
    else:
        print("  未入库")
    for attempt in range(4):
        try:
            d = fetch_subject(sid)
            break
        except Exception as e:
            if attempt == 3:
                print("  ERR", e)
                d = None
            time.sleep(2.5)
    if not d:
        continue
    intro = (d.get("summary") or "").strip() or fetch_intro(sid)
    dirs = "、".join(x.get("name", "") for x in (d.get("directors") or []))
    print("  %s | %s | %s | %s | 导演:%s | %s/%s | 简介%d字"
          % (d["title"], d.get("year"), "、".join(d.get("genres") or []),
             "、".join(d.get("countries") or []), dirs or "(空)",
             (d.get("rating") or {}).get("value"), (d.get("rating") or {}).get("count"),
             len(intro)))
    print("  intro:", intro[:140].replace("\n", " "))
    time.sleep(0.6)
