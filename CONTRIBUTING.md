# 贡献指南

感谢你对「影窝 · 影视片单静态站生成器」感兴趣！欢迎提 Issue、给建议、提交功能 PR。

## 提 Issue

- **bug 反馈**请附上：操作系统、Python 版本、完整报错信息、复现步骤。
- **功能建议**请说明使用场景和期望效果。

## 提交代码（PR）

1. Fork 本仓库到你的账号。
2. 从 `main` 切一个分支：`git checkout -b fix/xxx` 或 `feat/xxx`。
3. 本地验证：`pip install -r requirements.txt` 后 `python gen_site.py` 能正常产出 `site/`。
4. 提交并推送，向 `main` 发起 Pull Request，描述清楚改动。

## ⚠️ 红线（务必遵守）

- **不要提交任何真实网盘链接 / 片单数据**。仓库只接受占位数据（`data/example_movie_master.csv`）。
  真实数据请通过 GitHub Actions 的 `MOVIE_CSV_B64` Secret 注入（见 README「自动部署」章节），不要进 git。
- **不要提交任何密钥**：Cloudflare Token、Bing API Key、Telegram Bot Token、豆瓣 Cookie 等一律不进仓库。
- 海报图片不进仓库（`assets/posters/` 已被 `.gitignore` 忽略）。

## 代码风格

- Python 保持简洁，函数单一职责，关键逻辑加注释。
- `gen_site.py` 内联了核心 CSS——改样式请改这里，不要改 `site/` 产物。
- 改动尽量小而聚焦，一个 PR 解决一件事。

## 本地联调工具链

`douban_export/` 下的脚本依赖联网抓取豆瓣，需要你自备 Cookie / 代理；它们不进任何凭证，请自行配置环境。
