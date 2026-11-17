#!/usr/bin/env python3
"""在苹果应用商店里搜一个词，按上架日期从新到旧排，看最近有哪些新应用进了这个方向。
用的是苹果公开的搜索接口，不花钱，不用登录。

用法：
  python3 appstore_new.py "iphone duo wallpaper" "live photo maker"
  python3 appstore_new.py --country gb "wallpaper maker"      # 换国家，默认美国

每个词输出最多 25 个应用：名字、哪天上架、多少个评分、价格、开发者。
最后打印一句：近两个月上架的有几个、一年以内的有几个。

怎么用这些结果：
  - 应用的名字里常带着别人正在抢的词，记进候选词表，来源写「应用商店」。
  - 近两个月上架了多少个同类应用，说明有多少人正在进这个方向。
  - 评分数很少的新应用，说明它还没拿到多少用户；评分多的老应用是这个方向里已经站住的。
  - 上架日期是这个应用第一次上架的日子。老应用改名换内容的，日期还是旧的。
"""
import datetime
import json
import sys
import time
import urllib.parse
import urllib.request


def search(term, country):
    url = ("https://itunes.apple.com/search?entity=software&limit=25&country=" + country +
           "&term=" + urllib.parse.quote(term))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")).get("results", [])


def main():
    args = sys.argv[1:]
    country = "us"
    if args[:1] == ["--country"] and len(args) > 1:
        country, args = args[1].lower(), args[2:]
    if not args:
        sys.exit(__doc__)
    today = datetime.date.today()
    print(f"# 应用商店搜索｜国家 {country}｜{today} 查｜按上架日期从新到旧")
    for term in args:
        try:
            rows = search(term, country)
        except Exception as e:
            print(f"\n## {term}\n没查成：{e}")
            continue
        rows.sort(key=lambda r: r.get("releaseDate", ""), reverse=True)
        new2 = new12 = 0
        print(f"\n## {term}（{len(rows)} 个）")
        for r in rows:
            d = (r.get("releaseDate") or "")[:10]
            try:
                age = (today - datetime.date.fromisoformat(d)).days
            except ValueError:
                age = None
            if age is not None and age <= 61:
                new2 += 1
            if age is not None and age <= 365:
                new12 += 1
            tag = "很新" if age is not None and age <= 61 else ("新" if age is not None and age <= 365 else "")
            print(f"{d}\t{tag}\t{r.get('userRatingCount', 0)} 个评分\t{r.get('formattedPrice', '')}\t"
                  f"{(r.get('trackName') or '')[:60]}\t{(r.get('sellerName') or '')[:30]}")
        print(f"近两个月上架的 {new2} 个，一年以内的 {new12} 个")
        time.sleep(1)


if __name__ == "__main__":
    main()
