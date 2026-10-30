# -*- coding: utf-8 -*-
"""
操作审计：落盘「谁、什么时间、从哪个 IP、对哪个 uid、做了什么、结果如何」

- 只记录写操作（POST/PUT/PATCH/DELETE），GET 页面访问不记录
- 按天写入 JSONL：<AUDIT_LOG_DIR>/audit-YYYYMMDD.jsonl，默认 webTool/logs/
- 同时输出一行摘要到 stdout（journald），journalctl -u web2026 可直接看到
- 审计本身绝不影响业务：record() 内部吞掉所有异常，只降级为一条 print
- 请求体只挑白名单字段，避免把身份证、令牌等无关内容写进日志
"""
import collections
import json
import os
import time

from flask import g, request

from config import current_config as config

WRITE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')

# 路由函数名 -> 业务动作（新增路由时补一行）
ENDPOINT_ACTIONS = {
    'add_money': '加钻石',
    'id_change': '改身份证',
    'insert_person': '插入人员',
    'sql_demo': '查询操作记录',
    'create_room': '创建房间',
    'pay': '充值',
    'add_commodity': '加商品',
    'add_exp': '加经验',
    'update_user_fragment': '改碎片',
    'insert_broker': '公会操作',
    'add_games': '加游戏记录',
    'crop_price': '作物售价计算',
    'crop_mature': '作物成熟',
    'execute_sql': '只读SQL查询',
}

# 只记录这些请求字段；不在白名单里的一律不落盘
PARAM_KEYS = (
    'uid', 'money', 'bid', 'app_id', 'identity_type', 'want_type', 'action',
    'num', 'cids', 'count', 'type', 'name', 'rank', 'phone', 'id_card',
    'star_score', 'fragment_num', 'sql', 'remark', 'room_name', 'game_id',
)
SENSITIVE_HINTS = ('token', 'password', 'pwd', 'secret', 'auth')
MAX_VALUE_LEN = 200


def _client_ip():
    """优先取网关透传的真实 IP（X-Forwarded-For 可被伪造，仅作参考）"""
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or ''


def _request_data():
    """取请求体；413 等异常情况下返回空 dict"""
    try:
        if request.is_json:
            return request.get_json(silent=True) or {}
        return request.form.to_dict()
    except Exception:
        return {}


def _clean_params(data):
    """按白名单挑字段，敏感键打码，超长截断"""
    cleaned = {}
    for key in PARAM_KEYS:
        if key not in data:
            continue
        value = data.get(key)
        if any(hint in key.lower() for hint in SENSITIVE_HINTS):
            cleaned[key] = '***'
            continue
        text = str(value)
        if len(text) > MAX_VALUE_LEN:
            text = text[:MAX_VALUE_LEN] + '...(截断)'
        cleaned[key] = text
    return cleaned


def _result_of(response):
    """把响应归类成便于检索的结果标签"""
    if response.status_code >= 500:
        return 'error'
    if response.status_code == 403:
        return 'blocked'
    if response.status_code >= 400:
        return 'rejected'
    payload = response.get_json(silent=True)
    if isinstance(payload, dict) and payload.get('success') is False:
        return 'failed'
    return 'ok'


def _log_dir():
    directory = getattr(config, 'AUDIT_LOG_DIR', '') or os.path.join(os.getcwd(), 'logs')
    return directory


def _append(line):
    directory = _log_dir()
    os.makedirs(directory, exist_ok=True)
    filename = 'audit-%s.jsonl' % time.strftime('%Y%m%d')
    with open(os.path.join(directory, filename), 'a', encoding='utf-8') as fp:
        fp.write(line + '\n')


def log_status():
    """返回 (日志目录, 文件个数)，供查询页在没数据时自证「到底读的哪儿」"""
    directory = _log_dir()
    if not os.path.isdir(directory):
        return directory, 0
    return directory, sum(
        1 for n in os.listdir(directory)
        if n.startswith('audit-') and n.endswith('.jsonl')
    )


def recent(limit=10, max_files=7):
    """取最近的审计记录（新 -> 旧）

    只扫最近 max_files 个按天文件，避免日志攒多以后每次都把磁盘读一遍。
    单文件内用 deque(maxlen=limit) 只留最后 N 条，不把整个文件读进内存；
    损坏行（写到一半被杀、手改坏了）直接跳过，不让一条脏数据毁掉整页。
    """
    directory = _log_dir()
    if not os.path.isdir(directory):
        return []
    names = sorted(
        (n for n in os.listdir(directory)
         if n.startswith('audit-') and n.endswith('.jsonl')),
        reverse=True,
    )[:max_files]

    rows = []
    for name in names:
        kept = collections.deque(maxlen=limit)
        try:
            with open(os.path.join(directory, name), encoding='utf-8') as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        kept.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            continue
        rows.extend(reversed(kept))
        if len(rows) >= limit:
            return rows[:limit]
    return rows


def record(response):
    """由 after_request 调用；任何异常都不允许往外抛"""
    if request.method not in WRITE_METHODS:
        return
    try:
        data = _request_data()
        started = g.get('_audit_start') or time.time()
        entry = {
            'ts': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'ip': _client_ip(),
            'remote': request.remote_addr or '',
            'user': (request.authorization.username if request.authorization else '') or '',
            'method': request.method,
            'endpoint': request.endpoint or '',
            'action': ENDPOINT_ACTIONS.get(request.endpoint, request.endpoint or ''),
            'path': request.path,
            'uid': str(data.get('uid', '') or ''),
            'params': _clean_params(data),
            'status': response.status_code,
            'result': _result_of(response),
            'ms': int((time.time() - started) * 1000),
            'ua': (request.headers.get('User-Agent') or '')[:120],
        }
        _append(json.dumps(entry, ensure_ascii=False))
        print('[AUDIT] {action} uid={uid} ip={ip} -> {result}({status}) {ms}ms'.format(**entry))
    except Exception as exc:  # 审计失败不影响业务
        print(f'审计日志写入失败: {exc}')
