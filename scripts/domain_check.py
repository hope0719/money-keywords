#!/usr/bin/env python3
"""押注时查候选域名。不花钱，不登录，只读公开信息。

用法：
  python3 domain_check.py wallpapersizes.com fitmywallpaper.com ...
  python3 domain_check.py --file 候选域名.txt        # 一行一个

对每个候选域名查四样：
  1. 有没有人注册：先 rdap.org，查不到用电脑自带的 whois 命令（和 whois_date.py 同一套）。
  2. 这个后缀的普通价：注册商 Porkbun 公开的价格表，首年和续费各多少美元。
     这是后缀的普通价，不是这个域名的实际价。溢价域名要到注册商的搜索页上看，见 SKILL.md 第 9 步。
  3. 以前有没有人用过：archive.org 的网页存档，最早和最晚各是哪个月、一共多少个月有存档，
     以及最后一次正常存档的网址。有存档说明这个域名以前被人注册过、后来放弃了。
     当年是什么站，要用浏览器打开那个网址看；存档站会挡掉脚本直接取页面。
  4. 同名的别的后缀：.com .net .org .io .app .ai .co 各是哪天注册的。

最后打印一张汇总表，可以直接贴进押注里。
哪一项「没查成」就照实写没查成，不当成通过。
"""
import concurrent.futures
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.dont_write_bytecode = True  # 不在 skill 目录里留缓存文件
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from whois_date import rdap, whois  # noqa: E402

SIBLING_TLDS = ["com", "net", "org", "io", "app", "ai", "co"]
UA = {"User-Agent": "Mozilla/5.0"}


def get(url, timeout=30, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout).read()


def registered(domain):
    result, _ = rdap(domain)
    if not result:
        result, _ = whois(domain)
    time.sleep(0.6)
    return result or "没查到"


_prices = None


def tld_price(tld):
    global _prices
    if _prices is None:
        try:
            raw = get("https://api.porkbun.com/api/json/v3/pricing/get", data=b"{}",
                      headers={"Content-Type": "application/json"})
            _prices = json.loads(raw).get("pricing", {})
        except Exception:
            _prices = {}
    p = _prices.get(tld)
    if not p:
        return "没查成"
    return f"首年 {p.get('registration')}，续费 {p.get('renewal')} 美元"


def archive_history(domain):
    """返回（一句话，最后一次正常存档的网址）。"""
    url = ("https://web.archive.org/cdx/search/cdx?url=" + domain +
           "&output=json&fl=timestamp,statuscode,mimetype,original&collapse=timestamp:6&limit=800")
    rows = None
    for _ in range(2):
        try:
            rows = json.loads(get(url, timeout=40).decode("utf-8", "replace") or "[]")[1:]
            break
        except Exception:
            time.sleep(3)
    if rows is None:
        return "没查成", ""
    if not rows:
        return "没有存档", ""
    first, last = rows[0][0], rows[-1][0]
    line = f"有 {len(rows)} 个月的存档，最早 {first[:4]}-{first[4:6]}，最晚 {last[:4]}-{last[4:6]}"
    title = ""
    good = [r for r in rows if r[1] == "200" and "html" in (r[2] or "")]
    if good:
        ts, _, _, original = good[-1]
        # 存档站会挡掉脚本直接取页面，所以只给出网址，由人或浏览器打开看当年是什么站
        title = f"最后一次正常存档 {ts[:4]}-{ts[4:6]}，打开看当年是什么站：https://web.archive.org/web/{ts}/{original}"
    return line, title


def main():
    args = sys.argv[1:]
    if args[:1] == ["--file"] and len(args) > 1:
        domains = [l.strip() for l in open(args[1], encoding="utf-8") if l.strip() and not l.startswith("#")]
    else:
        domains = args
    if not domains:
        sys.exit(__doc__)
    summary = []
    for d in domains:
        d = d.lower().replace("https://", "").replace("http://", "").split("/")[0]
        if d.startswith("www."):
            d = d[4:]
        name, tld = d.rsplit(".", 1)
        print(f"\n## {d}", flush=True)
        reg = registered(d)
        print(f"有没有人注册：{reg}", flush=True)
        price = tld_price(tld)
        print(f".{tld} 的普通价：{price}", flush=True)
        # 存档和几个同名后缀一起查，不一个一个等。最多同时 4 个，免得被登记信息的网站限住
        others = [t for t in SIBLING_TLDS if t != tld]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            f_hist = pool.submit(archive_history, d)
            f_sib = [pool.submit(registered, f"{name}.{t}") for t in others]
            hist, title = f_hist.result()
            sib_res = [f.result() for f in f_sib]
        print(f"以前有没有人用过：{hist}" + (f"；{title}" if title else ""), flush=True)
        sib = [f".{t} {r}" for t, r in zip(others, sib_res) if r not in ("没人注册", "没查到")]
        sib_line = "；".join(sib) if sib else "都没人注册"
        print(f"同名的别的后缀：{sib_line}", flush=True)
        summary.append((d, reg, price, hist + (f"；{title}" if title else ""), sib_line))
    print("\n| 域名 | 有没有人注册 | 这个后缀的普通价 | 以前有没有人用过 | 同名的别的后缀 |")
    print("|---|---|---|---|---|")
    for row in summary:
        print("| `" + row[0] + "` | " + " | ".join(row[1:]) + " |")


if __name__ == "__main__":
    main()
