#!/usr/bin/env python3
"""查数：谷歌趋势和搜索量，走 DataForSEO。只用 Python 自带的库。默认美国、英语。

用法：
  python3 dfs.py related [--days 7|30] [--geo us|world] [--type web|images|youtube] 词根1 词根2 ...
      谷歌趋势的相关查询：上升栏和热门栏。几个词根一起发。每个词根约 0.011 美元。
  python3 dfs.py volume 词1 词2 ...            或者  python3 dfs.py volume --file 词表.txt
      每月的搜索量和出价，带最近 6 个月每月的量。一批最多 1000 个词，一批约 0.09 美元。
      空着回来的词会自动单独再查一次，多一次约 0.09 美元；不想多花的加 --no-retry。
  python3 dfs.py overview 词1 词2 ...          或者  --file 词表.txt
      点击流校正后的量、难度。一批最多 700 个词，约 0.03 美元。
  python3 dfs.py compare [--small] 词1 词2 ...
      和一个量已知的尺子词比热度，粗估每月的量。一次最多 4 个词，约 0.011 美元。
      默认尺子是 personality test，每月约 18 万次；--small 换成 image splitter，约 1.4 万次。
  python3 dfs.py curve [--5y] 词1 词2 ...
      每个词过去 12 个月（或 5 年）的趋势曲线，用来判新旧。几个词一起发。每个词约 0.011 美元。
  python3 dfs.py cost
      这个文件夹里到现在一共花了多少。

凭证：放一个 .env 文件，写两行
  DATAFORSEO_LOGIN=接口登录名
  DATAFORSEO_PASSWORD=接口密码
两个值在 DataForSEO 后台的 API Access 页。脚本只读这两行，不打印、不存到别处。
按顺序找这几个位置，先找到的先用（任选一处放就行）：
  1. 当前工作目录的 .env
  2. scripts/ 目录下的 .env
  3. skill 根目录的 .env          ← 推荐，本机就放这里，换工作目录也不用重配
  4. skill 根目录的真实路径的 .env（装成副本时 3 和 4 是两个不同目录，都会找）
  5. ~/.workbuddy/secrets/dataforseo.env
也可以直接用同名环境变量。没配凭证也能跑整套流程，见
references/本地部署与快速开始.md 的「轻量一轮」。

花费：每次请求把接口返回的实际花费记进当前文件夹的 花费.tsv，每条命令最后打印这次花了多少、累计多少。
读数：返回里没有的写「没收录」，不填 0。月搜索量是估算的搜索次数，不是会来的人数。
"""
import base64
import concurrent.futures
import datetime
import json
import os
import re
import sys
import threading
import time
import urllib.request

US = {"location_code": 2840, "language_code": "en"}
COST_FILE = "花费.tsv"
RULERS = {False: ("personality test", 180000), True: ("image splitter", 14000)}
_lock = threading.Lock()
_spent = 0.0


