# 本地改动清单（升级后需重放）

本机对 skl_money-keywords v1.0.1 做过增强。**SkillHub 升级到新版本时 `current` 会指向新目录，这些改动会失效**，需要按本文件重放。

- 基线版本：`skl_money-keywords` v1.0.1（SHA-256 `34cde778…4a898a`）
- 改动日期：2026-11-18
- 原始副本：`.original-1.0.1/`（未改动的 15 个文件）
- 对比命令：`diff -ru .original-1.0.1 versions/1.0.1`

---

## 改了什么

| # | 文件 | 类型 | 为什么 |
|---|---|---|---|
| 1 | `scripts/dfs.py` | 修改两处 | **原版只在「当前工作目录」找 `.env`**，从别处调用脚本时凭证找不到，整套付费查询跑不起来 |
| 2 | `scripts/healthcheck.py` | 新增 | 装完无法判断能不能用，配错也不知道错在哪 |
| 3 | `references/本地部署与快速开始.md` | 新增 | 没有凭证时怎么完整跑完一轮、各档强度怎么选、常见故障怎么修，正文里散着但没成篇 |
| 4 | `SKILL.md` | 插入 1 节 + 改 2 处 | 把自检和档位选择放到开工前；凭证位置改成分级说明 |

---

## 1. `scripts/dfs.py`

### 1a. 新增 `env_search_paths()`

按优先级返回四个 `.env` 位置，`creds()` 和 `healthcheck.py` 共用这一个函数，保证口径一致：

```python
def env_search_paths():
    here = os.path.dirname(os.path.abspath(__file__))
    skill_root = os.path.dirname(here)
    return [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(here, ".env"),
        os.path.join(skill_root, ".env"),
        os.path.expanduser("~/.workbuddy/secrets/dataforseo.env"),
    ]
```

### 1b. `creds()` 改为遍历 5 个位置 + 报错列出全部找过的位置

- 签名改成 `creds(verbose=False)`，`verbose=True` 时在 stderr 打印命中的文件（**不打印凭证值**）
- 全部失败时报错里逐条列出 `tried` 路径，替用户省掉「到底该放哪」这一轮猜
- 报错末尾指到 `references/本地部署与快速开始.md`

### 1c. 文件头 docstring 的「凭证」段同步改写

---

## 2. `scripts/healthcheck.py`（新增）

一条命令查六项，默认不花钱（`/v3/appendix/user_data` 是免费端点，用来验证凭证并读余额）：

1. Python ≥ 3.8
2. 7 个脚本 + 6 篇参考 + SKILL.md 是否齐全
3. 6 个 `.py` 逐个 `py_compile`
4. 是否只依赖标准库（复现「不用 pip install」的承诺）
5. 凭证：在哪、全不全、**有效没效、余额多少**
6. 网络：谷歌下拉 / RDAP / 苹果商店 / DataForSEO；另查代理环境变量

参数：`--quiet` 只打印问题项，`--offline` 跳过网络检查。

退出码：0 = 可开工，1 = 有硬阻塞。

---

## 3. `SKILL.md`

### 3a. 在 `## 怎么开始` 前插入 `## 开工前：跑一次自检`

含三档强度表（轻量 $0 / 标准 $0.4 / 完整 $1–1.5）和「三档判断标准完全一样」这句，防止 AI 在轻量档下擅自降低判定门槛。

### 3b. `## 工具` 章凭证那一条

改为说明查找顺序（5 个位置，含软链两侧），标注「推荐放 skill 根目录」，并指向 healthcheck。

### 3c. `## 做不了时怎么办` 表

凭证那一行的「先这样办」列由空改为「跑 healthcheck.py，它会列出找过的全部位置」。

---

## 升级后怎么重放

```bash
S=~/.scys-market/skills/money-keywords

# 1. 备份新版本，留回滚点
cp -R "$S/current/." "$S/.pre-patch-$(date +%Y%m%d)"

# 2. 拷两个新增文件（从旧的 patched 版本目录拷，别从 .original 拷）
cp versions/1.0.1/scripts/healthcheck.py          "$S/current/scripts/"
cp versions/1.0.1/references/本地部署与快速开始.md  "$S/current/references/"

# 3. dfs.py 的两处改动需要手工重打（新版可能已经改了这段）
diff -u "$S/.original-1.0.1/scripts/dfs.py" versions/1.0.1/scripts/dfs.py

# 4. SKILL.md 的三处改动同样手工重打
diff -u "$S/.original-1.0.1/SKILL.md" versions/1.0.1/SKILL.md

# 5. 重跑自检
python3 "$S/current/scripts/healthcheck.py"
```

> 如果新版 `dfs.py` 已经支持多级查找 `.env`，跳过 1a/1b，只保留 healthcheck。

---

## 没改动的地方（有意为之）

- **没有压缩 SKILL.md 正文。** 686 行里有大量实测校准数字（比如「两个月和四个月之间为什么单分一档」），删掉会让判定失准。触发成本的问题另外算。
- **没有改任何评分阈值、档位定义、判定规则。** 作者的方法论原样保留。
- **没有碰 `manifest.json`。** 它的 `files[].sha256` 校验的是原始文件，本地改动后该字段与实际不再一致；这只影响服务端变更检测，不影响本机运行。
