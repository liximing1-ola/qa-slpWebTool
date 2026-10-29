# -*- coding: utf-8 -*-
"""web2026 回归测试：路由行为 + 成长值查表等价性 + sqlite 上的事务/金额/上限行为

用法（在 webTool 目录下执行）：
    python tests/run_tests.py

不依赖真实 MySQL：数据库相关用例走 stub 与内存 sqlite（含 ATTACH 模拟跨库前缀）。
全部通过时打印 ALL_OK 并退出码 0，任一失败退出码 1。
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(HERE)
sys.path.insert(0, WEB)
os.chdir(WEB)
for k in ('SQL_API_TOKEN', 'BASIC_AUTH_USER', 'BASIC_AUTH_PASSWORD'):
    os.environ.pop(k, None)

from sqlalchemy import create_engine

import config
import database
import app as appmod

RESULTS = []


def check(name, ok, extra=''):
    RESULTS.append((name, bool(ok)))
    print(('PASS  ' if ok else 'FAIL  ') + name + (('  | ' + str(extra)) if extra else ''))


# ==================== 1. 页面与入口 ====================
client = appmod.app.test_client()
r = client.get('/web2026/')
html = r.get_data(as_text=True)
check('首页返回 200', r.status_code == 200, r.status_code)
check('CI 打包入口存在', 'http://172.19.37.71:8080/' in html)
check('首页卡片数量 15', html.count('class="card"') == 15, html.count('class="card"'))
check('首页有「查询人员信息」入口', 'href="/web2026/sqlDemo"' in html)

for path in ('/web2026/add', '/web2026/addExp', '/web2026/addCommodity', '/web2026/addfragment',
             '/web2026/createRoom', '/web2026/idChange', '/web2026/insertPerson', '/web2026/insertbroker',
             '/web2026/pay', '/web2026/sqlDemo', '/web2026/cropPrice'):
    rr = client.get(path)
    check(f'GET {path}', rr.status_code == 200, rr.status_code)

rr = client.get('/web2026/cropPrice')
page = rr.get_data(as_text=True)
check('作物成熟按钮已改走 api/cropMature', '/web2026/api/cropMature' in page)
check('页面不再直接调用 api/sql', '/api/sql' not in page)

rr = client.get('/web2026/not-exist')
check('404 非 AJAX 返回 HTML', rr.status_code == 404, rr.status_code)
rr = client.get('/web2026/not-exist', headers={'X-Requested-With': 'XMLHttpRequest'})
check('404 AJAX 返回 JSON', rr.status_code == 404 and rr.is_json and rr.json.get('success') is False, rr.data[:80])

# ==================== 2. 成长值查表等价性 ====================
OLD_A = {"0": 0, "10": 0, "20": 200, "30": 800, "40": 2500, "50": 10000, "60": 25000,
         "70": 65000, "80": 150000, "90": 500000, "100": 2000000}
OLD_B = {"0": 0, "10": 0, "20": 200, "30": 1000, "40": 3000, "50": 12000, "60": 30000,
         "70": 80000, "80": 200000, "90": 600000, "100": 2600000}
OLD_C = {"0": 0, "10": 0, "20": 600, "30": 3000, "40": 10000, "50": 40000, "60": 100000,
         "70": 250000, "80": 600000, "90": 2000000, "100": 8000000}


def old_lookup(app_id, identity, level):
    if app_id == 66:
        m = OLD_A
    elif app_id == 70:
        m = OLD_B if identity == 'anchor' else OLD_C
    else:
        m = OLD_A
    return m.get(level, 0)


mismatch = []
for app_id in (66, 70, 99):
    for identity in ('anchor', 'user'):
        growth = appmod.TITLE_GROWTH_BASE.get((str(app_id), identity), appmod.DEFAULT_TITLE_GROWTH)
        for level in [str(i) for i in range(0, 101, 10)]:
            if growth.get(level, 0) != old_lookup(app_id, identity, level):
                mismatch.append((app_id, identity, level))
check('爵位成长值与原逻辑完全一致', not mismatch, mismatch[:5])

# ==================== 3. 验证器边界 ====================
import validators as v

def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return False
    except v.ValidationError:
        return True

check('validate_num 10 通过', v.validate_num('10', max_val=10) == 10)
check('validate_num 11 被拦截', raises(v.validate_num, '11', max_val=10))
check('validate_num 0 通过(max=0)', v.validate_num('0', max_val=0) == 0)
check('validate_money 0 通过(max=0)', v.validate_money('0', max_amount=0) == 0)
check('validate_money 超限被拦截', raises(v.validate_money, '6', max_amount=5))

# ==================== 4. 路由行为（stub DB） ====================
class StubDB:
    def __init__(self):
        self.calls = []

    def update_money(self, *a, **kw):
        self.calls.append(('update_money', a, kw))
        return 1

    def switch_broker(self, *a, **kw):
        self.calls.append(('switch_broker', a, kw))
        return self.switch_ok

    def insert_people(self, *a, **kw):
        self.calls.append(('insert_people', a, kw))
        return True

    def pay(self, *a, **kw):
        self.calls.append(('pay', a, kw))
        return self.pay_result

    def insert_pay_change(self, *a, **kw):
        self.calls.append(('insert_pay_change', a, kw))
        return 1

    def execute_sql(self, sql):
        self.calls.append(('execute_sql', (sql,), {}))
        if 'update' in sql.lower():
            raise ValueError('仅支持只读查询（SELECT/SHOW/DESC/EXPLAIN）')
        return [{'1': 1}]

    CROP_MATURE_ACTIONS = ('farm', 'machine', 'fish')

    def crop_mature(self, action, uid):
        self.calls.append(('crop_mature', (action, uid), {}))
        return self.crop_result

    crop_result = 1
    ping_ok = True

    def ping(self):
        self.calls.append(('ping', (), {}))
        return self.ping_ok

    switch_ok = True
    pay_result = 'ORDER-1'


real_db = appmod.db
stub = StubDB()
appmod.db = stub
AJAX = {'X-Requested-With': 'XMLHttpRequest'}

r = client.post('/web2026/add', data={'uid': '200252633', 'money': '100'}, headers=AJAX)
check('addMoney 成功', r.is_json and r.json.get('success') is True, r.data[:120])
check('addMoney 按口径清零其它币种',
      stub.calls and stub.calls[-1][2] == {'money': 100, 'money_b': 0, 'money_cash': 0,
                                          'money_cash_b': 0, 'gold_coin': 0, 'money_debts': 0},
      stub.calls[-1] if stub.calls else '无调用')

stub.switch_ok = True
r = client.post('/web2026/insertbroker', data={'uid': '200252633', 'bid': '200000030', 'app_id': '66', 'want_type': 'join'}, headers=AJAX)
check('insertbroker join 成功', r.is_json and r.json.get('success') is True, r.data[:120])
check('insertbroker 走事务方法 join=True', stub.calls[-1][0] == 'switch_broker' and stub.calls[-1][2].get('join') is True, stub.calls[-1])

stub.switch_ok = False
r = client.post('/web2026/insertbroker', data={'uid': '200252633', 'app_id': '66', 'want_type': 'exit'}, headers=AJAX)
check('insertbroker 失败返回失败', r.is_json and r.json.get('success') is False, r.data[:120])

stub.pay_result = None
r = client.post('/web2026/pay', data={'uid': '200252633', 'money': '10'}, headers=AJAX)
check('pay 写库失败不再假成功', r.is_json and r.json.get('success') is False, r.data[:120])
stub.pay_result = 'ORDER-1'
r = client.post('/web2026/pay', data={'uid': '200252633', 'money': '10'}, headers=AJAX)
check('pay 成功路径正常', r.is_json and r.json.get('success') is True, r.data[:120])

r = client.post('/web2026/insertPerson', data={'rid': '200252633', 'num': '11', 'app_id': '66'}, headers=AJAX)
check('insertPerson 11 人被拦截', r.is_json and r.json.get('success') is False and '10' in r.json.get('message', ''), r.json if r.is_json else r.data[:120])
r = client.post('/web2026/insertPerson', data={'rid': '200252633', 'num': '10', 'app_id': '66'}, headers=AJAX)
check('insertPerson 10 人正常', r.is_json and r.json.get('success') is True, r.data[:120])

# /api/sql
r = client.post('/web2026/api/sql', json={'sql': 'select 1'})
check('/api/sql 未配置口令时关闭', r.status_code == 403, r.status_code)
config.current_config.SQL_API_TOKEN = 'tok'
r = client.post('/web2026/api/sql', json={'sql': 'select 1'})
check('/api/sql 无口令 401', r.status_code == 401, r.status_code)
r = client.post('/web2026/api/sql', json={'sql': 'update xs_user_money set money=1'},
                headers={'X-API-Token': 'tok'})
check('/api/sql 写语句被拒', r.status_code == 400, (r.status_code, r.data[:80]))
r = client.post('/web2026/api/sql', json={'sql': 'select 1'}, headers={'X-API-Token': 'tok'})
check('/api/sql 只读查询正常', r.status_code == 200 and r.json.get('success') is True, r.data[:120])
config.current_config.SQL_API_TOKEN = ''

# 一键成熟接口（原先前端拼 SQL 调 /api/sql）
r = client.post('/web2026/api/cropMature', json={'uid': '200252633', 'action': 'farm'}, headers=AJAX)
check('cropMature farm 成功', r.status_code == 200 and r.json.get('success') is True, r.data[:120])
check('cropMature 参数透传正确', stub.calls[-1][1] == ('farm', 200252633), stub.calls[-1])
r = client.post('/web2026/api/cropMature', json={'uid': '200252633', 'action': 'machine'}, headers=AJAX)
check('cropMature machine 成功', r.status_code == 200 and r.json.get('success') is True, r.data[:120])
r = client.post('/web2026/api/cropMature', json={'uid': '200252633', 'action': 'fish'}, headers=AJAX)
check('cropMature fish 成功', r.status_code == 200 and r.json.get('success') is True, r.data[:120])
r = client.post('/web2026/api/cropMature', json={'uid': '200252633', 'action': 'drop'}, headers=AJAX)
check('cropMature 非法操作 400', r.status_code == 400 and r.json.get('success') is False, r.data[:120])
r = client.post('/web2026/api/cropMature', json={'uid': '123', 'action': 'farm'}, headers=AJAX)
check('cropMature 非法 uid 400', r.status_code == 400, r.data[:160])
stub.crop_result = None
r = client.post('/web2026/api/cropMature', json={'uid': '200252633', 'action': 'farm'}, headers=AJAX)
check('cropMature 未找到农场 404', r.status_code == 404 and '农场' in r.json.get('message', ''), r.data[:160])
stub.crop_result = False
r = client.post('/web2026/api/cropMature', json={'uid': '200252633', 'action': 'farm'}, headers=AJAX)
check('cropMature 执行失败 500', r.status_code == 500, r.status_code)
stub.crop_result = 2
r = client.post('/web2026/api/cropMature', json={'uid': '200252633', 'action': 'fish'}, headers=AJAX)
check('cropMature 返回影响行数', r.json.get('rowcount') == 2, r.data[:120])

# 平台认证开关
r = client.get('/web2026/')
check('默认不启用认证', r.status_code == 200, r.status_code)
config.current_config.BASIC_AUTH_USER = 'u'
config.current_config.BASIC_AUTH_PASSWORD = 'p'
r = client.get('/web2026/')
check('开启认证后未带凭据 401', r.status_code == 401, r.status_code)
import base64
hdr = {'Authorization': 'Basic ' + base64.b64encode(b'u:p').decode()}
r = client.get('/web2026/', headers=hdr)
check('开启认证后带正确凭据 200', r.status_code == 200, r.status_code)
r = client.get('/web2026/healthz')
check('开启认证时 healthz 仍放行（给监控用）',
      r.status_code == 200 and r.json.get('status') == 'ok', r.status_code)
config.current_config.BASIC_AUTH_USER = ''
config.current_config.BASIC_AUTH_PASSWORD = ''

# 健康检查
stub.ping_ok = True
before = len(stub.calls)
r = client.get('/web2026/healthz')
check('healthz 200', r.status_code == 200 and r.json.get('status') == 'ok', r.data[:150])
check('healthz 默认不查库', r.json.get('db') is None and len(stub.calls) == before, stub.calls[before:])
r = client.get('/web2026/healthz?db=1')
check('healthz?db=1 探测成功 200', r.status_code == 200 and r.json.get('db') == 'ok', r.data[:150])
stub.ping_ok = False
r = client.get('/web2026/healthz?db=1')
check('healthz?db=1 数据库故障 503', r.status_code == 503 and r.json.get('status') == 'degraded', r.data[:150])
stub.ping_ok = True

# 安全响应头
r = client.get('/web2026/')
check('安全头 nosniff', r.headers.get('X-Content-Type-Options') == 'nosniff', dict(r.headers))
check('安全头 X-Frame-Options', r.headers.get('X-Frame-Options') == 'SAMEORIGIN', dict(r.headers))
check('安全头 Referrer-Policy', r.headers.get('Referrer-Policy') == 'same-origin', dict(r.headers))

# 跨站写请求（幂等写法：先记已有调用数，避免依赖上一条用例）
before = len(stub.calls)
r = client.post('/web2026/add', data={'uid': '200252633', 'money': '100'},
                headers={'Origin': 'http://evil.example.com'})
check('跨站 POST 被拦 403', r.status_code == 403 and r.json.get('success') is False, r.status_code)
check('跨站 POST 未落库', len(stub.calls) == before, stub.calls[before:])
r = client.post('/web2026/add', data={'uid': '200252633', 'money': '100'},
                headers=dict(AJAX, Origin='http://localhost'))
check('同源 POST 放行', r.status_code == 200 and r.json.get('success') is True, r.status_code)
r = client.post('/web2026/add', data={'uid': '200252633', 'money': '100'},
                headers=dict(AJAX, Referer='http://localhost/web2026/add'))
check('带同源 Referer 放行', r.status_code == 200, r.status_code)
r = client.post('/web2026/add', data={'uid': '200252633', 'money': '100'},
                headers=dict(AJAX, Origin='http://114.55.3.96', **{'X-Forwarded-Host': '114.55.3.96'}))
check('网关改写 Host 时按 X-Forwarded-Host 放行', r.status_code == 200, r.status_code)
r = client.post('/web2026/add', data={'uid': '200252633', 'money': '100'},
                headers=dict(AJAX, Origin='null'))
check('Origin 为 null 不误拦', r.status_code == 200, r.status_code)

# 请求体超限
big = 'x' * (config.current_config.MAX_CONTENT_LENGTH + 1024)
r = client.post('/web2026/add', data={'uid': '200252633', 'money': '1', 'pad': big}, headers=AJAX)
check('请求体超限 413', r.status_code == 413 and r.json.get('success') is False, r.status_code)

# ==================== 4.1 操作审计 ====================
import json as _json
import tempfile

audit_dir = tempfile.mkdtemp(prefix='web2026-audit-')
config.current_config.AUDIT_LOG_DIR = audit_dir


def audit_lines():
    path = os.path.join(audit_dir, 'audit-%s.jsonl' % time.strftime('%Y%m%d'))
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as fp:
        return [_json.loads(line) for line in fp if line.strip()]


client.post('/web2026/add', data={'uid': '200252633', 'money': '100'}, headers=AJAX)
entries = audit_lines()
check('审计：记录写操作', len(entries) == 1, entries)
entry = entries[-1] if entries else {}
check('审计：动作名与 uid', entry.get('action') == '加钻石' and entry.get('uid') == '200252633', entry)
check('审计：参数按白名单记录', (entry.get('params') or {}).get('money') == '100', entry.get('params'))
check('审计：结果与状态码', entry.get('result') == 'ok' and entry.get('status') == 200, entry.get('result'))
check('审计：含来源 IP 与耗时', bool(entry.get('ip')) and isinstance(entry.get('ms'), int),
      (entry.get('ip'), entry.get('ms')))

client.get('/web2026/')
check('审计：GET 不记录', len(audit_lines()) == 1, len(audit_lines()))

client.post('/web2026/add', data={'uid': '200252633', 'money': '1'},
            headers={'Origin': 'http://evil.example.com'})
check('审计：被拦截的请求也记录', audit_lines()[-1].get('result') == 'blocked', audit_lines()[-1])

# 表单校验失败必须是 400，否则审计会把失败记成 ok（旧行为是 200）
r = client.post('/web2026/add', data={'uid': '1', 'money': '1'}, headers=AJAX)
check('校验失败返回 400（AJAX）', r.status_code == 400 and r.json.get('success') is False, r.status_code)
last = audit_lines()[-1]
check('审计：校验失败记为 rejected', last.get('result') == 'rejected' and last.get('status') == 400, last)
r = client.post('/web2026/add', data={'uid': '1', 'money': '1'})
check('校验失败返回 400（页面形态）', r.status_code == 400 and '用户ID必须是' in r.get_data(as_text=True), r.status_code)

client.post('/web2026/api/sql', json={'sql': 'SELECT 1', 'token': 'should-not-log'}, headers=AJAX)
last = audit_lines()[-1]
check('审计：SQL 动作与语句', last.get('action') == '只读SQL查询'
      and (last.get('params') or {}).get('sql') == 'SELECT 1', last.get('params'))
check('审计：敏感字段不落盘', 'token' not in (last.get('params') or {}), last.get('params'))

# 审计目录不可写（指到一个已存在的文件）时不能影响业务
blocker = os.path.join(audit_dir, 'blocker-file')
with open(blocker, 'w', encoding='utf-8') as fp:
    fp.write('x')
audit_backup = config.current_config.AUDIT_LOG_DIR
config.current_config.AUDIT_LOG_DIR = blocker
r = client.post('/web2026/add', data={'uid': '200252633', 'money': '100'}, headers=AJAX)
check('审计：写失败不影响请求', r.status_code == 200 and r.json.get('success') is True, r.status_code)
config.current_config.AUDIT_LOG_DIR = audit_backup

appmod.db = real_db

# 连接超时配置（用 mock 拦 create_engine，只看建池参数，不建真实连接）
from unittest import mock
probe = database.Database.__new__(database.Database)
probe._initialized = False
with mock.patch.object(database, 'create_engine') as fake_create:
    database.Database.__init__(probe)
kw = fake_create.call_args.kwargs
check('连接池等待超时已生效', kw.get('pool_timeout') == config.current_config.DB_POOL_TIMEOUT,
      kw.get('pool_timeout'))
check('建立连接超时已生效',
      kw.get('connect_args', {}).get('connect_timeout') == config.current_config.DB_CONNECT_TIMEOUT,
      kw.get('connect_args'))
check('连接池健康检测已开启', kw.get('pool_pre_ping') is True, kw.get('pool_pre_ping'))

# ==================== 5. sqlite 上的真实 SQL 行为 ====================
engine = create_engine('sqlite://')

from sqlalchemy import event


@event.listens_for(engine, 'connect')
def _register_mysql_funcs(dbapi_conn, _record):
    # sqlite 没有 MySQL 的 UNIX_TIMESTAMP()，注册一个等价实现
    dbapi_conn.create_function('UNIX_TIMESTAMP', 0, lambda: int(time.time()))

FULL_BROKER = ('CREATE TABLE xianshi.xs_broker_user (bid INT, uid INT, app_id INT, deleted INT, '
               'dateline INT, state INT, "exit" INT, pack_cal INT, sign INT, corp_cal INT, '
               'corp_status INT, is_risk INT, apply_time INT)')
CHECK_BROKER = ('CREATE TABLE xianshi.xs_broker_user (bid INT, uid INT, app_id INT, deleted INT, '
                'dateline INT, state INT, "exit" INT, pack_cal INT, sign INT, corp_cal INT, '
                'corp_status INT, is_risk INT CHECK (is_risk = 1), apply_time INT)')

with engine.connect() as c:
    c.exec_driver_sql("ATTACH DATABASE ':memory:' AS xianshi")
    c.exec_driver_sql("CREATE TABLE xs_user_money (uid INT PRIMARY KEY, money BIGINT, money_b BIGINT, "
                      "money_cash BIGINT, money_cash_b BIGINT, gold_coin BIGINT, money_debts BIGINT)")
    c.exec_driver_sql("CREATE TABLE xs_user_commodity (uid INT, cid INT, state INT, num INT, period_end INT, "
                      "used INT, in_use INT, dateline TEXT)")
    c.exec_driver_sql("CREATE TABLE xs_user_fragment (uid INT, app_id INT, star_score INT, "
                      "fragment_num INT NOT NULL, update_time INT, create_time INT)")
    c.exec_driver_sql("CREATE TABLE xs_chatroom_config (rid INT, position INT, app_id INT, uid INT)")
    c.commit()

t_db = database.Database.__new__(database.Database)
t_db._initialized = True
t_db.engine = engine
check('ping 在可用库上返回 True', t_db.ping() is True, '')


def rows(sql, **p):
    with engine.connect() as c:
        return [dict(x._mapping) for x in c.exec_driver_sql(sql, p or None).fetchall()]


with engine.connect() as c:
    c.exec_driver_sql("INSERT INTO xs_user_money VALUES (200252633, 1, 2, 3, 4, 5, 6)")
    c.commit()

t_db.update_money(200252633, money=100)
row = rows("SELECT * FROM xs_user_money WHERE uid=:uid", uid=200252633)[0]
check('update_money 只传 money 时只改 money', row['money'] == 100, row)
check('update_money 未传字段保持原值', (row['money_b'], row['money_cash'], row['money_cash_b'],
                                       row['gold_coin'], row['money_debts']) == (2, 3, 4, 5, 6), row)

# 加钻石（addMoney 入口传全 6 个字段）→ 其它币种应被清零
t_db.update_money(200252633, money=100, money_b=0, money_cash=0, money_cash_b=0,
                  gold_coin=0, money_debts=0)
row = rows("SELECT * FROM xs_user_money WHERE uid=:uid", uid=200252633)[0]
check('加钻石后 money 为传入值', row['money'] == 100, row)
check('加钻石后其它币种全部清零', (row['money_b'], row['money_cash'], row['money_cash_b'],
                                  row['gold_coin'], row['money_debts']) == (0, 0, 0, 0, 0), row)

t_db.update_money(200252633, gold_coin=7)
row = rows("SELECT * FROM xs_user_money WHERE uid=:uid", uid=200252633)[0]
check('update_money 只改 gold_coin', row['gold_coin'] == 7 and row['money'] == 100, row)
check('update_money 无字段返回 None', t_db.update_money(200252633) is None)

# 房间加人
with engine.connect() as c:
    for pos in range(12):
        c.exec_driver_sql("INSERT INTO xs_chatroom_config VALUES (200252633, ?, 66, NULL)", (pos,))
    c.commit()
check('insert_people 10 人成功', t_db.insert_people(10, 200252633, 66) is True)
filled = rows("SELECT COUNT(*) n FROM xs_chatroom_config WHERE uid IS NOT NULL")[0]['n']
check('insert_people 实际写入 10 行', filled == 10, filled)
check('insert_people 11 人被拒绝', t_db.insert_people(11, 200252633, 66) is False)
filled = rows("SELECT COUNT(*) n FROM xs_chatroom_config WHERE uid IS NOT NULL")[0]['n']
check('insert_people 被拒后无额外写入', filled == 10, filled)

# 背包：失败回滚
with engine.connect() as c:
    c.exec_driver_sql("INSERT INTO xs_user_commodity (uid, cid, num) VALUES (200252633, 111, 1), (200252633, 222, 1)")
    c.commit()
ok = t_db.add_commodity(200252633, cids=[329, 'x'], num=3)
kept = rows("SELECT cid FROM xs_user_commodity WHERE uid=:uid", uid=200252633)
check('add_commodity 失败返回 False', ok is False)
check('add_commodity 失败后旧数据仍在', [k['cid'] for k in kept] == [111, 222], kept)
ok = t_db.add_commodity(200252633, cids=[329, 330], num=3)
new = rows("SELECT cid, num FROM xs_user_commodity WHERE uid=:uid", uid=200252633)
check('add_commodity 成功写入 2 条', ok is True and [n['cid'] for n in new] == [329, 330], new)
check('add_commodity num 生效', all(n['num'] == 3 for n in new), new)

# 碎片：插入失败回滚删除
with engine.connect() as c:
    c.exec_driver_sql("INSERT INTO xs_user_fragment VALUES (200252633, 66, 0, 9, 1, 1)")
    c.commit()
ok = t_db.update_user_fragment(200252633, None, 66)
left = rows("SELECT fragment_num FROM xs_user_fragment WHERE uid=:uid", uid=200252633)
check('update_user_fragment 失败返回 False', ok is False)
check('update_user_fragment 失败后旧记录仍在', [x['fragment_num'] for x in left] == [9], left)
ok = t_db.update_user_fragment(200252633, 5, 66)
left = rows("SELECT fragment_num FROM xs_user_fragment WHERE uid=:uid", uid=200252633)
check('update_user_fragment 成功覆盖', ok is True and [x['fragment_num'] for x in left] == [5], left)

# 公会：插入失败不误退会
with engine.connect() as c:
    c.exec_driver_sql(CHECK_BROKER)
    c.exec_driver_sql("INSERT INTO xianshi.xs_broker_user (bid, uid, app_id) VALUES (1, 200252633, 66)")
    c.commit()
ok = t_db.switch_broker(200252633, 200000030, 66, join=True)
left = rows("SELECT bid FROM xianshi.xs_broker_user WHERE uid=:uid", uid=200252633)
check('switch_broker 插入失败返回 False', ok is False)
check('switch_broker 失败后原公会关系仍在', [x['bid'] for x in left] == [1], left)

with engine.connect() as c:
    c.exec_driver_sql("DROP TABLE xianshi.xs_broker_user")
    c.exec_driver_sql(FULL_BROKER)
    c.commit()
ok = t_db.switch_broker(200252633, 200000030, 66, join=True)
left = rows("SELECT bid, app_id, state FROM xianshi.xs_broker_user WHERE uid=:uid", uid=200252633)
check('switch_broker join 成功', ok is True and [x['bid'] for x in left] == [200000030], left)
ok = t_db.switch_broker(200252633, 200000030, 66, join=False)
left = rows("SELECT bid FROM xianshi.xs_broker_user WHERE uid=:uid", uid=200252633)
check('switch_broker exit 成功', ok is True and left == [], left)

# execute / execute_sql
n = t_db.execute("UPDATE xs_user_money SET money=:m WHERE uid=:uid", {'m': 50, 'uid': 200252633})
check('execute 返回影响行数', n == 1, n)
try:
    t_db.execute_sql('DELETE FROM xs_user_money')
    blocked = False
except ValueError:
    blocked = True
check('execute_sql 拦截写语句', blocked)
ok_rows = t_db.execute_sql('select 1 as v')
check('execute_sql 只读查询可用', ok_rows == [{'v': 1}], ok_rows)

# 一键成熟（原先前端拼 SQL 的三个按钮）
with engine.connect() as c:
    c.exec_driver_sql("ATTACH DATABASE ':memory:' AS starship")
    c.exec_driver_sql("CREATE TABLE starship.xs_farm_info (id INT, belong_uid INT)")
    c.exec_driver_sql("CREATE TABLE starship.xs_farm_plot (farm_id INT, crop_state1_time BIGINT, crop_state2_time BIGINT)")
    c.exec_driver_sql("CREATE TABLE starship.xs_farm_machine (belong_uid INT, status INT, fruit_id INT)")
    c.exec_driver_sql("CREATE TABLE starship.xs_fishpond_user (belong_uid INT, fishing_state_time BIGINT)")
    c.exec_driver_sql("INSERT INTO starship.xs_farm_info VALUES (777, 200252633)")
    c.exec_driver_sql("INSERT INTO starship.xs_farm_plot VALUES (777, 0, 0)")
    c.exec_driver_sql("INSERT INTO starship.xs_farm_machine VALUES (200252633, 0, 5), (200252633, 0, 0)")
    c.exec_driver_sql("INSERT INTO starship.xs_fishpond_user VALUES (200252633, 0)")
    c.commit()

now = int(time.time())
n = t_db.crop_mature('farm', 200252633)
plot = rows("SELECT crop_state1_time, crop_state2_time FROM starship.xs_farm_plot WHERE farm_id=777")[0]
check('crop_mature farm 影响 1 行', n == 1, n)
check('crop_mature farm 时间回拨 1 小时',
      0 < plot['crop_state1_time'] <= now and abs(plot['crop_state2_time'] - plot['crop_state1_time']) <= 1, plot)

n = t_db.crop_mature('machine', 200252633)
mach = rows("SELECT fruit_id, status FROM starship.xs_farm_machine WHERE belong_uid=:uid ORDER BY fruit_id", uid=200252633)
check('crop_mature machine 只处理 fruit_id>0', n == 1, n)
check('crop_mature machine 状态置 2',
      [m['status'] for m in mach] == [0, 2], mach)

n = t_db.crop_mature('fish', 200252633)
fish = rows("SELECT fishing_state_time FROM starship.xs_fishpond_user WHERE belong_uid=:uid", uid=200252633)[0]
check('crop_mature fish 影响 1 行', n == 1, n)
check('crop_mature fish 时间回拨 1 小时', 0 < fish['fishing_state_time'] <= now, fish)

check('crop_mature 未找到农场返回 None', t_db.crop_mature('farm', 200000001) is None)
try:
    t_db.crop_mature('drop', 200252633)
    blocked = False
except ValueError:
    blocked = True
check('crop_mature 非法操作被拦截', blocked)

# ==================== 汇总 ====================
bad = [n for n, ok in RESULTS if not ok]
print('\n合计 %d 项，失败 %d 项' % (len(RESULTS), len(bad)))
if bad:
    for n in bad:
        print('  FAILED:', n)
    sys.exit(1)
print('ALL_OK')
