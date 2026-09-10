# -*- coding: utf-8 -*-
"""
从 movie_master.csv 生成纯静态影视资源站（多页版）。
零框架、零构建：
  - 首页 index.html（流媒体暗色网格：卡片网格 + 搜索/筛选/排序 + 悬停查看详情）
  - 每部片 movie/<id> 独立详情页（独立 title/description/JSON-LD Movie + 站内互链）
  - sitemap.xml 含 101 个 URL（首页 + 100 详情页）
  - 海报统一引用压缩后的 webp
数据列：片名,完整原名,年份,类型,制片国家,地区,导演,我的评分,豆瓣评分,是否下架,豆瓣链接,海报,百度网盘链接,百度提取码,夸克网盘链接,简介,迅雷网盘链接,迅雷提取码
"""
import csv, json, os, glob, shutil, re, unicodedata, urllib.parse
from collections import Counter
from datetime import date
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))

# 数据来源 CSV（18 列，表头见 README「数据格式」）。可用环境变量 MOVIE_SRC 覆盖。
# 优先级：MOVIE_SRC 环境变量 → data/movie_master.csv → data/example_movie_master.csv（开箱即用的示例）
_data_dir = os.path.join(HERE, "data")
_candidates = [
    os.environ.get("MOVIE_SRC"),
    os.path.join(_data_dir, "movie_master.csv"),
    os.path.join(_data_dir, "example_movie_master.csv"),
]
SRC = next((c for c in _candidates if c and os.path.exists(c)), _candidates[1])
# 生成产物输出目录。可用环境变量 MOVIE_OUT 覆盖。
OUT = os.environ.get("MOVIE_OUT") or os.path.join(HERE, "site")

# ===== 可改配置 =====
# 以下均可按需修改；部署前请改成你自己的站点信息。
# 也可用环境变量覆盖：SITE_TITLE / SITE_DESC / SITE_URL / GSC_CODE /
# BING_CODE / TG_URL / CF_ANALYTICS
SITE_TITLE = os.environ.get("SITE_TITLE", "影窝 · 国内看不到的片单（示例）")
SITE_DESC  = os.environ.get("SITE_DESC",
    "收录国内主流平台暂无正版源的影视与动画，提供百度网盘 / 夸克网盘 / 迅雷网盘资源索引，不提供在线播放。")
SITE_URL   = os.environ.get("SITE_URL", "https://your-domain.example/")
# Google Search Console / Bing Webmaster 验证码（改成你自己的，留空则不输出验证标签）
GSC_CODE  = os.environ.get("GSC_CODE", "")
BING_CODE = os.environ.get("BING_CODE", "")
# Telegram 频道（链接失效反馈 / 新片推送），留空则不显示
TG_URL    = os.environ.get("TG_URL", "https://t.me/your_channel")
# Cloudflare Web Analytics 片段（留空则不加统计），可在 Cloudflare 控制台获取
ANALYTICS = os.environ.get("CF_ANALYTICS", "")

# 站点图标（金底「影」字）：ico 兼容旧浏览器/Windows，svg 现代浏览器，png 供 iOS 主屏
FAVICON_LINKS = (
    "<link rel=\"icon\" href=\"/favicon.ico\">\n"
    "<link rel=\"icon\" type=\"image/svg+xml\" href=\"/favicon.svg\" sizes=\"any\">\n"
    "<link rel=\"apple-touch-icon\" href=\"/apple-touch-icon.png\">\n"
)

# 自定义事件埋点已移除（2026-09-07）：/api/event 后端从未部署，纯静态站上永远 404，
# 且被 Googlebot 抓取导致 GSC 报「由于遇到其他 4xx 问题而被屏蔽」。统计用 Cloudflare Web Analytics。
EVENTS_JS = ""
# ====================

os.makedirs(OUT, exist_ok=True)
os.makedirs(os.path.join(OUT, "movie"), exist_ok=True)

def g(row, k):
    v = row.get(k)
    return v.strip() if v else ""

def poster_id(poster_field):
    if not poster_field:
        return ""
    base = os.path.basename(poster_field)
    return os.path.splitext(base)[0]

def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def comment_widget(page, asset_rel):
    """返回一个自包含的评论区 HTML 片段（含样式 + 容器 + 脚本）。"""
    css = """
.comments{max-width:860px;margin:28px auto 0;padding:20px;background:var(--panel,#151a23);border:1px solid var(--line,#222a39);border-radius:14px}
.comments h2{font-size:18px;margin:0 0 14px;color:var(--text,#e9edf5)}
.c-count{color:var(--accent,#f5c518)}
.c-list{display:flex;flex-direction:column;gap:12px;margin-bottom:16px}
.c-empty{color:var(--muted,#8b93a7);font-size:14px;margin:0}
.c-item{padding:12px 14px;background:var(--bg2,#11151e);border:1px solid var(--line,#222a39);border-radius:10px}
.c-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.c-author{font-weight:600;color:var(--text,#e9edf5);font-size:14px}
.c-time{color:var(--muted,#8b93a7);font-size:12px}
.c-body{color:var(--text,#e9edf5);font-size:14px;line-height:1.6;white-space:pre-wrap;word-break:break-word}
.c-form{display:flex;flex-direction:column;gap:10px}
.c-name,.c-text{background:var(--bg2,#11151e);border:1px solid var(--line,#222a39);color:var(--text,#e9edf5);border-radius:9px;padding:10px 12px;font-size:13px;outline:none;font-family:inherit}
.c-text{min-height:80px;resize:vertical}
.c-name:focus,.c-text:focus{border-color:var(--accent,#f5c518)}
.c-submit{align-self:flex-start;background:var(--accent,#f5c518);color:#11151e;border:none;border-radius:9px;padding:10px 20px;font-size:14px;font-weight:600;cursor:pointer}
.c-submit:disabled{opacity:.6;cursor:default}
.c-tip{display:block;margin-top:8px;color:var(--muted,#8b93a7);font-size:12px}
.c-hp{position:absolute;left:-9999px;width:1px;height:1px;opacity:0}
"""
    return (
        '<section class="comments" data-page="%s">'
        '<style>%s</style>'
        '<h2>💬 评论 <span class="c-count">0</span></h2>'
        '<div class="c-list" id="c-list"></div>'
        '<form class="c-form" id="c-form">'
        '<input class="c-name" id="c-name" type="text" maxlength="40" placeholder="昵称（可不填，默认匿名）" autocomplete="off">'
        '<textarea class="c-text" id="c-content" maxlength="1000" placeholder="说点什么吧…（文明发言，广告/外链会被删）" required></textarea>'
        '<input type="text" class="c-hp" id="c-hp" tabindex="-1" autocomplete="off" aria-hidden="true">'
        '<button type="submit" class="c-submit">发表评论</button>'
        '</form>'
        '<small class="c-tip">评论存于 Cloudflare D1，站长可审核删除。</small>'
        '</section>'
        '<script src="%s" defer></script>'
    ) % (esc(page), css, asset_rel)

rows = []
with open(SRC, encoding="utf-8-sig", newline="") as f:
    for idx, row in enumerate(csv.DictReader(f)):
        if not g(row, "片名"):
            continue
        bd   = g(row, "百度网盘链接")
        qk   = g(row, "夸克网盘链接")
        code = g(row, "百度提取码")
        xl   = g(row, "迅雷网盘链接")
        xcd  = g(row, "迅雷提取码")
        if not bd and not qk and not xl:
            continue
        pid = poster_id(g(row, "海报")) or ("m%03d" % idx)
        rows.append({
            "id":        pid,
            "title":     g(row, "片名"),
            "orig":      g(row, "完整原名"),
            "year":      g(row, "年份"),
            "genres":    [x.strip() for x in re.split(r"[、/]", g(row, "类型").strip()) if x.strip()],
            "country":   g(row, "制片国家"),
            "region":    [x.strip() for x in re.split(r"[、/,]", g(row, "地区").strip()) if x.strip()],
            "directors": g(row, "导演"),
            "myrating":  g(row, "我的评分"),
            "rating":    g(row, "豆瓣评分"),
            "takedown":  g(row, "是否下架") == "是",
            "douban":    g(row, "豆瓣链接"),
            "poster":    g(row, "海报"),
            "intro":     g(row, "简介"),
            "bd":        bd,
            "code":      code,
            "qk":        qk,
            "xl":        xl,
            "xcd":       xcd,
        })

region_counts = Counter()
for r in rows:
    for reg in (r["region"] or ["未分类"]):
        region_counts[reg] += 1
stat_line = " · ".join(f"{k} {v}" for k, v in region_counts.most_common())

# 豆瓣高赞短评缓存（fetch_comments.py 抓取，key 为豆瓣 subject id）
COMMENTS = {}
_cmt_path = os.path.join(HERE, "data", "comments_cache.json")
if os.path.exists(_cmt_path):
    try:
        COMMENTS = json.load(open(_cmt_path, encoding="utf-8"))
        print("已载入豆瓣短评缓存：%d 部" % len(COMMENTS))
    except Exception as e:
        print("短评缓存载入失败：%s" % e)
        COMMENTS = {}
# 外部高赞评论缓存（豆瓣抓取失败的作品，从 Letterboxd / IMDb / serializd 等补充，已译为中文）
# 由 external_reviews.json 提供，key 同为豆瓣 subject id；结构见该文件。
EXTERNAL = {}
_ext_path = os.path.join(HERE, "data", "external_reviews.json")
if os.path.exists(_ext_path):
    try:
        EXTERNAL = json.load(open(_ext_path, encoding="utf-8"))
        print("已载入外部评论缓存：%d 部" % len(EXTERNAL))
    except Exception as e:
        print("外部评论缓存载入失败：%s" % e)
        EXTERNAL = {}

# 评分人数缓存（真实豆瓣评分人数，由 backfill_rating_count 脚本回填）
RATING_COUNT = {}
_rc_path = os.path.join(HERE, "data", "rating_count_cache.json")
if os.path.exists(_rc_path):
    try:
        RATING_COUNT = json.load(open(_rc_path, encoding="utf-8"))
        print("已载入评分人数缓存：%d 部" % len(RATING_COUNT))
    except Exception as e:
        print("评分人数缓存载入失败：%s" % e)

def rating_source(r):
    """返回该片的评分来源标签，默认「豆瓣」。

    绝大多数影片的评分来自豆瓣。但 AHS S2/S4 这类豆瓣没有独立条目的影片，
    sid 只是占位符（如 ahs_s2），其评分与投票数取自 IMDb 分集数据加权计算，
    在 rating_count_cache.json 里以 "source": "IMDb" 标注。

    标签必须与评分的真实来源一致，否则结构化数据会与页面可见内容互相矛盾，
    有被搜索引擎判为结构化数据不实的风险。
    """
    _m = re.search(r"/subject/([^/]+)", r.get("douban") or "")
    if _m:
        _rc = RATING_COUNT.get(_m.group(1))
        if isinstance(_rc, dict) and _rc.get("source"):
            return _rc["source"]
    return "豆瓣"

# 低于该点赞数的短评不展示（冷门片最高赞可能只有 0~2，不算「高赞」）
CMT_MIN_VOTES = 3
CMT_MIN_ITEMS = 2

def poster_webp_home(r):   return "assets/posters/%s.webp" % r["id"]
def poster_webp_detail(r): return "../assets/posters/%s.webp" % r["id"]
def poster_abs(r):         return SITE_URL + "assets/posters/%s.webp" % r["id"]
def poster_thumb_home(r):   return "assets/thumb/%s.webp" % r["id"]
def poster_thumb_detail(r): return "../assets/thumb/%s.webp" % r["id"]
def poster_thumb_abs(r):    return SITE_URL + "assets/thumb/%s.webp" % r["id"]
def page_url(r):           return SITE_URL + "movie/%s" % r["id"]