def env_search_paths():
    """按优先级列出 .env 可能的位置。

    本机增强：原版只认「当前工作目录的 .env」，从别处调用脚本（例如
    `python3 ~/.workbuddy/skills/money-keywords/scripts/dfs.py ...`）时 CWD 不是
    skill 目录，凭证就找不到。这里改成按优先级查找，任一处命中即可。

    第 3、4 项是同一个「skill 根目录」的两种可能：安装器常用软链
    （skills/money-keywords -> 版本目录），此时脚本被调用时看到的是软链路径，
    而 os.path.abspath 不解析软链、os.path.realpath 解析；装成副本时这两个目录
    就真的不同。两个都找，用户把 .env 放进哪个根目录都能命中（同一个目录会自动去重）。

    healthcheck.py 复用本函数，保证两处口径一致。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    skill_root = os.path.dirname(here)
    real_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    paths = [
        os.path.join(os.getcwd(), ".env"),                                  # 1. 本轮工作目录
        os.path.join(here, ".env"),                                         # 2. scripts/
        os.path.join(skill_root, ".env"),                                   # 3. skill 根目录（调用时看到的路径）
        os.path.join(real_root, ".env"),                                    # 4. skill 根目录（软链指向的真实路径）
        os.path.expanduser("~/.workbuddy/secrets/dataforseo.env"),          # 5. 全局 secrets
    ]
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def creds(verbose=False):
    login, pw = os.environ.get("DATAFORSEO_LOGIN"), os.environ.get("DATAFORSEO_PASSWORD")
    src = "环境变量" if (login and pw) else None
    tried = []
    for p in env_search_paths():
        tried.append(p)
        if login and pw:
            break
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8", errors="ignore"):
            m = re.match(r"\s*(DATAFORSEO_LOGIN|DATAFORSEO_PASSWORD)\s*=\s*(.*)", line)
            if m:
                v = m.group(2).strip().strip("\"'")
                if m.group(1) == "DATAFORSEO_LOGIN":
                    login = login or v
                else:
                    pw = pw or v
        if login and pw and not src:
            src = p
    if not (login and pw):
        sys.exit(
            "没有找到 DataForSEO 的凭证。下面这些位置都找过了：\n  - "
            + "\n  - ".join(tried)
            + "\n\n任选一处放一个 .env，里面写两行：\n"
            "  DATAFORSEO_LOGIN=接口登录名\n  DATAFORSEO_PASSWORD=接口密码\n"
            "（两个值在 DataForSEO 后台的 API Access 页；也可以用同名环境变量）\n\n"
            "没有凭证也能跑这一整套，只是趋势和搜索量要改用浏览器手动看，"
            "见 references/本地部署与快速开始.md 的「轻量一轮」。"
        )
    if verbose and src:
        print(f"[凭证] 来自 {src}", file=sys.stderr)
    return login, pw


def post(path, body, note):
    """发一次请求，把实际花费记进 花费.tsv。接口报错时返回 None，并把报错原文打印出来。"""
    global _spent
    login, pw = creds()
    tok = base64.b64encode(f"{login}:{pw}".encode()).decode()
    req = urllib.request.Request("https://api.dataforseo.com" + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": "Basic " + tok, "Content-Type": "application/json"})
    d = None
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.load(r)
            break
        except Exception as e:
            if i == 2:
                print(f"!! 没发成（{note}）：{e}", file=sys.stderr)
                return None
            time.sleep(5 * (i + 1))
    cost = d.get("cost") or 0
    with _lock:
        _spent += cost
        with open(COST_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{cost}\t{path}\t{note}\n")
    bad = [(t.get("status_code"), t.get("status_message")) for t in (d.get("tasks") or []) if t.get("status_code") != 20000]
    if d.get("status_code") != 20000 or bad:
        print(f"!! 接口报错（{note}）：{d.get('status_code')} {d.get('status_message')} {bad[:2]}", file=sys.stderr)
        return None
    return d


def results(d):
    return [r for t in (d or {}).get("tasks") or [] for r in (t.get("result") or [])]


def total_cost():
    tot = 0.0
    if os.path.exists(COST_FILE):
        for line in open(COST_FILE, encoding="utf-8"):
            p = line.split("\t")
            try:
                tot += float(p[1])
            except Exception:
                pass
    return tot


def footer():
    tot = total_cost()
    print(f"\n# 这次花了 {_spent:.4f} 美元；这个文件夹累计 {tot:.4f} 美元")
    if tot >= 3:
        print("# 累计已经到 3 美元：照「花钱的规矩」，停下来告诉用户花了多少、还差哪几步，等他说继续")


def words(args):
    if args[:1] == ["--file"] and len(args) > 1:
        raw = [l.strip() for l in open(args[1], encoding="utf-8")]
    else:
        raw = args
    good, bad = [], []
    for k in raw:
        k = re.sub(r"\s+", " ", k.lower().replace("’", "'")).strip()
        if not k or k.startswith("#"):
            continue
        if len(k) > 80 or len(k.split()) > 10 or re.search(r"[^a-z0-9 \-'&./+#%$]", k):
            bad.append(k)
        elif k not in good:
            good.append(k)
    if bad:
        print(f"# 这 {len(bad)} 个词太长或带特殊符号，接口不收，没查：" + "；".join(bad[:20]), file=sys.stderr)
    return good


def opt(args, name, default, allowed=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            sys.exit(f"{name} 后面要跟一个值")
        v = args[i + 1]
        del args[i:i + 2]
        if allowed and v not in allowed:
            sys.exit(f"{name} 只能是 " + "、".join(allowed))
        return v
    return default


def flag(args, name):
    if name in args:
        args.remove(name)
        return True
    return False


def together(fn, items):
    """几个请求一起发，最多同时 4 个，结果照原来的顺序给回来。"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(fn, items))


