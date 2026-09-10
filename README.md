# 影窝 · 影视片单静态站生成器

一个**零框架、零后端**的纯静态影视资源索引站生成器。给定一份 CSV 片单，脚本会产出：

- 流媒体暗色风格的首页（卡片网格 + 搜索 / 筛选 / 排序 + 悬停看简介）
- 每部影片独立的详情页（独立 `<title>` / `description` / JSON-LD `Movie` 结构化数据 + 站内互链）
- `sitemap.xml`、`robots.txt`、`llms.txt` / `llms-full.txt`（便于 SEO 与 AI 搜索引擎收录）
- 分类落地页（按类型 / 地区 / 年份）、`about.html`、`faq.html`、`404.html`

本仓库**只开源代码与工具链**，示例数据使用占位链接；你自己的片单（含网盘链接）放在本地、不进仓库。

> ⚠️ 内容说明：本站仅做「资源索引」，不托管、不提供在线播放。所有链接来自网络，仅供个人交流学习，请支持正版。仓库本身不含任何受版权保护的内容。

---

## 快速开始

```bash
# 1. 准备 Python 环境（需 Python 3.10+）
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. 准备你的片单
#    复制示例，改名后填入你自己的数据：
cp data/example_movie_master.csv data/movie_master.csv
#    （用记事本 / Excel 打开编辑，详见下方「数据格式」）

# 3. 把海报放到 assets/posters/，命名：<豆瓣 subject id>.webp
#    例如 assets/posters/1292052.webp（无海报也能生成，只是图片位置留空）

# 4. 生成站点
python gen_site.py
#   产物在 site/ 目录

# 5. 本地预览
cd site && python -m http.server 8080
#   浏览器打开 http://localhost:8080
```

生成时可用环境变量覆盖默认配置：

| 变量 | 说明 | 默认 |
|---|---|---|
| `MOVIE_SRC` | 片单 CSV 路径 | `data/movie_master.csv` |
| `MOVIE_OUT` | 产物输出目录 | `site/` |
| `SITE_TITLE` | 站点标题 | `影窝 · 国内看不到的片单（示例）` |
| `SITE_DESC` | 站点描述（用于 SEO） | 见源码 |
| `SITE_URL` | 你的站点域名（带结尾 `/`） | `https://your-domain.example/` |
| `GSC_CODE` | Google Search Console 验证码（留空则不输出） | 空 |
| `BING_CODE` | Bing Webmaster 验证码 | 空 |
| `TG_URL` | Telegram 频道链接（留空则不显示） | `https://t.me/your_channel` |
| `CF_ANALYTICS` | Cloudflare Web Analytics 片段（留空则不加统计） | 空 |

示例：

```bash
SITE_URL="https://your-site.pages.dev/" SITE_TITLE="我的片单" python gen_site.py
```

---

## 数据格式

CSV **第一行是表头**，共 18 列（顺序固定）：

| # | 列名 | 说明 |
|---|---|---|
| 1 | 片名 | 展示用中文名 |
| 2 | 完整原名 | 原文名（可含英文/日文等） |
| 3 | 年份 | 数字，如 `2023` |
| 4 | 类型 | 用 `、` 分隔，如 `剧情、犯罪` |
| 5 | 制片国家 | 如 `美国` |
| 6 | 地区 | 分类用，如 `欧美` / `日本` |
| 7 | 导演 | 可多个，用 `、` 分隔 |
| 8 | 我的评分 | 没打分填 `—` |
| 9 | 豆瓣评分 | 如 `9.4` |
| 10 | 是否下架 | `否` / `是` |
| 11 | 豆瓣链接 | `https://movie.douban.com/subject/<id>/` |
| 12 | 海报 | 路径，如 `assets/posters/1292052.webp` |
| 13 | 百度网盘链接 | 留空表示无 |
| 14 | 百度提取码 | 与 13 对应 |
| 15 | 夸克网盘链接 | 留空表示无 |
| 16 | 简介 | 影片简介（详情页展示） |
| 17 | 迅雷网盘链接 | 留空表示无；带 `?pwd=` 时提取码内嵌，无需填 18 列 |
| 18 | 迅雷提取码 | 链接含 `?pwd=` 时留空即可 |

> 至少要有「百度 / 夸克 / 迅雷」三者之一，否则该行会被跳过（不会生成页面）。

---

## 目录结构

```
movie-list-site/
├── gen_site.py              # 核心生成器
├── comments.js              # 详情页评论区前端脚本
├── requirements.txt
├── README.md
├── LICENSE
├── .gitignore
├── data/
│   └── example_movie_master.csv   # 示例片单（4 行，占位链接）
├── assets/
│   └── posters/             # 你的海报（.gitignore 不追踪）
└── douban_export/          # 数据维护工具链
    ├── add_single.py        # 单部入库（自动抓豆瓣元数据）
    ├── add_batch.py         # 批量入库
    ├── fetch_comments.py    # 抓取豆瓣短评缓存
    ├── _check_sids.py       # 入库前校验 sid + 查重
    ├── _fix_intro.py        # 补/改简介
    └── push_tg.py           # 推送文案到 Telegram 频道（需 --token）
```

### 工具链说明

`douban_export/` 下是日常维护用的小工具，大多依赖联网抓取豆瓣：

- `add_single.py <豆瓣sid> [夸克链接] [--baidu 链接 --pwd 码] [--xunlei 链接 --xpwd 码]`：补一部片子。
- `_check_sids.py <sid,...>`：校验 sid、打印元数据并查重（**命中在库时不要自动覆盖**）。
- `fetch_comments.py --sids <sid,...>`：抓取高赞短评到 `data/comments_cache.json`。
- `push_tg.py --token <BOT_TOKEN> --chat <频道> --file 文案.md`：把文案发到 Telegram。

> 这些工具不在本仓库存放任何豆瓣 Cookie 或 Telegram Token；如需使用，请自行配置网络与凭证。

---

## 部署到 Cloudflare Pages

**方式一：本地部署（推荐，最简单）**

```bash
# 需要 Node.js + wrangler
npm install -g wrangler
wrangler pages deploy site --project-name <你的项目名> --branch main
# 按提示登录 Cloudflare 即可
```

**方式二：连接 Git 自动部署**

在 Cloudflare Pages 控制台「Connect to Git」绑定本仓库，构建设置：

- Build command：`python gen_site.py`
- Build output directory：`site`
- 环境变量：`MOVIE_SRC=data/movie_master.csv`（其余可选）

---

## 许可证

[MIT](LICENSE) — 欢迎 Fork、改动、自用或二次发布。
