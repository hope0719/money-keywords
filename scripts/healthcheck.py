#!/usr/bin/env python3
"""开工前自检：一条命令告诉你这套 skill 现在能不能用、缺什么、怎么补。

用法：
  python3 scripts/healthcheck.py           查一遍，不花钱
  python3 scripts/healthcheck.py --quiet   只打印结论和问题项
  python3 scripts/healthcheck.py --network 跳过网络检查（离线时用）

查六件事：
  1. Python 版本够不够（要 3.8 以上）
  2. skill 的文件齐不齐、脚本语法通不通
  3. 脚本有没有用到标准库以外的东西（这套脚本号称只用标准库）
  4. DataForSEO 凭证找到了没有、有效没有、余额还剩多少
  5. 四个数据源通不通：谷歌下拉、RDAP、苹果商店、DataForSEO
  6. 有没有设代理环境变量

结论只有两种：
  ✅ 可以开工 —— 有凭证走标准一轮，没凭证走轻量一轮，都能跑完
  ⛔ 先修一下 —— 有硬阻塞，按提示补
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.dont_write_bytecode = True   # 别在 skill 目录里留 __pycache__

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PY_SCRIPTS = ["dfs.py", "suggest.py", "appstore_new.py", "domain_check.py",
              "serp_table.py", "whois_date.py"]
JS_SCRIPTS = ["google_top20.js"]
REFS = ["取谷歌前20名的办法.md", "新词的几条规律.md", "查询词怎么出.md",
        "读真人原帖的办法.md", "从抱怨里找.md", "去哪发现新词和新站.md"]

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

results = []   # (等级, 标题, 说明)


def add(level, title, detail=""):
    results.append((level, title, detail))


def fetch(url, timeout=8, method="GET", headers=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", UA)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(400)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return None, repr(e).encode()[:200]


# ---------- 1. Python ----------
def check_python():
    v = sys.version_info
    if v >= (3, 8):
        add("ok", "Python %d.%d.%d" % v[:3], "")
    else:
        add("bad", "Python 版本太低：%d.%d" % v[:2], "要 3.8 以上，换个 python3 再跑")


# ---------- 2. 文件与语法 ----------
def check_files():
    missing = []
    for n in PY_SCRIPTS + JS_SCRIPTS:
        if not os.path.isfile(os.path.join(HERE, n)):
            missing.append("scripts/" + n)
    for n in REFS:
        if not os.path.isfile(os.path.join(ROOT, "references", n)):
            missing.append("references/" + n)
    if not os.path.isfile(os.path.join(ROOT, "SKILL.md")):
        missing.append("SKILL.md")

    if not missing:
        add("ok", "文件完整", "%d 个脚本 + %d 篇参考" % (len(PY_SCRIPTS) + len(JS_SCRIPTS), len(REFS)))
    else:
        add("bad", "缺 %d 个文件" % len(missing), "、".join(missing))

    # 语法检查：用内置 compile()，不落 __pycache__、不启子进程
    bad = []
    for n in PY_SCRIPTS:
        p = os.path.join(HERE, n)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                compile(f.read(), p, "exec")
        except SyntaxError as e:
            bad.append("%s: 第 %s 行 %s" % (n, e.lineno, e.msg))
        except Exception as e:
            bad.append("%s: %s" % (n, repr(e)[:80]))
    if bad:
        add("bad", "有脚本语法不通", "；".join(bad))
    elif not missing:
        add("ok", "脚本语法全部通过", "")


# ---------- 3. 第三方依赖 ----------
def check_deps():
    third = []
    for n in PY_SCRIPTS:
        p = os.path.join(HERE, n)
        if not os.path.isfile(p):
            continue
        for line in open(p, encoding="utf-8", errors="ignore"):
            m = re.match(r"\s*(?:import|from)\s+([a-zA-Z_][\w]*)", line)
            if not m:
                continue
            mod = m.group(1)
            if mod in sys.stdlib_module_names or mod in ("__future__",):
                continue
            if os.path.isfile(os.path.join(HERE, mod + ".py")):
                continue
            third.append("%s ← %s" % (mod, n))
    if third:
        add("warn", "用到标准库以外的模块", "、".join(sorted(set(third))))
    else:
        add("ok", "只用 Python 标准库", "不用 pip install 任何东西")


# ---------- 4. 凭证 ----------
def find_env():
    """和 dfs.py 完全同一套查找顺序。"""
    try:
        sys.path.insert(0, HERE)
        import dfs  # noqa
        for p in dfs.env_search_paths():
            if os.path.exists(p):
                login = pw = None
                for line in open(p, encoding="utf-8", errors="ignore"):
                    m = re.match(r"\s*(DATAFORSEO_LOGIN|DATAFORSEO_PASSWORD)\s*=\s*(.*)", line)
                    if m:
                        v = m.group(2).strip().strip("\"'")
                        if m.group(1) == "DATAFORSEO_LOGIN":
                            login = v
                        else:
                            pw = v
                if login and pw:
                    return p, login, pw
                return p, login, pw          # 文件在但缺一行
        return None, None, None
    except Exception:
        p = os.path.join(ROOT, ".env")
        if os.path.exists(p):
            return p, None, None
        return None, None, None


def check_creds(network=True):
    login = os.environ.get("DATAFORSEO_LOGIN")
    pw = os.environ.get("DATAFORSEO_PASSWORD")
    if login and pw:
        add("ok", "DataForSEO 凭证来自环境变量", "")
        return login, pw, "环境变量"

    path, login, pw = find_env()
    if not path:
        add("warn", "没有 DataForSEO 凭证",
            "不影响开跑，走「轻量一轮」；想用标准一轮就把 .env 放到 skill 根目录")
        return None, None, None
    if not (login and pw):
        add("warn", "凭证文件不全：%s" % path,
            "里面缺 DATAFORSEO_LOGIN 或 DATAFORSEO_PASSWORD 其中一行")
        return None, None, None

    add("ok", "DataForSEO 凭证已找到", path)

    if not network:
        return login, pw, path

    # 验证有效性 + 查余额（appendix/user_data 不花钱）
    tok = base64.b64encode(("%s:%s" % (login, pw)).encode()).decode()
    code, body = fetch("https://api.dataforseo.com/v3/appendix/user_data",
                       timeout=12, headers={"Authorization": "Basic " + tok})
    if code == 200:
        try:
            d = json.loads(body.decode("utf-8", "replace"))
            money = (d.get("tasks") or [{}])[0].get("result") or []
            bal = None
            if money and isinstance(money, (list,)):
                bal = (money[0] or {}).get("money", {}).get("balance")
            add("ok", "凭证有效" + ("，余额 $%s" % bal if bal is not None else ""),
                "余额查不到不影响，接口能认就行")
        except Exception:
            add("ok", "凭证有效", "余额解析失败，不影响")
        return login, pw, path
    if code in (401, 403):
        add("bad", "凭证无效（%s）" % code, "密码或登录名不对，去 API Access 页重新复制")
        return None, None, None
    if code is None:
        add("warn", "DataForSEO 连不上", "网络或代理问题，凭证本身没验成")
        return login, pw, path
    add("warn", "DataForSEO 返回 %s" % code, "把报错给 DataForSEO 客服看")
    return login, pw, path


# ---------- 5. 网络 ----------
def check_network():
    targets = [
        ("谷歌下拉", "https://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl=us&q=test"),
        ("RDAP 注册日期", "https://rdap.org/domain/example.com"),
        ("苹果应用商店", "https://itunes.apple.com/search?term=test&country=us&limit=1"),
    ]
    down = []
    for name, url in targets:
        code, body = fetch(url, timeout=8)
        if code and code < 500 and code not in (401, 403):
            add("ok", name + " 通", "HTTP %s" % code)
        else:
            down.append("%s(HTTP %s)" % (name, code))
            add("bad", name + " 不通", "HTTP %s" % code)
    if down:
        add("warn", "有 %d 个数据源连不上" % len(down),
            "先看代理：谷歌相关通常要代理；查 DNS：dig rdap.org")


# ---------- 6. 代理 ----------
def check_proxy():
    keys = ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    hit = ["%s=%s" % (k, os.environ[k]) for k in keys if os.environ.get(k)]
    if hit:
        add("ok", "代理环境变量已设", "、".join(hit))
    else:
        add("info", "没有代理环境变量", "谷歌能通就不用管；连不上再配")


# ---------- 汇总 ----------
def main():
    quiet = "--quiet" in sys.argv
    network = "--network" not in sys.argv and "--offline" not in sys.argv

    check_python()
    check_files()
    check_deps()
    check_creds(network=network)
    if network:
        check_network()
    check_proxy()

    icon = {"ok": "✅", "warn": "⚠️ ", "bad": "⛔", "info": "· "}
    if not quiet:
        print("=" * 62)
        print("money-keywords 自检   %s" % ROOT)
        print("=" * 62)
        for lv, t, d in results:
            print("%s %s" % (icon[lv], t))
            if d:
                print("    %s" % d)
    else:
        for lv, t, d in results:
            if lv in ("bad", "warn"):
                print("%s %s%s" % (icon[lv], t, (" — " + d) if d else ""))

    bad = [r for r in results if r[0] == "bad"]
    creds = any(r[1].startswith("DataForSEO 凭证已找到") or "凭证有效" in r[1] for r in results)
    print()
    if bad:
        print("⛔ 先修一下上面标 ⛔ 的项，再开工。")
        return 1

    print("✅ 可以开工。%s" % (
        "有 DataForSEO 凭证，按 SKILL.md 的「一轮做多少」走标准一轮。"
        if creds else
        "没有 DataForSEO 凭证，走「轻量一轮」——全套流程照样跑完，只是搜索量改用趋势粗估和档位。"
    ))
    print("   开跑前读一眼：references/本地部署与快速开始.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