def _cat_groups():
    """返回 {kind: {key: [rows]}}，kind ∈ genre/region/year，供分类落地页与 noscript 共用。"""
    out = {"genre": {}, "region": {}, "year": {}}
    for r in rows:
        for g in (r["genres"] or []):
            out["genre"].setdefault(g, []).append(r)
        for reg in (r["region"] or ["其他"]):
            out["region"].setdefault(reg, []).append(r)
        out["year"].setdefault(r["year"] or "未知", []).append(r)
    return out

def cat_card(r):
    """分类页用的服务端卡片，复用首页 .card / .poster / .info 样式（相对路径 ../）。"""
    bid = r["id"]
    badges = []
    if r["rating"]:
        badges.append('<span class="rate-badge">%s</span>' % esc(r["rating"]))
    if r["region"]:
        badges.append('<span class="region-badge">%s</span>' % esc(r["region"][0]))
    takedown = '<span class="xtakedown">已下架</span>' if r["takedown"] else ""
    sub = " / ".join(filter(None, [r["year"], "、".join(r["genres"])]))
    return (
        '<a class="card" href="../movie/%s">' % bid
        + '<div class="poster">'
        + '<img src="../assets/thumb/%s.webp" alt="%s" loading="lazy" decoding="async">' % (bid, esc(r["title"]))
        + "".join(badges) + takedown
        + '</div>'
        + '<div class="info"><div class="name">%s</div>' % esc(r["title"])
        + '<div class="sub">%s</div></div>' % esc(sub)
        + '</a>'
    )

def build_category(kind, key, items):
    """生成单个分类落地页（类型 / 地区 / 年份）的完整 HTML，含 ItemList JSON-LD。"""
    slug = urllib.parse.quote(key, safe="")
    url = SITE_URL + kind + "/" + slug
    n = len(items)
    by_rate = sorted(items, key=lambda x: -(float(x["rating"] or 0)))
    if kind == "pan":
        # 按网盘类型聚合，承接「夸克网盘 影视资源」这类泛词。
        # 只给片数足够的网盘类型建页（百度仅 16 部，页面太薄，不建）。
        _label = {"quark": "夸克网盘"}.get(key, key)
        h1 = "%s影视资源（共 %d 部）" % (_label, n)
        desc = ("影窝收录的%s影视资源共 %d 部，全部提供%s链接，"
                "附豆瓣评分与豆瓣高赞短评，按豆瓣评分排序。" % (_label, n, _label))
    elif kind == "genre":
        h1 = "%s 类影视（共 %d 部）" % (key, n)
        desc = "影窝收录的%s类影视共 %d 部，提供夸克网盘 / 百度网盘资源索引与豆瓣高赞短评，按豆瓣评分排序。" % (key, n)
    elif kind == "region":
        h1 = "%s 制作影视（共 %d 部）" % (key, n)
        desc = "影窝收录的%s制作影视共 %d 部，提供网盘资源索引与豆瓣高赞短评，按豆瓣评分排序。" % (key, n)
    else:
        h1 = "%s 年影视（共 %d 部）" % (key, n)
        desc = "影窝收录的%s年上映影视共 %d 部，提供网盘资源索引与豆瓣高赞短评，按豆瓣评分排序。" % (key, n)
    cards = "".join(cat_card(r) for r in by_rate)
    img = poster_abs(by_rate[0]) if by_rate else (SITE_URL + "favicon.svg")
    itemlist = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": h1,
        "numberOfItems": n,
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "url": page_url(r), "name": r["title"]}
            for i, r in enumerate(by_rate)
        ],
    }
    ld = json.dumps(itemlist, ensure_ascii=False).replace("</", "<\\/")
    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="index, follow">\n'
        '<meta name="description" content="%s">\n' % esc(desc)
        + '<meta property="og:title" content="%s">\n' % esc(h1)
        + '<meta property="og:description" content="%s">\n' % esc(desc)
        + '<meta property="og:type" content="website">\n'
        + '<meta property="og:url" content="%s">\n' % url
        + '<meta property="og:image" content="%s">\n' % img
        + '<link rel="canonical" href="%s">\n' % url
        + '<meta name="twitter:card" content="summary_large_image">\n'
        + '<title>%s</title>\n' % esc(h1 + " · 影窝片库")
        + '<style>%s</style>\n' % CSS
        + '<link rel="icon" href="/favicon.ico">\n'
        + '<link rel="icon" type="image/svg+xml" href="/favicon.svg" sizes="any">\n'
        + '<link rel="apple-touch-icon" href="/apple-touch-icon.png">\n'
        + '</head>\n<body>\n<div class="detail">\n'
        + '<a class="back" href="../">&larr; 返回影窝片单</a>\n'
        + '<h1>%s</h1>\n' % esc(h1)
        + '<p style="color:var(--muted);font-size:14px;line-height:1.8;margin:6px 0 22px">%s</p>\n' % esc(desc)
        + '<div class="grid">%s</div>\n' % cards
        + '<footer>资源来自网络，仅供个人交流学习，请支持正版。<br>'
        + '本站不提供在线播放；网盘链接由站长持续补全，失效可反馈。<br>'
        + '<a href="../" style="color:#229ed9">返回影窝片单</a></footer>\n'
        + '</div>\n<script type="application/ld+json">%s</script>\n' % ld
        + ANALYTICS + '\n</body>\n</html>'
    )

def gen_thumbs(width=320, quality=82):
    """为网格/相关推荐生成小尺寸缩略图，避免首页加载 480px 原图。"""
    src_dir = os.path.join(OUT, "assets", "posters")
    dst_dir = os.path.join(OUT, "assets", "thumb")
    os.makedirs(dst_dir, exist_ok=True)
    n = 0
    for fp in glob.glob(os.path.join(src_dir, "*.webp")):
        name = os.path.basename(fp)
        outp = os.path.join(dst_dir, name)
        try:
            im = Image.open(fp)
            if im.width > width:
                h = round(im.height * width / im.width)
                im = im.resize((width, h), Image.LANCZOS)
            im.save(outp, "WEBP", quality=quality)
            n += 1
        except Exception:
            pass
    return n

