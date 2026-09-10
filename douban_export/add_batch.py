# -*- coding: utf-8 -*-
"""批量添加《豆瓣2025年度榜单-不可播放影视清单》条目到网站。

数据来自 _batch_items.json（由 xlsx 解析生成）：序号/片名/sid/评分/评价人数/网盘链接。
rexxar 抓主数据（年份/类型/地区/导演/简介/海报），summary 为空时回退移动页简介。
网盘链接按域名自动分到「夸克网盘链接」或「百度网盘链接」+「百度提取码」。

用法：python add_batch.py [--dry] [--limit N] [--offset N]
"""
import csv, json, os, re, sys, time
import requests
from PIL import Image
from io import BytesIO

CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "movie_master.csv")
CACHE = "rating_count_cache.json"
ITEMS_JSON = "_batch_items.json"
POSTER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "assets", "posters")
_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
PROXIES = {"http": _proxy, "https": _proxy} if _proxy else {}
UA_M = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")


def fetch_subject(sid):
    """rexxar 抓主数据，带重试（偶发 429/403 限流）。"""
    last = None
    for attempt in range(4):
        try:
            r = requests.get("https://m.douban.com/rexxar/api/v2/subject/%s?for_mobile=1" % sid,
                             headers={"User-Agent": UA_M,
                                      "Referer": "https://m.douban.com/movie/subject/%s/" % sid},
                             proxies=PROXIES, timeout=30)
            if r.status_code in (403, 429):
                raise RuntimeError("HTTP %s" % r.status_code)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(2.5 * (attempt + 1))
    raise last


def fetch_intro(sid):
    """rexxar 的 summary 对剧集常为空，回退抓移动页简介段。"""
    try:
        r = requests.get("https://m.douban.com/movie/subject/%s/" % sid,
                         headers={"User-Agent": UA_M}, proxies=PROXIES, timeout=30)
    except Exception:
        return ""
    h = r.text
    for kw in ("剧集简介", "剧情简介"):
        i = h.find(kw)
        if i != -1:
            seg = h[i:i + 1500]
            txt = re.sub(r"<[^>]+>", " ", seg)
            txt = re.sub(r"\s+", " ", txt).strip()[len(kw):].strip()
            txt = re.split(r"\s*var img\s*=|document\.createElement", txt)[0].strip()
            if len(txt) > 30:
                return txt
    return ""


def save_poster(url, sid):
    cover = url.split("?")[0] + "?imageView2/2/w/1000/q/90/format/jpg"
    r = requests.get(cover, headers={"User-Agent": "Mozilla/5.0",
                                     "Referer": "https://movie.douban.com/"},
                     proxies=PROXIES, timeout=40)
    r.raise_for_status()
    im = Image.open(BytesIO(r.content)).convert("RGB")
    w, h = im.size
    im.resize((1000, int(h * 1000 / w)), Image.LANCZOS).save(
        os.path.join(POSTER_DIR, sid + ".webp"), "WEBP", quality=85)


def clean_text(s):
    """豆瓣片名偶带 U+200E 等双向文本控制符（如「凡人修仙传：外海风云‎」），需剔除。"""
    return re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", s or "").strip()


def pick_directors(d):
    """剧集的 directors 常是冗长的分集导演列表，超过 3 人时只取前 3 位。
    豆瓣个别条目（短剧/纪录片）本身未填导演，保留占位「—」。"""
    names = [x.get("name", "") for x in (d.get("directors") or []) if x.get("name")]
    if not names:
        return "—"
    if len(names) > 3:
        return "、".join(names[:3]) + " 等"
    return "、".join(names)


# 豆瓣本身无简介（rexxar summary 与移动页均空）的条目，手写兜底
INTRO_FALLBACK = {
    # 石纪元 第四季 Part.2
    "37005375": "科学王国在千空的带领下持续壮大。为了揭开石化光线的真相、实现飞向月球的计划，"
                "千空与伙伴们一边对抗残留的石化势力，一边把人类文明一级级推向新的高度。",
}


def split_pan(pan):
    """按域名拆分网盘链接，返回 (quark, baidu, baidu_code)。"""
    pan = (pan or "").strip()
    if not pan:
        return "", "", ""
    if "baidu" in pan:
        m = re.search(r"[?&]pwd=([A-Za-z0-9]+)", pan)
        return "", pan, (m.group(1) if m else "")
    return pan, "", ""