# ---------- 相关查询 ----------
def cmd_related(args):
    days = opt(args, "--days", "7", ["7", "30"])
    geo = opt(args, "--geo", "us", ["us", "world"])
    kind = opt(args, "--type", "web", ["web", "images", "youtube"])
    roots = [a.strip() for a in args if a.strip()]
    if not roots:
        sys.exit("没有给词根")

    def one(root):
        body = {"keywords": [root], "type": kind, "time_range": f"past_{days}_days",
                "item_types": ["google_trends_queries_list"]}
        if geo == "us":
            body["location_code"] = 2840
        d = post("/v3/keywords_data/google_trends/explore/live", [body], f"相关查询 {root}")
        if d is None:
            return root, None, None
        top, rising = [], []
        for r in results(d):
            for it in r.get("items") or []:
                if it.get("type") == "google_trends_queries_list" and isinstance(it.get("data"), dict):
                    top = [(x.get("query"), x.get("value")) for x in (it["data"].get("top") or [])]
                    rising = [(x.get("query"), x.get("value")) for x in (it["data"].get("rising") or [])]
        return root, rising, top

    names = {"web": "网页搜索", "images": "图片搜索", "youtube": "YouTube 搜索"}
    print(f"# 谷歌趋势相关查询｜{names[kind]}｜过去 {days} 天｜{'美国' if geo == 'us' else '全球'}｜{datetime.date.today()} 查")
    for root, rising, top in together(one, roots):
        print(f"\n## {root}")
        if rising is None:
            print("没查成")
            continue
        def show(v):
            return "Breakout" if isinstance(v, (int, float)) and v >= 5000 else f"+{v}%"
        print(f"上升栏 {len(rising)} 条：" + ("；".join(f"{q}（{show(v)}）" for q, v in rising) or "空"))
        print("热门栏前 10：" + ("；".join(f"{q}（{v}）" for q, v in top[:10]) or "空"))
    print("\n# 上升栏的数是涨幅；Breakout 是刚冒出来、涨了几十倍以上的。上升栏不到 5 条的，换 --days 30 再看")