# ---------- 公共 CSS（详情页样式保留 + 新增首页资料库风） ----------
CSS = """\
:root{
  --bg:#06080d; --bg2:#0c111c; --panel:#141a2e; --panel2:#1a2238;
  --text:#eef1f8; --muted:#8d97b0; --accent:#f5c518; --accent2:#ff6b6b;
  --ambient:#7c5cff; --line:#232c47; --line2:#2f3a5e;
  --ok:#3ecf8e; --shadow:rgba(0,0,0,.6);
  --r-sm:8px; --r-md:12px; --r-lg:16px; --r-xl:22px;
  --sh-1:0 2px 8px rgba(0,0,0,.35);
  --sh-2:0 10px 26px rgba(0,0,0,.45);
  --sh-3:0 22px 54px rgba(0,0,0,.58);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;color:var(--text);
  font-family:-apple-system,"PingFang SC","Microsoft YaHei",Segoe UI,Roboto,sans-serif;
  -webkit-font-smoothing:antialiased;
  background-color:var(--bg);
  background-image:
    radial-gradient(900px 430px at 16% -6%, rgba(124,92,255,.15), transparent 62%),
    radial-gradient(760px 380px at 88% -2%, rgba(245,197,24,.08), transparent 60%);
  background-repeat:no-repeat;
}
a{color:inherit;text-decoration:none}
.detail{max-width:1280px;margin:0 auto;padding:28px 20px 70px}

.topbar{position:sticky;top:0;z-index:50;background:rgba(6,8,13,.86);backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
.topbar-inner{max-width:1320px;margin:0 auto;display:flex;align-items:center;gap:18px;padding:14px 22px}
.brand{font-size:22px;font-weight:800;white-space:nowrap;letter-spacing:.3px;margin:0}
.brand span{color:var(--accent)}
.search{flex:1;min-width:180px;padding:11px 16px;border-radius:var(--r-md);border:1px solid var(--line);background:var(--bg2);color:var(--text);font-size:14px;outline:none;transition:.15s}
.search:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(245,197,24,.10)}
.topstat{color:var(--muted);font-size:13px;white-space:nowrap}
.topstat b{color:var(--text)}

.hero{max-width:1320px;margin:24px auto 0;padding:0 22px}
.hero-inner{position:relative;overflow:hidden;border-radius:var(--r-xl);
  border:1px solid var(--line2);padding:26px 28px;
  background:
    radial-gradient(620px 300px at 12% 8%, rgba(124,92,255,.22), transparent 65%),
    radial-gradient(520px 260px at 92% 92%, rgba(245,197,24,.13), transparent 62%),
    linear-gradient(135deg,#141d38 0%,#0d1220 58%,#090d16 100%);
  box-shadow:var(--sh-2);
  display:grid;grid-template-columns:1.45fr 1fr;gap:28px;align-items:center}
.hero-kicker{margin:0 0 9px;font-size:12px;letter-spacing:2px;color:var(--ambient);font-weight:700}
.hero-title{margin:0;font-size:30px;line-height:1.25;font-weight:800;letter-spacing:.2px}
.hero-meta{margin:11px 0 0;font-size:13px;color:var(--muted)}
.hero-meta b{color:var(--accent);font-size:17px;font-weight:800}
.hero-desc{margin:13px 0 0;font-size:14px;line-height:1.85;color:#c3cadd;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.hero-actions{display:flex;gap:10px;margin-top:19px;flex-wrap:wrap}
.hero-btn{display:inline-flex;align-items:center;padding:11px 21px;border-radius:var(--r-md);
  font-size:14px;font-weight:600;transition:.15s;border:1px solid transparent;white-space:nowrap}
.hero-btn.primary{background:var(--accent);color:#170f00}
.hero-btn.primary:hover{filter:brightness(1.08)}
.hero-btn.ghost{background:rgba(255,255,255,.04);border-color:var(--line2);color:var(--text)}
.hero-btn.ghost:hover{border-color:var(--accent);color:var(--accent)}
.hero-side{list-style:none;margin:0;padding:0;display:grid;gap:2px}
.hero-side li{border-top:1px solid var(--line)}
.hero-side a{display:flex;align-items:baseline;gap:10px;padding:10px 2px;font-size:13px;color:#c3cadd;transition:.15s}
.hero-side a:hover{color:var(--text)}
.hero-side .hs-name{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hero-side .hs-rate{color:var(--accent);font-weight:800;font-variant-numeric:tabular-nums}

.filterbar{max-width:1320px;margin:0 auto;padding:20px 22px 4px;display:flex;flex-direction:column;gap:14px}
.filter-row{display:flex;flex-wrap:wrap;gap:14px 26px;align-items:flex-start}
.fgroup{display:flex;flex-direction:column;gap:9px}
.fgroup h3{font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin:0;font-weight:700;display:flex;justify-content:space-between}
.chips{display:flex;flex-wrap:wrap;gap:8px 10px;padding-bottom:2px}
.chip{padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--panel);color:var(--muted);font-size:12px;cursor:pointer;user-select:none;transition:.15s;white-space:nowrap}
.chip:hover{background:var(--panel2);color:var(--text);border-color:var(--line2)}
.chip.active{background:var(--accent);color:#14100a;border-color:var(--accent);font-weight:700}
.chips-extra{display:none}
.chips-extra:not(.collapsed){display:flex;flex-wrap:wrap;gap:8px 10px;width:100%;padding-top:12px;margin-top:8px;border-top:1px dashed var(--line)}
.chip-toggle{background:rgba(255,255,255,.04);border-style:dashed;color:var(--muted);align-self:flex-start}
.chip-toggle:hover{background:rgba(255,255,255,.08);color:var(--text);border-color:var(--accent)}
.sortsel{background:var(--bg2);color:var(--text);border:1px solid var(--line);border-radius:var(--r-md);padding:10px 12px;font-size:13px;outline:none;min-width:160px;align-self:flex-end}
.clearbtn{padding:10px 15px;border-radius:var(--r-md);border:1px solid var(--line);background:transparent;color:var(--muted);font-size:13px;cursor:pointer;transition:.15s;height:fit-content;align-self:flex-end;white-space:nowrap}
.clearbtn:hover{color:var(--text);border-color:var(--accent)}

.resultbar{max-width:1320px;margin:0 auto;padding:12px 22px 0;color:var(--muted);font-size:13px}
.resultbar b{color:var(--text)}

.grid{max-width:1320px;margin:0 auto;padding:20px 18px 70px;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:24px 18px}
.card{position:relative;border-radius:var(--r-lg);overflow:hidden;background:linear-gradient(180deg,var(--panel) 0%,#101524 100%);border:1px solid var(--line);transition:.2s;text-decoration:none;display:flex;flex-direction:column;box-shadow:var(--sh-1)}
.card:hover{transform:translateY(-6px);border-color:var(--accent);box-shadow:0 18px 40px var(--shadow),0 0 0 1px rgba(245,197,24,.25)}
.poster{position:relative;overflow:hidden;background:var(--panel2);height:0;padding-top:150%}
.poster img{position:absolute;top:0;left:0;width:100%;height:100%;-webkit-object-fit:cover;object-fit:cover;display:block;transition:.3s}
.poster-empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:13px;background:var(--panel2);z-index:0}
.poster .overlay{z-index:2}
.card:hover .poster img{transform:scale(1.07)}
.rate-badge{position:absolute;top:8px;right:8px;background:var(--accent);color:#170f00;font-weight:800;font-size:13px;padding:2px 8px;border-radius:var(--r-sm);font-variant-numeric:tabular-nums;box-shadow:var(--sh-1)}
.region-badge{position:absolute;top:8px;left:8px;background:rgba(6,8,13,.82);color:var(--text);font-size:11px;padding:2px 8px;border-radius:var(--r-sm);white-space:nowrap}
.xtakedown{position:absolute;bottom:8px;left:8px;font-size:10px;font-weight:700;color:#fff;background:var(--accent2);padding:2px 7px;border-radius:5px}
.overlay{position:absolute;inset:0;background:linear-gradient(to top,rgba(6,8,13,.94) 0%,rgba(6,8,13,.40) 45%,transparent 70%);opacity:0;transition:.2s;display:flex;align-items:flex-end;padding:12px}
.card:hover .overlay{opacity:1}
.overlay .view{color:#fff;font-size:13px;font-weight:700;border:1px solid var(--accent);border-radius:var(--r-md);padding:7px 12px;width:100%;text-align:center;background:rgba(245,197,24,.14)}
.card .info{padding:11px 12px;flex:0 0 auto}
.card .name{font-size:14px;font-weight:600;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text)}
.card .sub{color:var(--muted);font-size:12px;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card-link{display:flex;flex-direction:column;flex:1 1 auto;color:inherit}
.card-actions{display:flex;gap:8px;padding:0 10px 12px;margin-top:auto}
.card-btn{flex:1;display:inline-flex;align-items:center;justify-content:center;padding:9px 0;border-radius:10px;font-size:12.5px;font-weight:700;text-align:center;transition:.15s}
.card-btn:hover{filter:brightness(1.08)}
.banner-row{max-width:1320px;margin:18px auto 0;padding:0 22px;display:grid;grid-template-columns:1fr 1fr;gap:14px}
.netdisk-banner{padding:12px 18px;display:flex;align-items:center;gap:16px;background:linear-gradient(135deg,rgba(245,197,24,.13),rgba(124,92,255,.08));border:1px solid var(--accent);border-radius:var(--r-lg);box-shadow:var(--sh-1)}
.netdisk-banner .nd-emoji{font-size:30px;line-height:1;flex:0 0 auto}
.netdisk-banner .nd-text{display:flex;flex-direction:column;gap:4px;flex:1 1 auto;min-width:0}
.netdisk-banner strong{font-size:16px;color:var(--text);font-weight:700}
.netdisk-banner span{font-size:13px;color:var(--muted)}
.netdisk-banner .nd-btn{margin-left:auto;flex:0 0 auto;padding:10px 22px;border-radius:var(--r-md);background:var(--accent);color:#1a1205;font-size:14px;font-weight:600;text-decoration:none;transition:.15s;white-space:nowrap}
.netdisk-banner .nd-btn:hover{filter:brightness(1.08)}
.tg-banner{padding:12px 18px;display:flex;align-items:center;gap:16px;background:linear-gradient(135deg,rgba(34,158,217,.17),rgba(34,158,217,.05));border:1px solid #229ed9;border-radius:var(--r-lg);box-shadow:var(--sh-1)}
.tg-banner .nd-emoji{font-size:28px;line-height:1;flex:0 0 auto}
.tg-banner .nd-text{display:flex;flex-direction:column;gap:4px;flex:1 1 auto;min-width:0}
.tg-banner strong{font-size:16px;color:var(--text);font-weight:700}
.tg-banner span{font-size:13px;color:var(--muted)}
.tg-banner .tg-btn{margin-left:auto;flex:0 0 auto;padding:10px 22px;border-radius:var(--r-md);background:#229ed9;color:#fff;font-size:14px;font-weight:600;text-decoration:none;transition:.15s;white-space:nowrap}
.tg-banner .tg-btn:hover{filter:brightness(1.1)}
.empty{padding:70px 0;text-align:center;color:var(--muted);font-size:15px;grid-column:1/-1}

.back{color:var(--muted);font-size:14px;display:inline-flex;align-items:center;gap:6px;margin-bottom:18px;transition:.15s}
.back:hover{color:var(--accent)}
.dtop{display:flex;gap:32px;flex-wrap:wrap;align-items:flex-start}
.dposter{width:260px;flex:0 0 260px;aspect-ratio:2/3;border-radius:var(--r-lg);overflow:hidden;border:1px solid var(--line2);background:var(--panel2);box-shadow:var(--sh-3)}
.dposter img{width:100%;height:100%;object-fit:cover;display:block}
.dinfo{flex:1;min-width:300px}
.dinfo h1{margin:0 0 6px;font-size:32px;line-height:1.25;font-weight:800;letter-spacing:.2px}
.dorig{color:var(--muted);font-style:italic;font-size:15px;margin-bottom:14px}
.dmeta{color:var(--muted);font-size:14px;line-height:2.2}
.dupd{color:var(--muted);font-size:12px;margin:2px 0 12px;opacity:.75}
.resinfo{background:var(--bg2);border:1px solid var(--line);border-radius:var(--r-md);padding:10px 13px;margin:0 0 12px;font-size:13px;line-height:1.75;color:var(--text)}
.resinfo b{color:var(--text);font-weight:500}
.dmeta b{color:var(--text);font-weight:500}
.dmeta .tag{background:var(--panel2);color:var(--text);font-size:12px;padding:4px 11px;border-radius:999px;margin-right:6px;border:1px solid var(--line)}
.dintro{margin-top:24px;line-height:1.9;font-size:15px;color:#d3dae8}
.dcmts{margin-top:44px}
.dcmts h2{font-size:17px;margin:0 0 14px;font-weight:700}
.cmt-list{list-style:none;padding:0;margin:0;display:grid;gap:12px}
.cmt{background:var(--panel);border:1px solid var(--line);border-radius:var(--r-md);padding:14px 16px}
.cmt-text{margin:0;font-size:15px;line-height:1.85;color:var(--text)}
.cmt-meta{margin-top:9px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;font-size:12px;color:var(--muted)}
.cmt-user{font-weight:600}
.cmt-rate{color:var(--accent)}
.cmt-votes{color:var(--accent2)}
.cmt-src{margin-top:14px;font-size:12px;color:var(--muted)}
.cmt-src a{color:var(--accent2)}
.cmt-fold{border:1px solid var(--line);border-radius:var(--r-md);background:var(--panel);padding:0;overflow:hidden}
.cmt-fold>summary{cursor:pointer;list-style:none;padding:13px 16px;font-size:14px;font-weight:600;color:var(--accent);user-select:none}
.cmt-fold>summary::-webkit-details-marker{display:none}
.cmt-fold>summary::before{content:"▸";display:inline-block;margin-right:8px;transition:transform .15s}
.cmt-fold[open]>summary::before{transform:rotate(90deg)}
.cmt-fold>summary:hover{color:var(--text)}
.cmt-fold .cmt-list{padding:0 16px 16px}
.dacts{margin-top:26px;display:flex;gap:12px;flex-wrap:wrap}
.dacts .btn{min-width:150px;flex:0 0 auto;padding:11px 22px;border-radius:11px;font-size:14px;font-weight:600;text-align:center;transition:.15s}
.btn-douban{background:var(--panel2);border:1px solid var(--line2);color:var(--text)}
.btn-douban:hover{border-color:var(--accent);color:var(--accent)}
.btn-baidu{background:#2563eb;color:#fff}
.btn-baidu:hover{filter:brightness(1.08)}
.btn-quark{background:#21c17a;color:#06281c}
.btn-quark:hover{filter:brightness(1.08)}
.btn-xunlei{background:#ff8a00;color:#1a1000}
.btn-xunlei:hover{filter:brightness(1.08)}
.btn-tg{background:#229ed9;color:#fff}
.btn-tg:hover{filter:brightness(1.08)}
.tg-tip{margin-top:12px;font-size:12px;color:var(--muted);line-height:1.7}
.tg-tip a{color:#229ed9}
.off{opacity:.45;cursor:default}
.rel{margin-top:56px}
.rel h3{font-size:18px;margin:0 0 18px;font-weight:700}
.rel-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:16px}
.sentinel{height:1px;width:100%}
.rel-card{background:var(--panel);border-radius:var(--r-md);overflow:hidden;border:1px solid var(--line);transition:.18s;box-shadow:var(--sh-1)}
.rel-card:hover{border-color:var(--accent);transform:translateY(-4px);box-shadow:var(--sh-2)}
.rel-card img{width:100%;aspect-ratio:2/3;object-fit:cover;display:block}
.rel-card .rt{padding:9px 11px;font-size:13px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:52px;line-height:1.9;border-top:1px solid var(--line);padding-top:22px}

@media (max-width:980px){
  .hero-inner{grid-template-columns:1fr;gap:20px}
  .hero-side{border-top:1px solid var(--line);padding-top:6px}
}
@media (max-width:860px){
  .filterbar{padding:14px 16px 2px;gap:12px 18px}
  .fgroup{min-width:140px}
  .grid{grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:16px 14px;padding:16px 14px 50px}
  .dtop{gap:20px}
}
@media (max-width:560px){
  .topbar-inner{padding:10px 14px;gap:12px}
  .brand{font-size:17px}
  .hero{padding:0 14px;margin-top:16px}
  .hero-inner{padding:20px 18px}
  .hero-title{font-size:23px}
  .grid{grid-template-columns:repeat(auto-fill,minmax(108px,1fr));gap:14px 10px}
  .card .name{font-size:13px}
  .sortsel{min-width:120px}
  .dposter{width:100%;flex:0 0 auto;max-width:280px;margin:0 auto}
  .dinfo h1{font-size:24px}
  .banner-row{grid-template-columns:1fr;padding:0 14px}
  .netdisk-banner,.tg-banner{flex-wrap:nowrap}
  .netdisk-banner .nd-text,.tg-banner .nd-text{min-width:0}
  .netdisk-banner .nd-btn,.tg-banner .tg-btn{margin-left:0}
}
"""

with open(os.path.join(OUT, "style.css"), "w", encoding="utf-8") as f:
    f.write(CSS)

# 生成缩略图（网格/相关推荐用），并给静态资源写长缓存头
n_thumb = gen_thumbs()
print("  - 缩略图 %d 张 -> assets/thumb/" % n_thumb)

# ---------- 首页 JSON-LD ItemList（item 指向本站详情页，利于站内 SEO/GEO） ----------
def movie_item(i, r):
    item = {
        "@type": "Movie",
        "name": r["title"],
        "url": page_url(r),
        "image": poster_abs(r),
    }
    if r.get("orig"):
        item["alternateName"] = r["orig"].split(" / ")[-1]
    if r.get("intro"):
        item["description"] = r["intro"]
    if r.get("genres"):
        item["genre"] = r["genres"]
    if r.get("year"):
        item["datePublished"] = r["year"]
    if r.get("directors"):
        item["director"] = {"@type": "Person", "name": r["directors"]}
    return {"@type": "ListItem", "position": i + 1, "item": item}

