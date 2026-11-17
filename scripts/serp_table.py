#!/usr/bin/env python3
"""把谷歌前 20 名和域名注册日期拼成每个词一张表，顺手把数数的事做完。不联网，不花钱。

用法：
  python3 serp_table.py domains 排名.txt
      列出排名里的独立站域名，一行一个，拿去给 whois_date.py 查注册日期。
      大站和免费子域名不列。
  python3 serp_table.py table 排名.txt 注册日期.txt [--today 2026-11-17]
      每个词一张表：名次、域名、注册日期、哪一档、标题或网址里有没有这个词的实词、标题。
      每个词后面一行小结，最后一段总数。

排名.txt 的写法，和 google_top20.js 取回来的一样，几个词可以放在同一个文件里：
  ## snow day calculator
  1 | p1 | snowdaycalculator.com | / | Snow Day Calculator
  2 | p1 | reddit.com | /r/xxx | ...
注册日期.txt 就是 whois_date.py 打印出来的内容：域名、制表符、日期。

它替你数的：一共几条；一年以内的新站几个、各排第几、排进前 10 的几个；
近两个月注册的几个；日期没查到的、还没查的各有哪些。

它不替你判断的：
  1. 「实词都在」只说明这个页面可能是专门做这个词的。它是办事的工具页，还是讲这件事的文章，
     要打开看，照 SKILL.md 第 5 步分。
  2. 大站的名单只收了最常见的。名单以外的大站会被当成独立站列出来去查日期，
     查出来是老域名，不影响结果。
"""
import datetime
import re
import sys

BIG = {
    "google.com", "youtube.com", "reddit.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
    "tiktok.com", "linkedin.com", "pinterest.com", "medium.com", "quora.com", "wikipedia.org", "github.com",
    "apple.com", "microsoft.com", "amazon.com", "adobe.com", "canva.com", "shopify.com", "substack.com",
    "threads.net", "twitch.tv", "discord.com", "yahoo.com", "bing.com", "forbes.com", "nytimes.com",
    "techcrunch.com", "theverge.com", "engadget.com", "mashable.com", "cnet.com", "wired.com",
    "producthunt.com", "stackexchange.com", "stackoverflow.com", "blog.youtube", "youtu.be",
}
FREE_HOSTS = ("vercel.app", "pages.dev", "github.io", "netlify.app", "web.app", "herokuapp.com",
              "blogspot.com", "wordpress.com", "wixsite.com")
TWO_LEVEL = {"co.uk", "org.uk", "com.au", "co.in", "com.br", "co.jp", "co.nz", "com.cn", "co.za",
             "com.sg", "com.hk", "com.tr", "com.mx", "co.kr", "com.tw"}
STOP = {"what", "is", "do", "does", "how", "the", "a", "an", "for", "to", "and", "vs", "best", "free", "of"}
SAME = [{"maker", "generator", "creator", "builder", "tool"}, {"checker", "detector"}]


def reg_domain(host):
    host = host.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    for f in FREE_HOSTS:
        if host.endswith("." + f):
            return host, "free"
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in TWO_LEVEL:
        return ".".join(parts[-3:]), ""
    return ".".join(parts[-2:]), ""


def norm(tok):
    tok = tok.lower().replace(".", "")
    for group in SAME:
        if tok in group or (tok.endswith("s") and tok[:-1] in group):
            return sorted(group)[0]
    if len(tok) > 3 and tok.endswith("s"):
        tok = tok[:-1]
    return tok


def tokens(text):
    return [norm(t) for t in re.split(r"[^A-Za-z0-9.]+", text) if t.strip(".")]


def real_words(query):
    return [t for t in tokens(query) if t not in STOP]


def has_all(query, domain, path, title):
    want = real_words(query)
    if not want:
        return False
    have = set(tokens(title) + tokens(path))
    blob = (domain + path).lower()
    for w in want:
        if w in have:
            continue
        if len(w) >= 4 and w in blob:
            continue
        return False
    return True


def read_serp(path):
    words, cur = [], None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("## "):
            cur = (line[3:].strip(), [])
            # 同一个词存了两次的（先存第一页，后来又存了两页合起来的），只认后面那一次
            for i, w in enumerate(words):
                if w[0] == cur[0]:
                    words[i] = cur
                    break
            else:
                words.append(cur)
            continue
        if cur is None or not line.strip() or line.startswith("#") or line.startswith("!!"):
            continue
        p = [x.strip() for x in line.split("|")]
        if len(p) < 4 or not p[0].isdigit():
            continue
        if len(p) == 4:      # 名次 | 域名 | 路径 | 标题
            rank, host, pth, title = p[0], p[1], p[2], p[3]
        else:                # 名次 | p1 | 域名 | 路径 | 标题；标题里有竖线的并回去
            rank, host, pth, title = p[0], p[2], p[3], " | ".join(p[4:])
        cur[1].append((int(rank), host, pth, title))
    return words