# ---------- 每月的量 ----------
def cmd_volume(args):
    no_retry = flag(args, "--no-retry")
    kws = words(args)[:1000]
    if not kws:
        sys.exit("没有给词")
    t = datetime.date.today()
    y, m = t.year - 1, t.month - 1
    if m == 0:
        y, m = y - 1, 12

    def fetch(batch, note):
        d = post("/v3/keywords_data/google_ads/search_volume/live",
                 [{**US, "keywords": batch, "date_from": f"{y}-{m:02d}-01"}], note)
        out = {}
        for it in results(d):
            ser = sorted((x["year"], x["month"], x.get("search_volume") or 0) for x in (it.get("monthly_searches") or []) if x.get("year"))
            out[(it.get("keyword") or "").lower()] = (it.get("search_volume"), it.get("cpc"), ser)
        return d, out

    d, got = fetch(kws, f"每月的量 {len(kws)} 个词")
    # 同一批里有两个相近的说法时，接口常常只给其中一个数，另一个空着回来；单独再查就有数。
    # 所以空着回来的词自动再查一次。多一次请求，约 0.09 美元；不想多花的加 --no-retry。
    empty = [k for k in kws if not got.get(k) or got[k][0] is None]
    second = set()
    if d is not None and empty and len(empty) < len(kws) and not no_retry:
        d2, got2 = fetch(empty, f"每月的量 空着回来的 {len(empty)} 个词再查一次")
        for k in empty:
            if got2.get(k) and got2[k][0] is not None:
                got[k] = got2[k]
                second.add(k)
    print("词\t12个月平均\t出价\t最近6个月（年-月:量）\t标记")
    same = {}
    for k in kws:
        v = got.get(k)
        if d is None:
            print(f"{k}\t没查成\t\t\t")
            continue
        if not v or v[0] is None:
            print(f"{k}\t没收录\t\t\t")
            continue
        ser = v[2][-6:]
        tags = []
        if len(ser) >= 3:
            last, p1, p2 = ser[-1][2], ser[-2][2], ser[-3][2]
            if last >= 200 and p1 <= last * 0.05 and p2 <= last * 0.05:
                tags.append("最近一个月才有量")
            elif last >= 200 and p2 <= last * 0.05:
                tags.append("近两个月才有量")
        if k in second:
            tags.append("第二次才查到")
        print(f"{k}\t{v[0]}\t{v[1] if v[1] is not None else ''}\t" + " ".join(f"{a}-{b:02d}:{c}" for a, b, c in ser) + "\t" + "，".join(tags))
        if v[0]:
            same.setdefault(tuple(v[2]), []).append(k)
    groups = [g for g in same.values() if len(g) > 1]
    if groups:
        print("\n# 下面每一组里的词，数一模一样，是工具已经并成了一组，量只算一次：")
        for g in groups:
            print("#   " + "；".join(g))
    if second:
        print(f"\n# 有 {len(second)} 个词第一次空着回来、单独再查才有数：同一批里相近的说法会互相挡掉。再查一次以后还是「没收录」的，才当它没收录")
    print("\n# 谷歌广告口径，数据会晚一两个月；长尾词可能被并进大词")


# ---------- 点击流校正后的量、难度 ----------
def cmd_overview(args):
    kws = words(args)[:700]
    if not kws:
        sys.exit("没有给词")
    d = post("/v3/dataforseo_labs/google/keyword_overview/live",
             [{**US, "keywords": kws, "include_serp_info": False, "include_clickstream_data": True}], f"点击流和难度 {len(kws)} 个词")
    got = {}
    for r in results(d):
        for it in r.get("items") or []:
            ki = it.get("keyword_info") or {}
            got[(it.get("keyword") or "").lower()] = (
                ki.get("search_volume"),
                (it.get("keyword_info_normalized_with_clickstream") or {}).get("search_volume"),
                (it.get("keyword_properties") or {}).get("keyword_difficulty"), ki.get("cpc"))
    def s(x):
        return "没收录" if x is None else str(x)
    print("词\t月搜索量（广告口径，12个月平均）\t点击流校正后的量\t难度\t出价")
    for k in kws:
        v = got.get(k)
        print(f"{k}\t" + ("没查成\t\t\t" if d is None else "没收录\t\t\t" if not v else "\t".join(s(x) for x in v)))
    print("\n# 都是估算。老词用点击流校正后的量；新词这里常常没收录，用 volume 里最近一个完整月的量")


# ---------- 比热度 ----------
def graph(d, kws):
    series = {}
    for r in results(d):
        for it in r.get("items") or []:
            if it.get("type") == "google_trends_graph":
                names = it.get("keywords") or kws
                for i, k in enumerate(names):
                    series[k] = [(p.get("date_from"), (p.get("values") or [None] * len(names))[i]) for p in (it.get("data") or [])]
    return series