jsonld = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    "name": SITE_TITLE,
    "description": SITE_DESC,
    "itemListElement": [movie_item(i, r) for i, r in enumerate(rows)],
}
jsonld_json = json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/")

# SiteNavigationElement schema
nav_schema = {
    "@context": "https://schema.org",
    "@type": "SiteNavigationElement",
    "name": "影窝站点导航",
    "url": SITE_URL,
    "hasPart": [
        {"@type": "WebPage", "name": "片库首页", "url": SITE_URL},
        {"@type": "WebPage", "name": "关于影窝", "url": SITE_URL + "about"},
        {"@type": "FAQPage", "name": "常见问题", "url": SITE_URL + "faq"},
    ],
}
nav_json = json.dumps(nav_schema, ensure_ascii=False).replace("</", "<\\/")

# 站点级 schema（WebSite + Organization）：让搜索引擎与 AI 把「影窝」识别为一个品牌实体，
# 而不是一堆互不关联的页面。用 @graph + @id 互相引用，避免 schema 碎片化。
site_schema = {
    "@context": "https://schema.org",
    "@graph": [
        {
            "@type": "Organization",
            "@id": SITE_URL + "#organization",
            "name": "影窝",
            "url": SITE_URL,
            "logo": {
                "@type": "ImageObject",
                "url": SITE_URL + "apple-touch-icon.png",
            },
            "description": SITE_DESC,
            "sameAs": [TG_URL],
        },
        {
            "@type": "WebSite",
            "@id": SITE_URL + "#website",
            "name": "影窝",
            "alternateName": SITE_TITLE,
            "url": SITE_URL,
            "description": SITE_DESC,
            "inLanguage": "zh-CN",
            "publisher": {"@id": SITE_URL + "#organization"},
            "potentialAction": {
                "@type": "SearchAction",
                "target": {
                    "@type": "EntryPoint",
                    "urlTemplate": SITE_URL + "?q={search_term_string}",
                },
                "query-input": "required name=search_term_string",
            },
        },
    ],
}
site_json = json.dumps(site_schema, ensure_ascii=False).replace("</", "<\\/")

for r in rows:
    r["_id"] = r["id"]
    r["_poster"] = poster_webp_home(r)   # 详情页主图（480px 原图）
    r["_thumb"] = poster_thumb_home(r)  # 首页网格 + 相关推荐（缩略图）
data_json = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")

VERIFY_META = ""
if GSC_CODE:
    VERIFY_META += '<meta name="google-site-verification" content="%s">\n' % GSC_CODE
if BING_CODE:
    VERIFY_META += '<meta name="msvalidate.01" content="%s">\n' % BING_CODE

# ---------- 首页 HTML：资料库风（侧栏筛选 + 信息密集表格） ----------
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="__DESC__">
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:type" content="website">
<meta property="og:url" content="__SITEURL__">
<link rel="canonical" href="__SITEURL__">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="__TITLE__">
<meta name="twitter:description" content="__DESC__">
__VERIFY__
<title>__TITLE__</title>
<link rel="preconnect" href="__SITEURL__">
<link rel="dns-prefetch" href="__SITEURL__">
<style>__CSS__</style>
<link rel="icon" href="/favicon.ico">
<link rel="icon" type="image/svg+xml" href="/favicon.svg" sizes="any">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
</head>
<body>
<div id="app">
  <div class="topbar">
    <div class="topbar-inner">
      <h1 class="brand"><span>影窝</span> · 片库</h1>
      <input id="search" class="search" type="search" placeholder="搜索片名 / 导演 / 类型…">
      <div class="topstat">共 <b id="total">0</b> 部</div>
    </div>
  </div>

__HERO__

  <div class="banner-row">
    <div class="netdisk-banner">
      <span class="nd-emoji">📦</span>
      <div class="nd-text">
        <strong>全站网盘资源</strong>
        <span>点卡片「网盘」按钮</span>
      </div>
      <a class="nd-btn" href="/faq">下载说明</a>
    </div>

    <div class="tg-banner">
      <span class="nd-emoji">✈️</span>
      <div class="nd-text">
        <strong>加入 Telegram 频道</strong>
        <span>失效秒补 · 新片推送</span>
      </div>
      <a class="tg-btn" href="__TGURL__" target="_blank" rel="noopener">加入频道</a>
    </div>
  </div>

  <div class="filterbar">
    <div class="fgroup ftype">
      <h3>类型</h3>
      <div class="chips" id="genreChips"></div>
    </div>
    <div class="filter-row">
      <div class="fgroup fregion">
        <h3>地区</h3>
        <div class="chips" id="regionChips"></div>
      </div>
      <select id="sort" class="sortsel">
        <option value="rating">评分（高 → 低）</option>
        <option value="year">年份（新 → 旧）</option>
        <option value="title">片名（A → Z）</option>
      </select>
      <button class="clearbtn" id="clearBtn">清除筛选</button>
    </div>
  </div>

  <div class="resultbar">显示 <b id="shown">0</b> / <span id="total2">0</span> 部</div>

  <div class="grid" id="grid"></div>
  <div id="sentinel" class="sentinel" aria-hidden="true"></div>

  <footer>
    资源来自网络，仅供个人交流学习，请支持正版。<br>
    本站不提供在线播放；网盘链接由站长持续补全，失效可反馈。<br>
    <a href="pan/quark" style="color:#229ed9">夸克网盘影视资源（全部 __QKCOUNT__ 部）</a> ·
    <a href="__TGURL__" target="_blank" rel="noopener" style="color:#229ed9">✈️ Telegram 频道 · 新片推送 / 链接失效反馈</a>
  </footer>
  __COMMENTS_HOME__
</div>
<noscript>
<h2>全部片单（共 __NOSCRIPT_COUNT__ 部，按地区分组）</h2>
<ul>
__NOSCRIPT_LIST__
</ul>
</noscript>

<script type="application/ld+json">__JSONLD__</script>
<script type="application/ld+json">__NAV__</script>
<script type="application/ld+json">__SITE__</script>
<script>
var DATA = __DATA__;
var state = { q:'', genres:{}, regions:{}, sort:'rating' };