def read_dates(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 2 and p[0].strip():
            out[p[0].strip().lower()] = p[1].strip()
    return out


def months_ago(today, n):
    y, m = today.year, today.month - n
    while m <= 0:
        y, m = y - 1, m + 12
    d = min(today.day, 28)
    return datetime.date(y, m, d)


def band(date_text, today):
    """返回（哪一档，是不是新站，是不是很新）。"""
    if not re.match(r"\d{4}-\d{2}-\d{2}$", date_text or ""):
        return ("没查到" if date_text else "还没查"), False, False
    d = datetime.date.fromisoformat(date_text)
    if d >= months_ago(today, 2):
        return "很新", True, True
    if d >= months_ago(today, 12):
        return "新站", True, False
    return "一年以上", False, False


def main():
    args = sys.argv[1:]
    today = datetime.date.today()
    if "--today" in args:
        i = args.index("--today")
        today = datetime.date.fromisoformat(args[i + 1])
        args = args[:i] + args[i + 2:]
    if len(args) < 2 or args[0] not in ("domains", "table"):
        sys.exit(__doc__)
    words = read_serp(args[1])
    if not words:
        sys.exit("排名文件里没有读到「## 词」开头的段落")

    if args[0] == "domains":
        seen = []
        for _, rows in words:
            for _, host, _, _ in rows:
                dom, kind = reg_domain(host)
                if kind == "free" or dom in BIG or dom in seen:
                    continue
                seen.append(dom)
        print("\n".join(seen))
        return

    if len(args) < 3:
        sys.exit("table 要两个文件：排名.txt 注册日期.txt")
    dates = read_dates(args[2])
    y1, m2 = months_ago(today, 12), months_ago(today, 2)
    print(f"今天按 {today} 算。很新：{m2} 以后注册的。新站：{y1} 到 {m2} 之间注册的。\n")
    total, all_new, all_new10, all_fresh, unknown, unchecked, checked = 0, {}, set(), set(), set(), set(), set()
    for q, rows in words:
        total += len(rows)
        print(f"## {q}（共 {len(rows)} 条）\n")
        print("| 名次 | 域名 | 注册日期 | 哪一档 | 实词都在 | 标题 |")
        print("|---|---|---|---|---|---|")
        new_here, big10, hit = [], 0, 0
        for rank, host, pth, title in rows:
            dom, kind = reg_domain(host)
            if kind == "free":
                dt, bd, is_new, fresh = "", "免费子域名", False, False
            elif dom in BIG:
                dt, bd, is_new, fresh = "", "大站", False, False
                big10 += rank <= 10
            else:
                dt = dates.get(dom, "")
                bd, is_new, fresh = band(dt, today)
                if bd == "没查到":
                    unknown.add(dom)
                elif bd == "还没查":
                    unchecked.add(dom)
                else:
                    checked.add(dom)
            match = has_all(q, host, pth, title)
            hit += match
            if is_new:
                new_here.append((rank, dom, dt, fresh))
                all_new.setdefault(dom, dt)
                if rank <= 10:
                    all_new10.add(dom)
                if fresh:
                    all_fresh.add(dom)
            shown = host if host == dom or host == "www." + dom else f"{host}"
            print(f"| {rank} | `{shown}` | {dt or ''} | {bd} | {'是' if match else ''} | {title[:60].replace('|', '/')} |")
        doms = {}
        for rank, dom, dt, fresh in new_here:
            doms.setdefault(dom, [dt, fresh, []])[2].append(rank)
        parts = [f"`{d}` {v[0]}{'，很新' if v[1] else ''}，第 {'、'.join(str(r) for r in v[2])}" for d, v in doms.items()]
        print(f"\n小结：标题或网址里实词都在的 {hit} 条，要打开分清是工具页还是文章。"
              f"新站 {len(doms)} 个" + ("：" + "；".join(parts) if parts else "") +
              f"。其中近两个月注册的 {sum(1 for v in doms.values() if v[1])} 个，"
              f"排进前 10 的 {sum(1 for v in doms.values() if min(v[2]) <= 10)} 个。前 10 里名单上的大站 {big10} 条。\n")
    print("## 总数\n")
    print(f"- {len(words)} 个词，一共 {total} 条自然结果。")
    print(f"- 查到注册日期的独立站 {len(checked)} 个；一年以内的新站 {len(all_new)} 个，排进前 10 的 {len(all_new10)} 个，近两个月注册的 {len(all_fresh)} 个。")
    if unknown:
        print(f"- 日期没查到的 {len(unknown)} 个，不当新站算：" + "、".join(sorted(unknown)))
    if unchecked:
        print(f"- 还没查的 {len(unchecked)} 个，是大站的不用查，是独立站的补查：" + "、".join(sorted(unchecked)))


if __name__ == "__main__":
    main()
