#!/usr/bin/env python3
"""谷歌下拉：在搜索框里打一个词，谷歌提示的那些搜法。公开地址，不花钱，不用登录。只用 Python 自带的库。

用法：
  python3 suggest.py 词根1 词根2 ...          每个词根取一次
  python3 suggest.py --az 名字1 名字2 ...     每个词后面再加 a 到 z，一个词发 27 次请求，几次一起发
  python3 suggest.py --gl gb 词根1            换国家，默认 us

输出：每个词根一段，以「## 词根」开头，下面一行一个搜法，去过重。

--az 慢，只对名字本身、名字加这件事、和趋势上升栏不到 5 条的词根用，一轮最多 5 个词根。
下拉里的多是老词。它只拿来找说法，不拿来比先后，也不说明有多少人搜；量要用 dfs.py volume 查。
"""
import concurrent.futures
import json
import sys
import time
import urllib.parse
import urllib.request


def one(q, gl):
    url = ("https://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl=" + gl +
           "&q=" + urllib.parse.quote(q))
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace"))[1]
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def main():
    args = sys.argv[1:]
    az = "--az" in args
    if az:
        args.remove("--az")
    gl = "us"
    if "--gl" in args:
        i = args.index("--gl")
        gl = args[i + 1]
        del args[i:i + 2]
    roots = [a.strip() for a in args if a.strip()]
    if not roots:
        sys.exit(__doc__)
    for root in roots:
        tails = [""] + ([" " + c for c in "abcdefghijklmnopqrstuvwxyz"] if az else [])
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            got = list(pool.map(lambda t: one(root + t, gl), tails))
        seen, failed = [], 0
        for g in got:
            if g is None:
                failed += 1
                continue
            for s in g:
                if s not in seen:
                    seen.append(s)
        print(f"## {root}（{len(seen)} 条" + (f"，{failed} 次没取到" if failed else "") + "）")
        print("\n".join(seen) + "\n")
        time.sleep(0.5)


if __name__ == "__main__":
    main()