function esc(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function buildChipsGroup(wrap, counts, store){
  wrap.innerHTML='';
  var keys=Object.keys(counts).sort(function(a,b){return counts[b]-counts[a];});
  var init=3;
  var visibleKeys=keys.slice(0,init);
  var hiddenKeys=keys.slice(init);
  // 若隐藏区里有已选中的筛选项，默认展开，避免用户找不到当前过滤条件
  var expanded=hiddenKeys.some(function(k){return store[k];});
  visibleKeys.forEach(function(k){
    wrap.appendChild(makeChip(k, counts[k], store));
  });
  if(hiddenKeys.length){
    var extra=document.createElement('span');
    extra.className='chips-extra'+(expanded?'':' collapsed');
    hiddenKeys.forEach(function(k){
      extra.appendChild(makeChip(k, counts[k], store));
    });
    wrap.appendChild(extra);
    var btn=document.createElement('span');
    btn.className='chip chip-toggle';
    btn.textContent=(expanded?'收起 ':'展开 ')+hiddenKeys.length+' 个';
    btn.onclick=function(){
      if(extra.classList.contains('collapsed')){
        extra.classList.remove('collapsed');
        btn.textContent='收起 '+hiddenKeys.length+' 个';
      }else{
        extra.classList.add('collapsed');
        btn.textContent='展开 '+hiddenKeys.length+' 个';
      }
    };
    wrap.appendChild(btn);
  }
}

function buildChips(){
  var gCount={}, rCount={};
  DATA.forEach(function(d){
    (d.genres||[]).forEach(function(g){ gCount[g]=(gCount[g]||0)+1; });
    (d.region||[]).forEach(function(rg){ rCount[rg]=(rCount[rg]||0)+1; });
    if(!(d.region||[]).length) rCount['未分类']=(rCount['未分类']||0)+1;
  });
  buildChipsGroup(document.getElementById('genreChips'), gCount, state.genres);
  buildChipsGroup(document.getElementById('regionChips'), rCount, state.regions);
}
function makeChip(label, count, store){
  var c=document.createElement('span');
  c.className='chip'+(store[label]?' active':'');
  c.textContent=label+' '+count;
  c.onclick=function(){
    store[label]=!store[label];
    c.className='chip'+(store[label]?' active':'');
    render(true);
  };
  return c;
}

function cardHTML(d){
  var poster = d._thumb
    ? '<img src="'+d._thumb+'" alt="'+esc(d.title)+'" loading="lazy" decoding="async" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block" onerror="this.style.display=\'none\'">'
    : '<div class="poster-empty">暂无海报</div>';
  var rate = d.rating ? '<span class="rate-badge">'+esc(d.rating)+'</span>' : '';
  var region = (d.region && d.region.length) ? '<span class="region-badge">'+esc(d.region[0])+'</span>' : '';
  var td = d.takedown ? '<span class="xtakedown">下架</span>' : '';
  var sub = [d.year, d.country].filter(Boolean).join(' · ');
  var actions = '';
  if(d.bd || d.qk || d.xl){
    var btns = [];
    if(d.bd) btns.push('<a class="btn-baidu card-btn" href="'+esc(d.bd)+'" target="_blank" rel="noopener">百度网盘</a>');
    if(d.qk) btns.push('<a class="btn-quark card-btn" href="'+esc(d.qk)+'" target="_blank" rel="noopener">夸克网盘</a>');
    if(d.xl) btns.push('<a class="btn-xunlei card-btn" href="'+esc(d.xl)+'" target="_blank" rel="noopener">迅雷网盘</a>');
    actions = '<div class="card-actions">'+btns.join('')+'</div>';
  }
  return '<div class="card">'
    + '<a class="card-link" href="movie/'+d._id+'">'
    + '<div class="poster">'+poster+rate+region+td
    + '<div class="overlay"><div class="view">查看详情</div></div></div>'
    + '<div class="info"><div class="name">'+esc(d.title)+'</div>'
    + (sub ? '<div class="sub">'+esc(sub)+'</div>' : '') + '</div></a>'
    + actions
    + '</div>';
}

function filtered(){
  var q=state.q.trim().toLowerCase();
  var gs=Object.keys(state.genres).filter(function(k){return state.genres[k];});
  var rs=Object.keys(state.regions).filter(function(k){return state.regions[k];});
  return DATA.filter(function(d){
    if(q){
      var hay=(d.title+' '+(d.orig||'')+' '+(d.directors||'')+' '+((d.genres||[]).join(' '))+' '+(d.intro||'')).toLowerCase();
      if(hay.indexOf(q)<0) return false;
    }
    if(gs.length){
      var ok=false;
      for(var i=0;i<gs.length;i++){ if((d.genres||[]).indexOf(gs[i])>=0){ ok=true; break; } }
      if(!ok) return false;
    }
    if(rs.length){
      var rr=d.region||[];
      var ok=false;
      for(var i=0;i<rs.length;i++){ if(rr.indexOf(rs[i])>=0){ ok=true; break; } }
      if(!ok) return false;
    }
    return true;
  });
}

var visible=24;            // 首屏渲染数量（避免一次加载 100 张图）
var current=[];            // 当前筛选+排序后的结果
var loading=false;
function cardNode(d){
  var wrap=document.createElement('div');
  wrap.innerHTML=cardHTML(d);
  return wrap.firstElementChild;
}
function updateCounts(n){
  document.getElementById('shown').textContent=n;
  document.getElementById('total').textContent=DATA.length;
  document.getElementById('total2').textContent=DATA.length;
}
function render(reset){
  current=filtered();
  current.sort(function(a,b){
    if(state.sort==='year') return (parseInt(b.year)||0)-(parseInt(a.year)||0);
    if(state.sort==='title') return a.title.localeCompare(b.title,'zh');
    return (parseFloat(b.rating)||0)-(parseFloat(a.rating)||0);
  });
  var grid=document.getElementById('grid');
  var sentinel=document.getElementById('sentinel');
  if(reset){ grid.innerHTML=''; visible=24; }
  if(!current.length){
    grid.innerHTML='<div class="empty">没有匹配的结果，试试放宽筛选条件。</div>';
    sentinel.style.display='none';
    updateCounts(0);
    return;
  }
  var start=grid.children.length;
  var slice=current.slice(start, visible);
  for(var i=0;i<slice.length;i++){ grid.appendChild(cardNode(slice[i])); }
  var more=visible<current.length;
  sentinel.style.display=more?'block':'none';
  updateCounts(current.length);
}
function loadMore(){
  if(loading) return;
  loading=true;
  setTimeout(function(){ visible+=24; render(false); loading=false; }, 30);
}

document.getElementById('search').addEventListener('input',function(e){ state.q=e.target.value; render(true); });
document.getElementById('sort').addEventListener('change',function(e){ state.sort=e.target.value; render(true); });
document.getElementById('clearBtn').addEventListener('click',function(){
  state.q=''; state.genres={}; state.regions={}; state.sort='rating';
  document.getElementById('search').value=''; document.getElementById('sort').value='rating';
  buildChips(); render(true);
});
// 支持 ?q=关键词 直达筛选结果（与首页 WebSite SearchAction 声明保持一致）
(function(){
  var m = location.search.match(/[?&]q=([^&]*)/);
  if(m){ var kw = decodeURIComponent((m[1]||'').replace(/\+/g,' ')); if(kw){ state.q = kw; document.getElementById('search').value = kw; } }
})();

if('IntersectionObserver' in window){
  var io=new IntersectionObserver(function(es){
    es.forEach(function(en){ if(en.isIntersecting){ loadMore(); } });
  }, {rootMargin:'500px'});
  io.observe(document.getElementById('sentinel'));
}

buildChips();
render(true);
</script>
__EVENTS__
__ANALYTICS__
</body>
</html>"""

# noscript: 全部影片的纯 HTML 列表（给搜索引擎 / AI 爬虫）
# 注意：AI 爬虫（GPTBot / ClaudeBot 等）一般不执行 JS，若只输出前 20 部，
# 它们就抓不到完整片单，因此这里按地区分组输出全部条目。
_noscript_items = []
_groups = {}
for r in rows:
    _groups.setdefault((r["region"] or ["其他"])[0], []).append(r)
for _reg, _rs in sorted(_groups.items(), key=lambda kv: -len(kv[1])):
    # 首页不支持 ?region= 参数筛选，此处用纯文本标题，避免坏链与重复 URL
    _noscript_items.append("<li><h3>%s（%d 部）</h3><ul>" % (esc(_reg), len(_rs)))
    for r in _rs:
        _t = esc(r["title"] + ((" (" + r["year"] + ")") if r["year"] else ""))
        _sub = esc(" / ".join(filter(None, [r["year"], r["country"], r["directors"]])))
        _noscript_items.append(
            '<li><a href="movie/%s">%s</a> - %s</li>' % (r["id"], _t, _sub)
        )
    _noscript_items.append("</ul></li>")
# 分类浏览入口（供 AI 爬虫发现分类落地页）
_catgrps = _cat_groups()
for _ck, _clbl in (("genre", "类型"), ("region", "地区"), ("year", "年份")):
    _entries = sorted(_catgrps[_ck].items(), key=lambda kv: -len(kv[1]))
    _parts = []
    for _k, _rs in _entries:
        _parts.append('<a href="%s/%s">%s（%d）</a>' % (_ck, urllib.parse.quote(_k, safe=""), esc(_k), len(_rs)))
    _noscript_items.append('<li style="list-style:none;margin-top:18px"><h3>按%s浏览</h3>'
                            '<div style="line-height:2.2">%s</div></li>' % (_clbl, " · ".join(_parts)))
_noscript_html = "\n".join(_noscript_items)

# ---------- 首页 hero 焦点区 ----------
# 设计要点：
# 1) 静态 HTML，不依赖 JS —— AI 爬虫 / 无 JS 环境都能读到，对 SEO/GEO 有益无害。
# 2) 背景是纯 CSS 渐变，不额外加载任何图片 —— 不影响 LCP、不造成 CLS。
# 3) 标题用 h2（页面 h1 是品牌名），维持标题层级规范。
# 4) 分类链接用 percent 编码且不带 .html，与 sitemap / noscript 保持一致。
_hero_html = ""
_hero_pool = [r for r in rows if r.get("rating")]
try:
    _hero_pool.sort(key=lambda x: -(float(x["rating"] or 0)))
except (ValueError, TypeError):
    _hero_pool = []

# 同一部剧的不同季只取评分最高的一季，避免「编辑精选」里连着出现
# 《瑞克和莫蒂 第一季 / 第二季 / 第三季…」这类重复推荐。
def _hero_base(title):
    # 取「剧名主体」用于去重：截掉「第X季」后缀，以及「：」后面的副标题。
    # 例：「瑞克和莫蒂 第二季」→「瑞克和莫蒂」；「摩登家庭：摩登式告别」→「摩登家庭」
    t = re.sub(r"\s*第[一二三四五六七八九十百\d]+季\s*$", "", title or "")
    t = re.split(r"[：:]", t)[0]
    return t.strip()

_seen_base = set()
_hero_pool2 = []
for r in _hero_pool:
    b = _hero_base(r["title"])
    if b in _seen_base:
        continue
    _seen_base.add(b)
    _hero_pool2.append(r)
_hero_pool = _hero_pool2

if _hero_pool:
    _t = _hero_pool[0]
    _g0 = (_t.get("genres") or [""])[0]
    _sub = " · ".join(filter(None, [
        _t.get("year"),
        _t.get("country") or (_t.get("region") or [""])[0],
        "、".join((_t.get("genres") or [])[:2]),
    ]))
    _side = "".join(
        '<li><a href="movie/%s"><span class="hs-name">%s</span>'
        '<span class="hs-rate">%s</span></a></li>'
        % (r["id"], esc(r["title"]), esc(r["rating"]))
        for r in _hero_pool[1:5]
    )
    _more = ('<a class="hero-btn ghost" href="genre/%s">更多%s</a>'
             % (urllib.parse.quote(_g0, safe=""), esc(_g0))) if _g0 else ""
    _raw_intro = (_t.get("intro") or "").strip()
    _cut = _raw_intro[:130]
    # 超长截断、或源数据本身就是半句话结尾时，都补省略号，避免看起来像渲染出错
    if len(_raw_intro) > 130 or (_cut and _cut[-1] not in "。！？!?…"):
        _cut += "…"
    _hero_intro = esc(_cut)
    _hero_html = (
        '  <section class="hero">\n'
        '    <div class="hero-inner">\n'
        '      <div>\n'
        '        <p class="hero-kicker">编辑精选 · 高分必看</p>\n'
        '        <h2 class="hero-title">%s</h2>\n'
        '        <p class="hero-meta"><b>%s</b> 分 · %s</p>\n'
        '        <p class="hero-desc">%s</p>\n'
        '        <div class="hero-actions">\n'
        '          <a class="hero-btn primary" href="movie/%s">查看详情</a>\n'
        '          %s\n'
        '        </div>\n'
        '      </div>\n'
        '      <ul class="hero-side">\n%s\n      </ul>\n'
        '    </div>\n'
        '  </section>\n'
        % (esc(_t["title"]), esc(_t["rating"]), esc(_sub),
           _hero_intro, _t["id"], _more, _side)
    )

index_html = (INDEX_HTML
    .replace("__TITLE__", SITE_TITLE)
    .replace("__DESC__", SITE_DESC)
    .replace("__SITEURL__", SITE_URL)
    .replace("__VERIFY__", VERIFY_META)
    .replace("__TGURL__", TG_URL)
    .replace("__DATA__", data_json)
    .replace("__JSONLD__", jsonld_json)
    .replace("__NAV__", nav_json)
    .replace("__SITE__", site_json)
    .replace("__NOSCRIPT_LIST__", _noscript_html)
    .replace("__HERO__", _hero_html)
    .replace("__NOSCRIPT_COUNT__", str(len(rows)))
        .replace("__COMMENTS_HOME__", comment_widget("home", "assets/comments.js"))
        .replace("__QKCOUNT__", str(len([r for r in rows if (r.get("qk") or "").strip()])))
        .replace("__EVENTS__", EVENTS_JS)
        .replace("__ANALYTICS__", ANALYTICS)
        .replace("__CSS__", CSS))
with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
    f.write(index_html)

# ---------- 每部片详情页 ----------
def related(r, n=6):
    others = [x for x in rows if x["id"] != r["id"]]
    same_dir = [x for x in others if r["directors"] and x["directors"] == r["directors"]]
    same_gen = [x for x in others
                if x not in same_dir and set(x["genres"]) & set(r["genres"])]
    same_reg = [x for x in others
                if x not in same_dir and x not in same_gen
                and r["region"] and x["region"] and set(x["region"]) & set(r["region"])]
    pool = same_dir + same_gen + same_reg
    if len(pool) < n:  # 仍不足则任意其他片兜底，保证区块恒存在
        extra = [x for x in others if x not in pool]
        pool = pool + extra
    return pool[:n]

def stars_html(s):
    return '<span class="stars">%s</span>' % esc(s)

SITE_BRAND = "影窝片库"
TODAY_ISO = date.today().isoformat()
PUBLISHER = {
    "@type": "Organization",
    "name": SITE_BRAND,
    "url": SITE_URL,
}

def disp_width(s):
    """按 SERP 显示宽度估算：CJK/全角算 2，其余算 1。
    Google 标题约 580px（≈29 个汉字），描述约 920px（≈75 个汉字）。"""
    w = 0
    for ch in s:
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w

def disk_kind(r):
    """该片实际拥有的网盘类型：「夸克网盘」/「百度网盘」/「迅雷网盘」/ 空字符串。

    用于 title / description 动态拼接网盘词，命中「片名 + 夸克网盘」类资源搜索词。
    必须按实际链接生成——写不存在的网盘类型属于虚假承诺，会伤排名。
    """
    if r.get("qk"):
        return "夸克网盘"
    if r.get("bd"):
        return "百度网盘"
    if r.get("xl"):
        return "迅雷网盘"
    return ""

def build_title(r):
    """详情页 <title> / <h1>：片名 (年份) + 网盘类型 + 评分。

    网盘词仅在该片确有对应链接时出现；无网盘链接则退回纯「片名 (年份)」。"""
    head = r["title"] + ((" (" + r["year"] + ")") if r["year"] else "")
    disk = disk_kind(r)
    if disk:
        head += " " + disk
    if r.get("rating"):
        head += " · %s%s" % (rating_source(r), r["rating"])
    return head

def build_desc(r):
    """描述模板：片名（年份） + 网盘资源句 + 类型 + 评分 + 简介。

    资源句刻意放在最前面：原先是「片名是一部XX片，豆瓣评分…+ 整段剧情简介」，
    150 字宽度会被剧情简介吃满，导致「片名 + 夸克网盘」类 query 时
    SERP 摘要里完全没有关键词。现在保证前 30 字内必命中网盘词。"""
    head = r["title"]
    if r["year"]:
        head += "（%s）" % r["year"]
    disk = disk_kind(r)
    if disk:
        head += "%s资源，" % disk
    if r["genres"]:
        head += "%s片，" % "、".join(r["genres"][:2])
    if r.get("rating"):
        head += "%s评分 %s。" % (rating_source(r), r["rating"])
    else:
        head = head.rstrip("，") + "。"
    intro = (r["intro"] or "").strip()
    # 简介若以片名开头，去掉避免与 head 重复
    if intro.startswith(r["title"]):
        intro = intro[len(r["title"]):].lstrip("，,。 ")
    full = head + intro
    if not intro:
        full = head + "本站提供%s资源索引，不提供在线播放。" % (disk or "网盘")
    # 描述过短时补一句站点说明，避免 SERP 摘要信息量不足
    _NOTE = "不提供在线播放，链接失效可进频道反馈补链。"
    if disp_width(full) + disp_width(_NOTE) <= 150 and disp_width(full) < 110:
        full = full.rstrip("。") + "。" + _NOTE
    if disp_width(full) > 150:
        cut = 150 - disp_width(head)
        if cut > 10:
            acc, w = [], 0
            for ch in intro:
                w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
                if w > cut:
                    break
                acc.append(ch)
            full = head + "".join(acc).rstrip("，,、 ") + "…"
        else:
            full = head
    return full

def comments_html(r):
    """豆瓣高赞短评区块。

    只引用少量短评并明确标注来源与作者，既丰富页面内容（利于 SEO / 被 AI 引用），
    也符合引用规范。短评内容版权归豆瓣及原作者所有。
    """
    m = re.search(r"/subject/(\d+)", r.get("douban") or "")
    if not m:
        # 占位条目（如恶搞之家 S1，无真实豆瓣页）：用内部 id 查海外平台评价兜底
        return _external_comments(r.get("id") or "")
    data = COMMENTS.get(m.group(1))
    if not data:
        return _external_comments(m.group(1))
    # 豆瓣返回的 new_score 排序不完全等于点赞数，这里按点赞数重排，
    # 并剔除过短的（<8 字）无信息量短评，保证「高赞」名副其实。
    items = [c for c in data.get("items", [])
             if (c.get("votes") or 0) >= CMT_MIN_VOTES and len(c.get("text") or "") >= 8]
    items.sort(key=lambda c: -(c.get("votes") or 0))
    if len(items) < CMT_MIN_ITEMS:
        return ""
    total = data.get("total", 0)
    sid = m.group(1)
    cmt_url = "https://movie.douban.com/subject/%s/comments" % sid

    lis = []
    for c in items[:6]:
        rate = ""
        if c.get("rating"):
            try:
                rate = '<span class="cmt-rate">%g/5</span>' % float(c["rating"])
            except (TypeError, ValueError):
                rate = ""
        user = c.get("user") or "豆瓣用户"
        lis.append(
            '<li class="cmt">'
            '<blockquote class="cmt-text">%s</blockquote>'
            '<div class="cmt-meta">'
            '<span class="cmt-user">豆瓣用户 %s</span>%s'
            '<span class="cmt-votes">%s 人有用</span>'
            '<span class="cmt-date">%s</span>'
            '</div></li>'
            % (esc(c["text"]), esc(user), rate,
               format(int(c.get("votes") or 0), ","), esc(c.get("date") or ""))
        )
    # 用原生 <details> 折叠：短评正文仍完整存在于 HTML 中（不是 JS 点击后才插入），
    # 因此 Google 与不执行 JS 的 AI 爬虫照样能读到全文，SEO / GEO 不受影响。
    return (
        '<section class="dcmts">'
        '<h2>豆瓣高赞短评</h2>'
        '<details class="cmt-fold">'
        '<summary>评论可能含剧透，点击展开</summary>'
        '<ul class="cmt-list">%s</ul>'
        '</details>'
        '<p class="cmt-src">以上短评来自 <a href="%s" target="_blank" rel="noopener nofollow">豆瓣</a>'
        '，该片共 %s 条短评，此处仅引用获赞最多的 %d 条。</p>'
        '</section>' % ("".join(lis), cmt_url, format(int(total), ","), len(lis))
    )

def _external_comments(sid):
    """豆瓣抓取失败的作品，改用 Letterboxd / IMDb / serializd 等海外平台的高赞评价（已译为中文）。
    同样用原生 <details> 折叠，正文留在 DOM，不影响 SEO / GEO。"""
    ext = EXTERNAL.get(sid)
    if not ext:
        return ""
    items = ext.get("items", [])[:6]
    if not items:
        return ""
    source = ext.get("source", "")
    source_url = ext.get("source_url", "")
    lis = []
    for c in items:
        rate = ('<span class="cmt-rate">%s</span>' % esc(str(c["rating"]))) if c.get("rating") else ""
        user = c.get("user") or source
        votes = c.get("votes")
        vtxt = ('<span class="cmt-votes">%s 人赞</span>' % format(int(votes), ",")) if votes else ""
        date = c.get("date") or ""
        datetxt = ('<span class="cmt-date">%s</span>' % esc(date)) if date else ""
        lis.append(
            '<li class="cmt">'
            '<blockquote class="cmt-text">%s</blockquote>'
            '<div class="cmt-meta">'
            '<span class="cmt-user">%s</span>%s%s%s'
            '</div></li>'
            % (esc(c.get("text") or ""), esc(user), rate, vtxt, datetxt)
        )
    srclink = ('<a href="%s" target="_blank" rel="noopener nofollow">%s</a>'
               % (esc(source_url), esc(source))) if source_url else esc(source)
    # 汉尼拔等海外剧评含大量剧透，折叠尤其必要；正文仍完整留 DOM。
    return (
        '<section class="dcmts">'
        '<h2>%s 高赞评价</h2>'
        '<details class="cmt-fold">'
        '<summary>评论可能含剧透，点击展开</summary>'
        '<ul class="cmt-list">%s</ul>'
        '</details>'
        '<p class="cmt-src">以上评价来自 %s（已译为中文），此处精选最具共鸣的 %d 条。</p>'
        '</section>' % (esc(source), "".join(lis), srclink, len(lis))
    )

def build_detail(r):
    url = page_url(r)
    title = build_title(r)
    desc = build_desc(r)
    mv = {
        "@context": "https://schema.org",
        "@type": "Movie",
        "name": r["title"],
        "url": url,
        "image": poster_abs(r),
        # 新鲜度信号 + 权威来源（E-E-A-T）：原先 321 页全部缺失
        "dateModified": TODAY_ISO,
        "inLanguage": "zh-CN",
        "publisher": dict(PUBLISHER),
    }
    if r.get("country"):
        mv["countryOfOrigin"] = r["country"].split("、")[0]
    if r.get("orig"):
        mv["alternateName"] = r["orig"].split(" / ")[-1]
    if r.get("intro"):
        mv["description"] = r["intro"]
    if r.get("genres"):
        mv["genre"] = r["genres"]
    if r.get("year"):
        mv["datePublished"] = r["year"]
    if r.get("directors"):
        mv["director"] = {"@type": "Person", "name": r["directors"]}
    # aggregateRating：只要有真实评分人数就写（避免富媒体被判无效/造假）
    # ratingValue 优先用评分人数表（Excel 真实数据），CSV 缺评分时回退；两者皆无才跳过
    try:
        _sid = None
        # 用 [^/]+ 而非 \d+：AHS S2/S4 等豆瓣无条目的影片 sid 是占位符（如 ahs_s2），
        # 它们的评分数据来自 IMDb，也放在同一份缓存里，需要能被查到。
        _m = re.search(r"/subject/([^/]+)", r.get("douban") or "")
        if _m:
            _sid = _m.group(1)
        _rc = RATING_COUNT.get(_sid) if _sid else None
        if isinstance(_rc, dict) and _rc.get("votes"):
            _rv = _rc.get("rating")
            if _rv is None:
                _rv = r.get("rating")
            if _rv is not None:
                mv["aggregateRating"] = {
                    "@type": "AggregateRating",
                    "ratingValue": float(_rv),
                    "ratingCount": int(_rc["votes"]),
                    "bestRating": 10,
                }
    except (ValueError, TypeError):
        pass
    mv_json = json.dumps(mv, ensure_ascii=False).replace("</", "<\\/")

    # BreadcrumbList schema
    bc = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "影窝片库", "item": SITE_URL},
            {"@type": "ListItem", "position": 2, "name": r["title"], "item": url},
        ],
    }
    bc_json = json.dumps(bc, ensure_ascii=False).replace("</", "<\\/")

    # FAQPage schema
    disk_name = ("夸克网盘" if r["qk"] else
                 ("百度网盘" if r["bd"] else
                  ("迅雷网盘" if r.get("xl") else "网盘")))
    faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "在哪里可以看%s？" % r["title"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "本站提供%s的%s资源链接，点击详情页的网盘按钮即可跳转下载。本站不提供在线播放。" % (r["title"], disk_name),
                },
            },
            {
                "@type": "Question",
                "name": "%s的%s评分是多少？" % (r["title"], rating_source(r)),
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": ("%s的%s评分为%s。" % (r["title"], rating_source(r), r["rating"])) if r.get("rating") else ("%s暂无评分数据。" % r["title"]),
                },
            },
        ],
    }
    faq_json = json.dumps(faq, ensure_ascii=False).replace("</", "<\\/")

    tags = "".join('<span class="tag">%s</span>' % esc(g) for g in r["genres"])
    rate = ""
    if r.get("rating"):
        rate += '%s <b>%s</b> ' % (esc(rating_source(r)), esc(r["rating"]))
    if r.get("myrating"):
        rate += stars_html(r["myrating"])

    if r["qk"]:
        disk_btn = '<a class="btn btn-quark" href="%s" target="_blank" rel="noopener">夸克网盘</a>' % esc(r["qk"])
    elif r["bd"]:
        disk_btn = '<a class="btn btn-baidu" href="%s" target="_blank" rel="noopener">百度网盘</a>' % esc(r["bd"])
    elif r.get("xl"):
        disk_btn = '<a class="btn btn-xunlei" href="%s" target="_blank" rel="noopener">迅雷网盘</a>' % esc(r["xl"])
    else:
        disk_btn = '<span class="btn btn-baidu off">网盘待补</span>'

    # 资源信息区块：网盘词此前只存在于按钮文字中，正文纯文本几乎全是剧情简介与豆瓣短评，
    # 语义密度过低。这里补一段可见文本，让「片名 + 夸克网盘」类 query 在正文也有匹配。
    _dk = disk_kind(r)
    if _dk:
        resinfo = (
            '<div class="resinfo"><b>《%s》%s资源</b>：本站收录%s的%s链接，'
            '最后更新 %s。本站不提供在线播放，链接失效可进频道反馈补链。</div>'
            % (esc(r["title"]), _dk, esc(r["title"]), _dk, TODAY_ISO)
        )
    else:
        resinfo = (
            '<div class="resinfo"><b>《%s》网盘资源待补</b>：该片暂缺网盘链接，'
            '可进频道反馈，站长会优先补链。</div>' % esc(r["title"])
        )
    douban_btn = ('<a class="btn btn-douban" href="%s" target="_blank" rel="noopener">豆瓣详情</a>'
                  % esc(r["douban"])) if r["douban"] else '<span class="btn btn-douban off">豆瓣</span>'

    rel = related(r)
    rel_html = ""
    if rel:
        cards = []
        for x in rel:
            cards.append(
                '<a class="rel-card" href="../movie/%s">'
                '<img src="%s" alt="%s" loading="lazy" decoding="async">'
                '<div class="rt">%s</div></a>'
                % (x["id"], poster_thumb_detail(x), esc(x["title"]), esc(x["title"]))
            )
        rel_html = '<div class="rel"><h3>相关推荐（同导演 / 同类型）</h3><div class="rel-grid">%s</div></div>' % "".join(cards)

    poster_img = '<img src="%s" alt="%s">' % (esc(poster_webp_detail(r)), esc(r["title"]))
    orig_line = ('<div class="dorig">%s</div>' % esc(r["orig"])) if r["orig"] else ""
    meta_bits = []
    year_country = []
    if r["year"]:    year_country.append("<b>%s</b>" % esc(r["year"]))
    if r["country"]: year_country.append(esc(r["country"]))
    # 地区（region）是筛选用的细分标签，已从「制片国家」第一个派生，
    # 详情元信息里再显示一次会重复（如「日本 · 日本」），故不输出。
    if year_country: meta_bits.append(" · ".join(year_country))
    if r["directors"]: meta_bits.append("导演 <b>%s</b>" % esc(r["directors"]))
    if tags: meta_bits.append("类型 " + tags)
    if r["takedown"]: meta_bits.append('<span style="color:var(--accent2)">已下架</span>')
    meta_html = '<div class="dmeta">%s</div>' % "<br>".join(meta_bits) if meta_bits else ""
    intro_html = ('<div class="dintro">%s</div>' % esc(r["intro"])) if r["intro"] else ""
    rate_html = ('<div class="rate" style="margin-top:12px;font-size:13px;color:var(--muted)">%s</div>' % rate) if rate else ""

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="__DESC__">
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:type" content="video.movie">
<meta property="og:url" content="__URL__">
<meta property="og:image" content="__IMG__">
<link rel="canonical" href="__URL__">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="__TITLE__">
<meta name="twitter:description" content="__DESC__">
<meta name="twitter:image" content="__IMG__">
<title>__TITLE__</title>
<link rel="preconnect" href="__SITEURL__">
<link rel="dns-prefetch" href="__SITEURL__">
<style>__CSS__</style>
<link rel="icon" href="/favicon.ico">
<link rel="icon" type="image/svg+xml" href="/favicon.svg" sizes="any">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
</head>
<body>
<div class="detail">
  <a class="back" href="../">&larr; 返回影窝片单</a>
  <div class="dtop">
    <div class="dposter">__POSTER__</div>
    <div class="dinfo">
      <h1>__TITLE__</h1>
      __ORIG__
      __META__
      __RATE__
      <div class="dupd">最后更新：<time datetime="__TODAY__">__TODAY__</time></div>
      __RESINFO__
      <div class="dacts">
        __DOUBAN__
        __DISK__
        <a class="btn btn-tg" href="__TGURL__" target="_blank" rel="noopener">✈️ 加入频道</a>
      </div>
      <div class="tg-tip">网盘链接失效？<a href="__TGURL__" target="_blank" rel="noopener">进频道反馈</a>，秒补新链；新片上架也会第一时间在频道推送。</div>
    </div>
  </div>
  __INTRO__
  __COMMENTS__
  __REL__
  <footer>
    资源来自网络，仅供个人交流学习，请支持正版。<br>
    本站不提供在线播放；网盘链接由站长持续补全，失效可反馈。<br>
    <a href="__TGURL__" target="_blank" rel="noopener" style="color:#229ed9">✈️ Telegram 频道 · 新片推送 / 链接失效反馈</a>
  </footer>
  __COMMENTS_DETAIL__
</div>
  <script type="application/ld+json">__MV__</script>
  <script type="application/ld+json">__BC__</script>
  <script type="application/ld+json">__FAQ__</script>
__EVENTS__
__ANALYTICS__
</body>
</html>"""
    html = (html
        .replace("__DESC__", esc(desc))
        .replace("__TITLE__", esc(title))
        .replace("__URL__", url)
        .replace("__IMG__", poster_abs(r))
        .replace("__POSTER__", poster_img)
        .replace("__ORIG__", orig_line)
        .replace("__META__", meta_html)
        .replace("__RATE__", rate_html)
        .replace("__TODAY__", TODAY_ISO)
        .replace("__RESINFO__", resinfo)
        .replace("__DOUBAN__", douban_btn)
        .replace("__DISK__", disk_btn)
        .replace("__TGURL__", TG_URL)
        .replace("__INTRO__", intro_html)
        .replace("__COMMENTS__", comments_html(r))
        .replace("__REL__", rel_html)
        .replace("__MV__", mv_json)
        .replace("__BC__", bc_json)
        .replace("__FAQ__", faq_json)
        .replace("__COMMENTS_DETAIL__", comment_widget(r["id"], "../assets/comments.js"))
        .replace("__EVENTS__", EVENTS_JS)
        .replace("__ANALYTICS__", ANALYTICS)
        .replace("__CSS__", CSS))
    return html

_keep = set()
for r in rows:
    html = build_detail(r)
    fn = "%s.html" % r["id"]
    _keep.add(fn)
    with open(os.path.join(OUT, "movie", fn), "w", encoding="utf-8") as f:
        f.write(html)

# 清理陈旧详情页：影片改名 / 换 id 后，旧的 html 会残留，
# 造成重复内容 + 旧外链（如仍指向 yingwo.pages.dev），影响收录。
_dir = os.path.join(OUT, "movie")
_removed = []
for fn in os.listdir(_dir):
    if fn.endswith(".html") and fn not in _keep:
        os.remove(os.path.join(_dir, fn))
        _removed.append(fn)
if _removed:
    print("  - 清理陈旧详情页 %d 个: %s" % (len(_removed), ", ".join(_removed)))

# ---------- 静态页：/about 和 /faq ----------
ABOUT_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="影窝是一个收录国内主流平台暂无正版源的影视与动画的片单站，提供百度网盘和夸克网盘资源索引。">
<meta property="og:title" content="关于影窝">
<meta property="og:description" content="影窝是一个收录国内主流平台暂无正版源的影视与动画的片单站。">
<meta property="og:type" content="website">
<meta property="og:url" content="__SITE_URL__about">
<link rel="canonical" href="__SITE_URL__about">
<link rel="preconnect" href="__SITEURL__">
<title>关于影窝 - 影窝 · 国内看不到的片单</title>
<style>__CSS__</style>
<link rel="icon" href="/favicon.ico">
<link rel="icon" type="image/svg+xml" href="/favicon.svg" sizes="any">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
</head>
<body>
<div class="detail">
  <a class="back" href="/">&larr; 返回影窝片单</a>
  <div class="dinfo">
    <h1>关于影窝</h1>
    <div class="dintro">
      <p>影窝（__SITEURL__）是一个收录国内主流平台暂无正版源的影视与动画的片单站。</p>
      <p>本站的特点：</p>
      <ul>
        <li>精选豆瓣高分影视，侧重国内平台暂无正版引进的作品</li>
        <li>提供百度网盘 / 夸克网盘资源索引，不提供在线播放</li>
        <li>支持按类型、地区、评分、年份筛选</li>
        <li>每部影片附豆瓣评分、导演、制片国家等元数据</li>
      </ul>
      <p>本站所有资源来自网络，仅供个人交流学习，请支持正版。网盘链接由站长持续补全，失效可反馈。</p>
    </div>
  </div>
  <footer>资源来自网络，仅供个人交流学习，请支持正版。</footer>
</div>
<script type="application/ld+json">__WEBPAGE__</script>
</body>
</html>"""

about_page = (ABOUT_HTML
    .replace("__SITE_URL__", SITE_URL)
    .replace("__CSS__", CSS)
    .replace("__WEBPAGE__", json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "关于影窝",
        "url": SITE_URL + "about",
        "description": "影窝是一个收录国内主流平台暂无正版源的影视与动画的片单站。",
        "isPartOf": {"@type": "WebSite", "name": "影窝", "url": SITE_URL},
    }, ensure_ascii=False).replace("</", "<\\/")))
with open(os.path.join(OUT, "about.html"), "w", encoding="utf-8") as f:
    f.write(about_page)

FAQ_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow">
<meta name="description" content="影窝常见问题：网盘资源怎么下载？链接失效怎么办？影片能在线看吗？">
<meta property="og:title" content="影窝常见问题">
<meta property="og:description" content="影窝常见问题解答：网盘资源、下载方式、链接失效等。">
<meta property="og:type" content="website">
<meta property="og:url" content="__SITE_URL__faq">
<link rel="canonical" href="__SITE_URL__faq">
<link rel="preconnect" href="__SITEURL__">
<title>常见问题 - 影窝 · 国内看不到的片单</title>
<style>__CSS__</style>
<link rel="icon" href="/favicon.ico">
<link rel="icon" type="image/svg+xml" href="/favicon.svg" sizes="any">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
</head>
<body>
<div class="detail">
  <a class="back" href="/">&larr; 返回影窝片单</a>
  <div class="dinfo">
    <h1>常见问题</h1>
    <div class="dintro">
      <h2>网盘资源怎么下载？</h2>
      <p>在影片详情页点击"夸克网盘""百度网盘"或"迅雷网盘"按钮即可跳转到网盘下载页面，迅雷链接的提取码标注在按钮旁。首页卡片下方也有网盘按钮，可直接点击下载。</p>
      <h2>链接失效了怎么办？</h2>
      <p>网盘链接可能因各种原因失效。如果遇到失效链接，可以在影片详情页的评论区留言反馈，站长会尽快补上。</p>
      <h2>影片能在线看吗？</h2>
      <p>本站不提供在线播放，仅提供资源索引和网盘下载链接。请下载后使用本地播放器观看。</p>
      <h2>影片是怎么筛选的？</h2>
      <p>本站侧重收录豆瓣高分影视作品，特别是国内主流平台暂无正版引进的作品。每部影片附有豆瓣评分、导演、类型、制片国家等元数据，方便筛选。</p>
      <h2>资源是正版的吗？</h2>
      <p>本站所有资源来自网络，仅供个人交流学习，请支持正版。如需观看正版，请前往各正版流媒体平台。</p>
    </div>
  </div>
  <footer>资源来自网络，仅供个人交流学习，请支持正版。</footer>
</div>
<script type="application/ld+json">__FAQ_SCHEMA__</script>
</body>
</html>"""

faq_schema = json.dumps({
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
        {"@type": "Question", "name": "网盘资源怎么下载？", "acceptedAnswer": {"@type": "Answer", "text": "在影片详情页点击夸克网盘、百度网盘或迅雷网盘按钮即可跳转到网盘下载页面，迅雷链接的提取码标注在按钮旁。首页卡片下方也有网盘按钮，可直接点击下载。"}},
        {"@type": "Question", "name": "链接失效了怎么办？", "acceptedAnswer": {"@type": "Answer", "text": "网盘链接可能因各种原因失效。如果遇到失效链接，可以在影片详情页的评论区留言反馈，站长会尽快补上。"}},
        {"@type": "Question", "name": "影片能在线看吗？", "acceptedAnswer": {"@type": "Answer", "text": "本站不提供在线播放，仅提供资源索引和网盘下载链接。请下载后使用本地播放器观看。"}},
        {"@type": "Question", "name": "影片是怎么筛选的？", "acceptedAnswer": {"@type": "Answer", "text": "本站侧重收录豆瓣高分影视作品，特别是国内主流平台暂无正版引进的作品。每部影片附有豆瓣评分、导演、类型、制片国家等元数据。"}},
        {"@type": "Question", "name": "资源是正版的吗？", "acceptedAnswer": {"@type": "Answer", "text": "本站所有资源来自网络，仅供个人交流学习，请支持正版。如需观看正版，请前往各正版流媒体平台。"}},
    ],
}, ensure_ascii=False).replace("</", "<\\/")

