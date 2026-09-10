#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞出个未来 / 影窝站 电报频道逐条文案推送脚本（t.me/your_channel）

前置（一次性）：
  1. Telegram 找 @BotFather，/newbot 拿到 token（形如 123456789:AAE...）
  2. 把该 bot 加为 @your_channel 频道管理员（否则无发帖权限）

用法:
  python push_tg.py --token <BOT_TOKEN> [--chat @your_channel] [--file 文案.md] [--mode test|rest|all]

- 文案.md 由 gen_tg_post.py 逐条产出后汇编而成，按单个圈码行（③ ④ … ⑯）分隔成多条
- 纯文本 sendMessage（不用 parse_mode，避免夸克链接里的下划线 _ 被当斜体）
- --mode:
    test  只发第一条（③），先验证排版/链接
    rest  发「除第一条外」的剩余条目（配合 test 用，避免重复）
    all   发全部（含第一条）
- 每条间隔 1.5s 防刷屏
- 走环境变量 HTTPS_PROXY 代理（本沙箱出网必须带）
"""
import os, sys, json, time, argparse, urllib.request, urllib.error

CIRCLED = set(chr(c) for c in list(range(0x2460, 0x2474)) + list(range(0x2474, 0x2488)))  # ①–⒇

def parse_entries(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    entries, cur, buf = [], None, []
    for ln in lines:
        s = ln.strip()
        if len(s) == 1 and s in CIRCLED:
            if cur is not None:
                entries.append((cur, "\n".join(buf).strip()))
            cur, buf = s, []
        elif cur is not None:
            buf.append(ln.rstrip())
    if cur is not None:
        entries.append((cur, "\n".join(buf).strip()))
    return entries

def send(token, chat, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    })
    r = urllib.request.urlopen(req, timeout=30)
    return json.loads(r.read().decode("utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True, help="BotFather 给的 bot token")
    ap.add_argument("--chat", default="@your_channel", help="频道 @username 或 chat_id")
    ap.add_argument("--file", default="telegram_posts.md", help="汇编好的文案 markdown")
    ap.add_argument("--mode", default="test", choices=["test", "rest", "all"])
    args = ap.parse_args()

    if not os.path.exists(args.file):
        print("找不到文案文件:", args.file); sys.exit(1)
    entries = parse_entries(args.file)
    print(f"解析到 {len(entries)} 条文案（来自 {args.file}）")

    if args.mode == "test":
        targets = entries[:1]
    elif args.mode == "rest":
        targets = entries[1:]
    else:
        targets = entries

    ok = 0
    for num, text in targets:
        try:
            res = send(args.token, args.chat, text)
            if res.get("ok"):
                ok += 1
                print(f"✅ {num} 发送成功 (msg_id={res['result']['message_id']})")
            else:
                print(f"❌ {num} 失败: {res}")
        except urllib.error.HTTPError as e:
            print(f"❌ {num} HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}")
        except Exception as e:
            print(f"❌ {num} 异常: {type(e).__name__} {e}")
        if args.mode in ("rest", "all") and num != targets[-1][0]:
            time.sleep(1.5)

    print(f"\n完成：成功 {ok}/{len(targets)}")

if __name__ == "__main__":
    main()
