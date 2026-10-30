# -*- coding: utf-8 -*-
"""入口自检：页面能不能打开、首页卡片和路由对不对得上、页面内链接有没有死链

不连接真实数据库（用 stub 顶替），可以在本机或 CI 里随时跑：
    python tools/check_entries.py

检查三件事：
1. 所有 GET 路由都返回 200（含首页、各表单页、healthz）
2. 首页卡片指向的地址都能命中路由（无死链）
3. 每个页面 HTML 里的站内链接都能命中路由（无死链）
   以及反向：有路由但首页没有入口的「孤立页面」（healthz / api 除外）

退出码：0 全部通过；1 有 FAIL（有死链或页面打不开）

注意：本目录不能加 __init__.py——webTool/ 下已有 tools.py（随机姓名/手机号等），
一旦 tools/ 变成真正的包，`from tools import randname` 会改指向本目录而报 ImportError。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(HERE)
sys.path.insert(0, WEB)
os.chdir(WEB)

# 操作记录查询页未配置密码时返回 403（设计如此），自检时给个临时密码，
# 否则会把「故意关闭」误报成页面打不开
os.environ.setdefault('AUDIT_VIEW_PASSWORD', 'entries-selfcheck')

import app as appmod  # noqa: E402
from config import current_config as config  # noqa: E402

BASE = config.BASE_PATH

# 不需要首页入口的页面：健康检查、API
ORPHAN_ALLOW = {BASE + '/', BASE + '/healthz', BASE + '/api/cropMature', BASE + '/api/sql'}


class StubDB:
    """GET 页面只用到这两个查询，返回空列表即可渲染"""

    CROP_MATURE_ACTIONS = ('farm', 'machine', 'fish')

    def ping(self):
        return True

    def select_gift_info(self):
        return []

    def select_games_info(self):
        return []


fails = []
warns = []


def ok(msg):
    print('PASS  ' + msg)


def fail(msg):
    fails.append(msg)
    print('FAIL  ' + msg)


def warn(msg):
    warns.append(msg)
    print('WARN  ' + msg)


appmod.db = StubDB()
client = appmod.app.test_client()

# ---------- 1. 路由清单 ----------
rules = sorted(appmod.app.url_map.iter_rules(), key=lambda r: r.rule)
get_rules = [r.rule for r in rules if 'GET' in r.methods]
static_like = [r for r in get_rules if '<' in r]  # 带变量的路由不直接测

print('GET 路由 %d 个，其中带参数 %d 个（跳过直连）' % (len(get_rules), len(static_like)))
for rule in get_rules:
    if rule in static_like:
        continue
    resp = client.get(rule)
    if resp.status_code != 200:
        fail('页面 %s 返回 %s' % (rule, resp.status_code))
        continue
    if rule.endswith('/healthz'):
        if not resp.is_json or resp.json.get('status') != 'ok':
            fail('healthz 返回内容异常：%s' % resp.data[:120])
        else:
            ok('%s 200 (json ok)' % rule)
        continue
    if 'text/html' not in (resp.headers.get('Content-Type') or ''):
        fail('%s Content-Type 不是 html：%s' % (rule, resp.headers.get('Content-Type')))
    else:
        ok('%s 200' % rule)

# ---------- 2. 首页卡片 <-> 路由 ----------
home = client.get(BASE + '/').get_data(as_text=True)
card_links = sorted(set(re.findall(r'href="(%s/[^"#?]*)"' % re.escape(BASE), home)))
route_set = set(get_rules)
for link in card_links:
    if link not in route_set:
        fail('首页卡片指向不存在的路由：%s' % link)
    else:
        ok('首页卡片 -> %s' % link)

# 反向：有页面但没有入口
for rule in get_rules:
    if rule in ORPHAN_ALLOW or '<' in rule:
        continue
    if rule not in card_links:
        warn('孤立入口（有页面但首页没有卡片）：%s' % rule)

# ---------- 3. 各页面内链接 ----------
for rule in get_rules:
    if '<' in rule or rule.endswith('/healthz'):
        continue
    body = client.get(rule).get_data(as_text=True)
    inner = set(re.findall(r'href="(%s/[^"#?]*)"' % re.escape(BASE), body))
    inner |= set(re.findall(r'action="(%s/[^"#?]*)"' % re.escape(BASE), body))
    dead = sorted(l for l in inner if l not in route_set)
    if dead:
        fail('%s 里存在死链：%s' % (rule, ', '.join(dead)))

# ---------- 结果 ----------
print('')
if warns:
    print('孤立入口 %d 个（不阻断，建议补卡片或确认废弃）：' % len(warns))
    for w in warns:
        print('    ' + w)
print('FAIL %d 个，WARN %d 个' % (len(fails), len(warns)))
if fails:
    print('ENTRIES_FAIL')
    sys.exit(1)
print('ENTRIES_OK')
