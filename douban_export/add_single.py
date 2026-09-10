# -*- coding: utf-8 -*-
"""添加单部影片到网站：python add_single.py <sid> [夸克链接] [--baidu 百度链接 --pwd 提取码] [--xunlei 迅雷链接 --xpwd 提取码] [--dry]
rexxar 抓主数据，summary 为空时回退移动页「剧情简介」段。

网盘可任选或并存（夸克 / 百度 / 迅雷）：
  仅夸克   add_single.py <sid> https://pan.quark.cn/s/xxx
  仅百度   add_single.py <sid> --baidu https://pan.baidu.com/s/xxx --pwd j9q5
  仅迅雷   add_single.py <sid> --xunlei https://pan.xunlei.com/s/xxx --xpwd yh9q
  两者都有 add_single.py <sid> https://pan.quark.cn/s/xxx --baidu <...> --pwd j9q5
"""
import csv, json, os, re, sys
import requests
from PIL import Image
from io import BytesIO

CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "movie_master.csv")
CACHE = "rating_count_cache.json"
POSTER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "assets", "posters")
_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
PROXIES = {"http": _proxy, "https": _proxy} if _proxy else {}
UA_M = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")


def fetch_subject(sid):
    r = requests.get("https://m.douban.com/rexxar/api/v2/subject/%s?for_mobile=1" % sid,
                     headers={"User-Agent": UA_M,
                              "Referer": "https://m.douban.com/movie/subject/%s/" % sid},
                     proxies=PROXIES, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_intro(sid):
    r = requests.get("https://m.douban.com/movie/subject/%s/" % sid,
                     headers={"User-Agent": UA_M}, proxies=PROXIES, timeout=30)
    h = r.text
    for kw in ("剧集简介", "剧情简介"):
        i = h.find(kw)
        if i != -1:
            seg = h[i:i + 1500]
            txt = re.sub(r"<[^>]+>", " ", seg)
            txt = re.sub(r"\s+", " ", txt).strip()
            txt = txt[len(kw):].strip()
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
    nh = int(h * 1000 / w)
    im.resize((1000, nh), Image.LANCZOS).save(
        os.path.join(POSTER_DIR, sid + ".webp"), "WEBP", quality=85)
    return (1000, nh)


def main():
    dry = "--dry" in sys.argv

    def opt(flag):
        """取 --flag 后的值（存在且非空则返回）。"""
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--"):
                return sys.argv[i + 1]
        return ""

    baidu, pwd = opt("--baidu"), opt("--pwd")
    xunlei, xpwd = opt("--xunlei"), opt("--xpwd")
    # 位置参数：剔除各 --flag 的值，避免被误当网盘链接
    opt_vals = {v for v in (baidu, pwd, xunlei, xpwd) if v}
    args = [a for a in sys.argv[1:] if not a.startswith("--") and a not in opt_vals]
    if not args:
        sys.exit("用法：python add_single.py <sid> [夸克链接] [--baidu 链接 --pwd 码] [--xunlei 链接 --xpwd 码] [--dry]")
    sid = args[0]
    quark = args[1] if len(args) > 1 else ""
    if not quark and not baidu and not xunlei:
        sys.exit("至少提供一个网盘链接（夸克位置参数 或 --baidu 或 --xunlei）")

    d = fetch_subject(sid)
    title = d["title"]
    orig = d.get("original_title") or ""
    full_orig = "%s / %s" % (title, orig) if orig else title
    year = str(d.get("year") or "")
    genres = "、".join(d.get("genres") or [])
    countries = "、".join(d.get("countries") or [])
    directors = "、".join(x.get("name", "") for x in (d.get("directors") or []) if x.get("name"))
    rating = d.get("rating") or {}
    rval, rcount = rating.get("value", ""), rating.get("count", 0)
    pic = (d.get("pic") or {}).get("large") or ""
    intro = (d.get("summary") or "").strip() or fetch_intro(sid)

    print("%s | %s | %s | 导演:%s | 评 %s/%s | 简介%d字"
          % (sid, title, year, directors or "(空)", rval, rcount, len(intro)))
    if dry:
        print("   原名:", full_orig, "| 类型:", genres, "| 地区:", countries)
        print("   海报:", pic)
        print("   简介:", intro[:90])
        print("\n--dry 未写入")
        return

    if pic:
        save_poster(pic, sid)
    cache = json.load(open(CACHE, encoding="utf-8"))
    cache[sid] = {"rating": rval, "votes": rcount}
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    link = "https://movie.douban.com/subject/%s/" % sid
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    if link in {(r.get("豆瓣链接") or "") for r in rows}:
        print("   -> 已存在，跳过 CSV")
        return
    with open(CSV, "a", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerow([
            title, full_orig, year, genres, countries, countries, directors or "—",
            "—", rval, "否", link,
            "assets/posters/%s.webp" % sid, baidu, pwd, quark, intro,
            xunlei, xpwd,
        ])
    disk = " + ".join(x for x in ("夸克" if quark else "",
                                  "百度(%s)" % pwd if baidu else "",
                                  "迅雷(%s)" % xpwd if xunlei else "") if x)
    print("   -> 已写入 CSV（%s），评分缓存已更新" % disk)


if __name__ == "__main__":
    main()
