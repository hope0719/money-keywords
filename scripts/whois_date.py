#!/usr/bin/env python3
"""查域名哪天注册的。不花钱，只读公开登记信息。

用法：
  python3 whois_date.py 域名1 域名2 ...
  python3 whois_date.py --file 域名表.txt        # 一行一个域名

输出每个域名一行：域名<TAB>注册日期，或「没人注册」「没查到」<TAB>从哪查到的

做法：先查 rdap.org，查不到用电脑自带的 whois 命令。一个一个查，每次隔 0.6 秒。
两处容易读错的地方已经处理：
  1. rdap.org 对 .io、.im、.co 这些后缀回 404，不等于没人注册，会再用 whois 查；
     只有 .com、.net、.org、.app、.dev 回 404 才当成没人注册。
  2. whois 输出最前面那段是后缀自己的登记信息，里面的 created 是后缀哪天设立的，
     不是域名的注册日期，读之前先去掉。
「没查到」的不要当成新站，也不要当成没人注册。
要给注册的主域名：`tools.example.com` 这样的子域名，给 `example.com`。开头的 www. 会自动去掉。
"""
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

RDAP_404_IS_FREE = {"com", "net", "org", "app", "dev"}
DATE_KEYS = r"(?:Creation Date|Created On|Registered on|Registration Time|Domain Registration Date|created)"
NOT_FOUND = r"no match|not found|no data found|is available|no entries found|domain not found|no object found|is free"


def rdap(domain):
    try:
        req = urllib.request.Request(
            "https://rdap.org/domain/" + domain,
            headers={"Accept": "application/rdap+json", "User-Agent": "Mozilla/5.0"},
        )
        data = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace"))
        for ev in data.get("events", []):
            if ev.get("eventAction") == "registration" and ev.get("eventDate"):
                return ev["eventDate"][:10], "rdap"
    except urllib.error.HTTPError as e:
        if e.code == 404 and domain.rsplit(".", 1)[-1] in RDAP_404_IS_FREE:
            return "没人注册", "rdap"
    except Exception:
        pass
    return None, None


def run_whois(args):
    try:
        return subprocess.run(["whois"] + args, capture_output=True, text=True, timeout=25).stdout or ""
    except Exception:
        return ""


def whois(domain):
    out = run_whois([domain])
    if "IANA WHOIS server" in out[:400]:
        # 最前面是后缀自己的登记信息，去掉；后面每一段以「# whois.某某」开头
        parts = re.split(r"\n# whois\.[^\n]*\n", out)
        body = "\n".join(parts[1:]) if len(parts) > 1 else ""
        if not body.strip():
            # 没有转到登记局，直接问登记局再试一次
            body = run_whois(["-h", "whois.nic." + domain.rsplit(".", 1)[-1], domain])
    else:
        body = out
    m = re.search(r"(?im)^\s*" + DATE_KEYS + r"\s*:\s*(\d{4}-\d{2}-\d{2})", body)
    if m:
        return m.group(1), "whois"
    if re.search("(?i)" + NOT_FOUND, body):
        return "没人注册", "whois"
    return None, None


def main():
    args = sys.argv[1:]
    if args[:1] == ["--file"] and len(args) > 1:
        domains = [l.strip() for l in open(args[1], encoding="utf-8") if l.strip() and not l.startswith("#")]
    else:
        domains = args
    if not domains:
        sys.exit(__doc__)
    for d in domains:
        d = d.lower().replace("https://", "").replace("http://", "").split("/")[0]
        if d.startswith("www."):
            d = d[4:]
        result, src = rdap(d)
        if not result:
            result, src = whois(d)
        print(f"{d}\t{result or '没查到'}\t{src or ''}", flush=True)
        time.sleep(0.6)


if __name__ == "__main__":
    main()