def cmd_compare(args):
    small = flag(args, "--small")
    kws = [a.strip() for a in args if a.strip()][:4]
    if not kws:
        sys.exit("没有给词")
    ruler, ruler_sv = RULERS[small]
    d = post("/v3/keywords_data/google_trends/explore/live",
             [{"keywords": kws + [ruler], "type": "web", "time_range": "past_30_days", "location_code": 2840}], f"比热度 {kws}")
    s = graph(d, kws + [ruler])
    def avg(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else 0
    ra = avg([v for _, v in s.get(ruler, [])])
    print(f"# 尺子 {ruler}：过去 30 天平均 {ra:.1f}，按每月约 {ruler_sv} 次算。美国")
    for k in kws:
        pts = [v or 0 for _, v in s.get(k, [])]
        if d is None or not pts:
            print(f"{k}\t没查成")
            continue
        nonzero = sum(1 for v in pts if v > 0)
        a30, a7 = avg(pts), avg(pts[-7:])
        if nonzero == 0:
            print(f"{k}\t趋势里看不出：读数全是 0，量太小显示不出来。" + ("" if small else "换 --small 再比一次"))
        elif nonzero <= 2:
            print(f"{k}\t趋势里读数太稀：30 天里只有 {nonzero} 天有读数，折算出来的数不能用，以 volume 的量为准")
        else:
            trend = "在涨" if a7 > a30 * 1.2 else ("在落" if a7 < a30 * 0.8 else "持平")
            est = round(ruler_sv * a30 / ra) if ra else "算不出"
            print(f"{k}\t过去 30 天平均 {a30:.1f}\t最近 7 天平均 {a7:.1f}\t粗估每月约 {est}\t{trend}")
    print("\n# 粗估，可能差几倍。趋势是宽匹配：一个短词的读数里，带着它的长词都算进去了")


# ---------- 曲线 ----------
def cmd_curve(args):
    five = flag(args, "--5y")
    kws = [a.strip() for a in args if a.strip()]
    if not kws:
        sys.exit("没有给词")
    rng = "past_5_years" if five else "past_12_months"

    def one(k):
        d = post("/v3/keywords_data/google_trends/explore/live",
                 [{"keywords": [k], "type": "web", "time_range": rng, "location_code": 2840}], f"曲线 {k}")
        return k, d, graph(d, [k]).get(k, [])

    print(f"# 谷歌趋势曲线｜{'过去 5 年' if five else '过去 12 个月'}｜美国")
    for k, d, raw in together(one, kws):
        print(f"\n## {k}")
        pts = [(a, v or 0) for a, v in raw]
        if d is None:
            print("没查成")
            continue
        if not pts or max(v for _, v in pts) == 0:
            print("趋势里看不出：读数全是 0，量太小显示不出来")
            continue
        first = next(a for a, v in pts if v > 0)
        peak = max(pts, key=lambda x: x[1])
        recent, before = [v for _, v in pts[-9:]], [v for _, v in pts[:-9]]
        ra = sum(recent) / len(recent)
        ba = sum(before) / len(before) if before else 0
        zeros = sum(1 for v in before if v == 0)
        print(f"第一次有读数：{first}。最高的一期：{peak[0]}。最近 9 期平均 {ra:.1f}；再往前 {len(before)} 期平均 {ba:.1f}，其中读数是 0 的 {zeros} 期")
        if sum(1 for _, v in pts if v > 0) <= len(pts) // 3:
            print("读数很稀，有 0 有几十的那种：量小的词常这样，不拿它判新旧，以 volume 里每月的量为准")
        print("每期读数，从早到晚：" + " ".join(str(v) for _, v in pts))
    print("\n# 读数是这个词自己和自己比，最高那一期是 100；不同的词之间不能拿这个数比大小")


def main():
    args = sys.argv[1:]
    cmds = {"related": cmd_related, "volume": cmd_volume, "overview": cmd_overview, "compare": cmd_compare, "curve": cmd_curve}
    if not args or args[0] in ("-h", "--help"):
        sys.exit(__doc__)
    if args[0] == "cost":
        print(f"这个文件夹累计花了 {total_cost():.4f} 美元，明细在 {COST_FILE}")
        return
    if args[0] not in cmds:
        sys.exit("不认识的用法：" + args[0] + "\n" + __doc__)
    cmds[args[0]](args[1:])
    footer()


if __name__ == "__main__":
    main()