def main():
    dry = "--dry" in sys.argv
    limit = offset = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if "--offset" in sys.argv:
        offset = int(sys.argv[sys.argv.index("--offset") + 1])

    items = json.load(open(ITEMS_JSON, encoding="utf-8"))
    if offset:
        items = items[offset:]
    if limit:
        items = items[:limit]

    existing_links = None
    results, failed = [], []

    for idx, it in enumerate(items, 1):
        sid, no = it["sid"], it["no"]
        try:
            d = fetch_subject(sid)
            title = clean_text(d["title"])
            orig = clean_text(d.get("original_title") or "")
            full_orig = "%s / %s" % (title, orig) if orig else title
            year = str(d.get("year") or "")
            genres = "、".join(d.get("genres") or [])
            countries = "、".join(d.get("countries") or [])
            directors = pick_directors(d)
            rating = d.get("rating") or {}
            # rexxar 实时值优先；抓不到（新片/未开分）时回退用清单里的数值
            rval = rating.get("value") or it["rating"]
            rcount = rating.get("count") or it["votes"]
            pic = (d.get("pic") or {}).get("large") or ""
            intro = clean_text((d.get("summary") or "").strip() or fetch_intro(sid)
                               or INTRO_FALLBACK.get(sid, ""))
            qk, bd, bd_code = split_pan(it["pan"])

            results.append(dict(no=no, sid=sid, title=title, full_orig=full_orig, year=year,
                                genres=genres, countries=countries, directors=directors,
                                rval=rval, rcount=rcount, pic=pic, intro=intro,
                                qk=qk, bd=bd, bd_code=bd_code))
            print("[%2d/%d] #%-3s %-24s | %s | %s | 导演:%s | 评 %s/%s | 简介%s字 | %s"
                  % (idx, len(items), no, title[:24], year, countries or "(空)",
                     directors[:18], rval, rcount, len(intro),
                     "百度" if bd else ("夸克" if qk else "无链接")))
            if not intro:
                print("        ⚠️ 简介为空")
            if not pic:
                print("        ⚠️ 海报为空")
        except Exception as e:
            failed.append((no, sid, it["name"], str(e)[:80]))
            print("[%2d/%d] #%-3s %s 抓取失败: %s" % (idx, len(items), no, it["name"], str(e)[:60]))
        time.sleep(0.6)

    print("\n成功 %d，失败 %d" % (len(results), len(failed)))
    if failed:
        print("--- 失败项 ---")
        for no, sid, n, e in failed:
            print("   #%s %s (%s): %s" % (no, n, sid, e))

    if dry:
        print("\n--dry 未写入")
        return

    if not results:
        return

    if existing_links is None:
        existing_links = {(r.get("豆瓣链接") or "")
                          for r in csv.DictReader(open(CSV, encoding="utf-8-sig"))}

    cache = json.load(open(CACHE, encoding="utf-8"))
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    fieldnames = list(rows[0].keys())
    f = open(CSV, "a", encoding="utf-8-sig", newline="")
    w = csv.DictWriter(f, fieldnames=fieldnames)
    added = 0
    for r in results:
        link = "https://movie.douban.com/subject/%s/" % r["sid"]
        if link in existing_links:
            print("   跳过已存在: %s" % r["title"])
            continue
        if r["pic"]:
            try:
                save_poster(r["pic"], r["sid"])
            except Exception as e:
                print("   ⚠️ 海报失败 %s: %s" % (r["sid"], str(e)[:60]))
        cache[r["sid"]] = {"rating": r["rval"], "votes": r["rcount"]}
        w.writerow({
            "片名": r["title"], "完整原名": r["full_orig"], "年份": r["year"],
            "类型": r["genres"], "制片国家": r["countries"], "地区": r["countries"],
            "导演": r["directors"], "我的评分": "—", "豆瓣评分": r["rval"],
            "是否下架": "否", "豆瓣链接": link,
            "海报": "assets/posters/%s.webp" % r["sid"],
            "百度网盘链接": r["bd"], "百度提取码": r["bd_code"],
            "夸克网盘链接": r["qk"], "简介": r["intro"],
        })
        existing_links.add(link)
        added += 1
    f.close()
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n已写入 CSV %d 行，评分缓存 %d 条" % (added, len(cache)))


if __name__ == "__main__":
    main()