faq_page = (FAQ_HTML
    .replace("__SITE_URL__", SITE_URL)
    .replace("__CSS__", CSS)
    .replace("__FAQ_SCHEMA__", faq_schema))
with open(os.path.join(OUT, "faq.html"), "w", encoding="utf-8") as f:
    f.write(faq_page)

print("  - about.html + faq.html（静态页）")

# ---------- 404.html ----------
# Cloudflare Pages 对不存在的路径默认回退到首页并返回 200（软 404），
# 会被搜索引擎判为重复内容 / Soft 404。提供 404.html 后会返回真正的 404 状态码。
NOTFOUND_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, follow">
<title>页面不存在 - %s</title>
<meta name="description" content="页面不存在，返回%s浏览全部片单。">
<style>%s</style>
</head>
<body>
<div class="wrap">
  <h1>404 · 页面不存在</h1>
  <p>这个地址没有对应的影片，可能是链接已变更或影片已下架。</p>
  <p><a class="btn" href="%s">← 返回片库首页</a></p>
  <p class="muted">也可以到 <a href="%s" target="_blank" rel="noopener">Telegram 频道</a> 反馈失效链接。</p>
</div>
</body>
</html>""" % (SITE_BRAND, SITE_BRAND, CSS, SITE_URL, TG_URL)
with open(os.path.join(OUT, "404.html"), "w", encoding="utf-8") as f:
    f.write(NOTFOUND_HTML)
print("  - 404.html（避免软 404）")

# ---------- 静态分类落地页（类型 / 地区 / 年份）：SEO 长尾词 + GEO 可引用页面 ----------
cat_urls = []
_catgrps = _cat_groups()
for _ck in ("genre", "region", "year"):
    _d = os.path.join(OUT, _ck)
    os.makedirs(_d, exist_ok=True)
    for _k, _rs in _catgrps[_ck].items():
        _html = build_category(_ck, _k, _rs)
        _slug = urllib.parse.quote(_k, safe="")
        # 文件名用原始中文（Cloudflare 收到编码 URL 会解码后匹配）；URL/sitemap 用 _slug 编码
        with open(os.path.join(_d, "%s.html" % _k), "w", encoding="utf-8") as _f:
            _f.write(_html)
        cat_urls.append(SITE_URL + _ck + "/" + _slug)
print("  - 分类落地页 genre/region/year 共 %d 个" % len(cat_urls))

# ---------- 网盘类型聚合页：承接「夸克网盘 影视资源」泛词 ----------
# 只在片数足够时建页，避免生成内容过薄的落地页被判低质量。
pan_urls = []
_qk_rows = [r for r in rows if (r.get("qk") or "").strip()]
if len(_qk_rows) >= 50:
    _pd = os.path.join(OUT, "pan")
    os.makedirs(_pd, exist_ok=True)
    with open(os.path.join(_pd, "quark.html"), "w", encoding="utf-8") as _f:
        _f.write(build_category("pan", "quark", _qk_rows))
    pan_urls.append(SITE_URL + "pan/quark")
    print("  - 网盘聚合页 pan/quark（%d 部）" % len(_qk_rows))

# ---------- sitemap（首页 + 详情页 + 分类页） ----------
today = date.today().isoformat()
urls = ['  <url>\n    <loc>%s</loc>\n    <lastmod>%s</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>1.0</priority>\n  </url>' % (SITE_URL, today)]
urls.append('  <url>\n    <loc>%sabout</loc>\n    <lastmod>%s</lastmod>\n    <changefreq>monthly</changefreq>\n    <priority>0.5</priority>\n  </url>' % (SITE_URL, today))
urls.append('  <url>\n    <loc>%sfaq</loc>\n    <lastmod>%s</lastmod>\n    <changefreq>monthly</changefreq>\n    <priority>0.5</priority>\n  </url>' % (SITE_URL, today))
for r in rows:
    urls.append('  <url>\n    <loc>%s</loc>\n    <lastmod>%s</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>' % (page_url(r), today))
for _u in cat_urls:
    urls.append('  <url>\n    <loc>%s</loc>\n    <lastmod>%s</lastmod>\n    <changefreq>monthly</changefreq>\n    <priority>0.6</priority>\n  </url>' % (_u, today))
for _u in pan_urls:
    urls.append('  <url>\n    <loc>%s</loc>\n    <lastmod>%s</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.7</priority>\n  </url>' % (_u, today))
sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>\n")
with open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8") as f:
    f.write(sitemap)

# ---------- llms.txt / llms-full.txt（面向 AI 爬虫，GEO） ----------
# AI 爬虫（GPTBot / ClaudeBot / PerplexityBot 等）一般不执行 JS，
# 首页是 JS 渲染的网格，它们抓不到片单。llms.txt 提供纯文本全量索引，
# 是让 AI 搜索/问答能引用本站内容的关键入口。
def _line(r):
    bits = [r["title"] + ((" (%s)" % r["year"]) if r["year"] else "")]
    sub = []
    if r["genres"]:
        sub.append("、".join(r["genres"][:3]))
    if r["directors"]:
        sub.append(r["directors"].split("、")[0])
    if r["rating"]:
        sub.append("豆瓣 %s" % r["rating"])
    bits.append(" - " + " / ".join(sub) if sub else "")
    return "- [%s](%s)%s" % (bits[0], page_url(r), bits[1])

_groups = {}
for r in rows:
    _groups.setdefault((r["region"] or ["其他"])[0], []).append(r)
_reg_order = sorted(_groups.items(), key=lambda kv: -len(kv[1]))

llms = ["# %s" % SITE_BRAND, "",
        "> %s" % SITE_DESC, "",
        "%s 是一个专注于收录「国内主流平台不易看到的优质影视作品」的"
        "纯静态索引站，共收录 %d 部影片。" % (SITE_BRAND, len(rows)),
        "每部条目包含豆瓣评分、类型、制片国家/地区、导演、剧情简介，"
        "以及夸克网盘 / 百度网盘 / 迅雷网盘的下载索引。",
        "",
        "## 站点定位与权威性", "",
        "- **内容来源**：影片元数据（评分/类型/导演/简介）来自豆瓣电影公开页面，"
        "高赞短评来自豆瓣短评页（已标注来源与作者），"
        "部分豆瓣已下架的作品补充了 Letterboxd / IMDb / serializd 的海外高赞评价（已译中文）。",
        "- **更新频率**：每周新增 5-15 部，网盘链接失效会及时更换。",
        "- **索引性质**：本站只做资源索引与信息聚合，**不提供在线播放、不存储任何影视文件**，"
        "下载需通过第三方网盘链接进行。",
        "- **收录标准**：豆瓣评分 7.0 以上或具有较高讨论度的影视剧，"
        "优先收录国内流媒体平台未引进或已下架的作品。",
        "",
        "## 常见问答（AI 可直接引用）", "",
        "- **Q: 这个网站是做什么的？** A: 影窝片库是一个影视资源索引站，"
        "收录国内主流平台不易看到的优质影视剧，提供网盘下载索引（不提供在线播放）。",
        "- **Q: 怎么下载影片？** A: 在影片详情页点击夸克网盘或百度网盘按钮，"
        "跳转到网盘页面下载。百度网盘链接可能需要提取码（详情页已标注）。",
        "- **Q: 链接失效了怎么办？** A: 可在 Telegram 频道 %s 反馈，会及时更换。" % TG_URL,
        "- **Q: 评分数据来自哪里？** A: 来自豆瓣电影。评分人数来自豆瓣公开页面。",
        "- **Q: 支持哪些类型/地区？** A: 覆盖剧情、悬疑、科幻、动画等类型，"
        "以及美国、日本、中国大陆、中国香港、韩国、英国等地区，"
        "可在首页按类型/地区/年份筛选，或访问下方分类落地页。",
        "- **Q: 网站提供在线播放吗？** A: 不提供。本站只做资源索引，"
        "需通过网盘链接下载后观看。",
        "",
        "## 站点页面", "",
        "- [首页片库](%s)：可按类型 / 地区 / 评分 / 年份筛选" % SITE_URL,
        "- [关于本站](%sabout)：站点定位与资源说明" % SITE_URL,
        "- [常见问题](%sfaq)：下载方式、链接失效等问题" % SITE_URL,
        "- [sitemap](%ssitemap.xml)" % SITE_URL,
        "",
        "## 分类落地页", "",
        "- 类型页（如「动画」「悬疑」「科幻」）：%sgenre/动画.html 等" % SITE_URL,
        "- 地区页（如「美国」「日本」「中国大陆」）：%sregion/美国.html 等" % SITE_URL,
        "- 年份页（如「2024」「2019」）：%syear/2024.html 等" % SITE_URL,
        "- 网盘类型页：%span/quark（夸克网盘资源，共 %d 部）" % (SITE_URL, len(_qk_rows)),
        "", "## 按地区浏览", ""]
for _reg, _rs in _reg_order:
    llms.append("- %s（%d 部）" % (_reg, len(_rs)))
llms += ["", "## 全部片单（按地区分组）", ""]
for _reg, _rs in _reg_order:
    llms.append("### %s" % _reg)
    llms += [_line(r) for r in sorted(_rs, key=lambda x: -(float(x["rating"] or 0)))]
    llms.append("")
with open(os.path.join(OUT, "llms.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(llms))

# llms-full.txt：含简介 + 高赞短评的完整版
llmsf = list(llms[:llms.index("## 全部片单（按地区分组）")])
llmsf += ["", "## 全部片单（含简介与豆瓣高赞短评）", ""]
for _reg, _rs in _reg_order:
    llmsf.append("### %s" % _reg)
    for r in sorted(_rs, key=lambda x: -(float(x["rating"] or 0))):
        llmsf.append(_line(r))
        intro = (r["intro"] or "").strip()
        if intro:
            llmsf.append("  简介：%s" % intro[:110])
        # 附 2 条高赞评价，让 AI 能引用到真实观众观点（需标注来源）
        _m = re.search(r"/subject/(\d+)", r.get("douban") or "")
        _d = COMMENTS.get(_m.group(1)) if _m else None
        if _d:
            _cs = sorted(
                [c for c in _d.get("items", [])
                 if (c.get("votes") or 0) >= CMT_MIN_VOTES and len(c.get("text") or "") >= 8],
                key=lambda c: -(c.get("votes") or 0))[:2]
            for _c in _cs:
                llmsf.append('  豆瓣用户「%s」短评（%s 人有用）：%s'
                             % (_c.get("user") or "匿名",
                                _c.get("votes") or 0, _c["text"][:120]))
        else:
            # 豆瓣抓取失败的作品，用外部高赞评价（已译为中文）补充
            _ext = EXTERNAL.get(_m.group(1)) if _m else None
            if _ext:
                _src = _ext.get("source", "海外观众")
                for _c in _ext.get("items", [])[:2]:
                    llmsf.append('  %s 用户「%s」评价（已译中文）：%s'
                                 % (_src, _c.get("user") or "匿名", (_c.get("text") or "")[:120]))
    llmsf.append("")
with open(os.path.join(OUT, "llms-full.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(llmsf))

with open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8") as f:
    f.write("""User-agent: *
