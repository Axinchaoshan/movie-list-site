# -*- coding: utf-8 -*-
"""抓取豆瓣高赞短评，缓存为 JSON，供 gen_site.py 渲染到详情页。

接口（实测可用；影片详情端点被限流，但短评接口正常）：
  https://m.douban.com/rexxar/api/v2/movie/<sid>/interests
      ?type=comment&count=N&start=0&sort=new_score&for_mobile=1
  sort=new_score = 按点赞数（最有用）排序

用法：
  python fetch_comments.py            # 抓取，带断点续跑
  python fetch_comments.py --force    # 忽略已有缓存，全部重抓
  python fetch_comments.py --limit 10 # 只抓前 10 部（测试用）

输出：data/comments_cache.json
"""
import csv, json, os, re, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # 仓库根目录（本文件位于 douban_export/ 下）
CSV = os.path.join(ROOT, "data", "movie_master.csv")
CACHE = os.path.join(ROOT, "data", "comments_cache.json")

# 多抓一些候选，渲染时再按点赞数取前 6 条
# （豆瓣 new_score 排序不完全等于点赞数，多抓才能挑出真正的高赞）
PER_MOVIE = 12
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1")

PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
_opener.addheaders = [("User-Agent", UA)]


def fetch(sid, retries=4):
    """返回 (data, err)；data 为 dict 或 None"""
    url = ("https://m.douban.com/rexxar/api/v2/movie/%s/interests"
           "?type=comment&count=%d&start=0&sort=new_score&for_mobile=1" % (sid, PER_MOVIE))
    last = "未知"
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA,
                         "Referer": "https://m.douban.com/movie/subject/%s/comments" % sid})
            with _opener.open(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8")), None
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:160]
            except Exception:
                pass
            last = "HTTP%s %s" % (e.code, body)
            if e.code in (400, 403, 429):
                time.sleep(8 * (i + 1))   # 限流退避
                continue
            return None, last
        except Exception as e:
            last = "%s" % type(e).__name__
            time.sleep(3 * (i + 1))
    return None, last


def main():
    force = "--force" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    # 只抓指定 sid（逗号分隔），用于增量补片
    sids_only = None
    if "--sids" in sys.argv:
        sids_only = set(sys.argv[sys.argv.index("--sids") + 1].split(","))

    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))

    cache = {}
    if os.path.exists(CACHE) and not force:
        try:
            cache = json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            cache = {}
    print("已有缓存 %d 条，本次 %s" % (len(cache), "强制重抓" if force else "断点续跑"))

    # 收集 (sid, 片名)，跳过无数字 sid 的条目（如 ahs_s2 占位）
    targets = []
    seen = set()
    for r in rows:
        m = re.search(r"/subject/(\d+)", r.get("豆瓣链接") or "")
        if not m:
            continue
        sid = m.group(1)
        if sid in seen:
            continue
        seen.add(sid)
        if sids_only and sid not in sids_only:
            continue
        if not force and sid in cache:
            continue
        targets.append((sid, r["片名"]))
    if limit:
        targets = targets[:limit]

    print("待抓取 %d 部（每部 %d 条短评）\n" % (len(targets), PER_MOVIE))
    ok = fail = 0
    for i, (sid, name) in enumerate(targets, 1):
        d, err = fetch(sid)
        if d and d.get("interests"):
            items = []
            for c in d["interests"][:PER_MOVIE]:
                text = (c.get("comment") or "").strip()
                if not text:
                    continue
                items.append({
                    "text": text,
                    "votes": c.get("vote_count") or 0,
                    "user": (c.get("user") or {}).get("name") or "",
                    "rating": (c.get("rating") or {}).get("value") or "",
                    "date": (c.get("create_time") or "")[:10],
                    "id": c.get("id") or "",
                })
            if items:
                cache[sid] = {"total": d.get("total", 0), "items": items}
                ok += 1
                top = items[0]
                print("[%d/%d] OK   %s  共%s条短评  最高赞%d: %s"
                      % (i, len(targets), name, d.get("total", 0), top["votes"], top["text"][:34]))
            else:
                fail += 1
                print("[%d/%d] SKIP %s (无有效内容)" % (i, len(targets), name))
        else:
            fail += 1
            print("[%d/%d] FAIL %s (%s)" % (i, len(targets), name, err))

        # 每 20 条落盘一次，避免中途挂掉丢进度
        if i % 20 == 0:
            json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print("    ... 已保存进度（%d 条）" % len(cache))
        time.sleep(2.0)

    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n抓取完成：成功 %d，失败 %d，缓存共 %d 条" % (ok, fail, len(cache)))
    print("缓存文件：%s" % CACHE)


if __name__ == "__main__":
    main()