Allow: /
Sitemap: %s

# 允许主流 AI 爬虫引用内容（Geo 友好）
User-agent: GPTBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: Claude-Web
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: CCBot
Allow: /

User-agent: Applebot-Extended
Allow: /
""" % (SITE_URL + "sitemap.xml"))

# Cloudflare Pages 缓存头：静态资源（海报/缩略图/js/css）缓存 1 年；
# HTML（详情页/列表/首页）设 max-age=0 + must-revalidate，每次回源验证，
# 这样删除某部片后能立即从站点消失，不留边缘缓存（降合规风险）。
with open(os.path.join(OUT, "_headers"), "w", encoding="utf-8") as f:
    f.write(
        "/assets/*\n"
        "  Cache-Control: public, max-age=31536000, immutable\n\n"
        "/movie/*\n"
        "  Cache-Control: public, max-age=0, must-revalidate\n\n"
        "/genre/*\n"
        "  Cache-Control: public, max-age=0, must-revalidate\n\n"
        "/region/*\n"
        "  Cache-Control: public, max-age=0, must-revalidate\n\n"
        "/year/*\n"
        "  Cache-Control: public, max-age=0, must-revalidate\n\n"
        "/pan/*\n"
        "  Cache-Control: public, max-age=0, must-revalidate\n\n"
        "/\n"
        "  Cache-Control: public, max-age=0, must-revalidate\n"
    )

# 复制评论区前端脚本到 assets（供详情页与首页引用）
_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "comments.js")
_dst = os.path.join(OUT, "assets", "comments.js")
if os.path.exists(_src):
    shutil.copyfile(_src, _dst)
    print("  - assets/comments.js（评论区前端）")

# 复制站点图标到站点根目录（供所有页面 /favicon.* 引用）
for _f in ("favicon.ico", "favicon.svg", "apple-touch-icon.png"):
    _src = os.path.join(os.path.dirname(os.path.abspath(__file__)), _f)
    _dst = os.path.join(OUT, _f)
    if os.path.exists(_src):
        shutil.copyfile(_src, _dst)
        print("  - %s（站点图标）" % _f)

print("OK 生成 %d 部（已剔除无链接项）" % len(rows))
print("  - index.html + style.css（流媒体暗色网格首页）")
print("  - movie/ 下 %d 个详情页" % len(rows))
print("  - sitemap.xml 共 %d 个 URL" % len(urls))
print("地区分布:", dict(region_counts))
