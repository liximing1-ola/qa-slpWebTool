# -*- coding: utf-8 -*-
"""
Flask应用主入口 - 优化版本
"""
import time
import urllib3
from flask import Flask, render_template, request, jsonify, Response, g
from urllib.parse import urlparse
import requests

import audit
from config import current_config as config
from database import db
from validators import (
    validate_uid, validate_rid, validate_money, validate_num,
    validate_cids, handle_form_error, handle_success, form_validator,
    ValidationError
)

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

# 会修改数据的请求方法
WRITE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')


# 爵位成长值基数：按 (app_id, 身份类型) 分组，值与原配置保持一致
TITLE_GROWTH_BASE = {
    ('66', 'user'): {
        "0": 0, "10": 0, "20": 200, "30": 800, "40": 2500,
        "50": 10000, "60": 25000, "70": 65000, "80": 150000,
        "90": 500000, "100": 2000000,
    },
    ('70', 'anchor'): {
        "0": 0, "10": 0, "20": 200, "30": 1000, "40": 3000,
        "50": 12000, "60": 30000, "70": 80000, "80": 200000,
        "90": 600000, "100": 2600000,
    },
    ('70', 'user'): {
        "0": 0, "10": 0, "20": 600, "30": 3000, "40": 10000,
        "50": 40000, "60": 100000, "70": 250000, "80": 600000,
        "90": 2000000, "100": 8000000,
    },
}
# app_id=66 不区分身份类型，未匹配到的组合统一用这份默认值
DEFAULT_TITLE_GROWTH = TITLE_GROWTH_BASE[('66', 'user')]


def _is_ajax():
    """是否为前端 AJAX 请求（决定返回 JSON 还是 HTML）"""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _same_origin():
    """判断写请求是否同源；拿不到来源信息时按同源处理（兼容 curl / 脚本）"""
    origin = request.headers.get('Origin') or request.headers.get('Referer')
    if not origin:
        return True
    try:
        host = urlparse(origin).hostname
    except Exception:
        return True
    if not host:
        return True
    # 网关可能改写 Host，X-Forwarded-Host 保留的原始域名也算同源
    hosts = {request.host.split(':')[0]}
    forwarded = request.headers.get('X-Forwarded-Host', '')
    if forwarded:
        hosts.add(forwarded.split(':')[0].strip())
    return host in hosts


@app.before_request
def mark_audit_start():
    """记录请求开始时间，供审计计算耗时"""
    g._audit_start = time.time()
    return None


@app.before_request
def block_cross_site_write():
    """跨站写操作防护（轻量 CSRF）：只拦「带了来源且来源不同」的写请求"""
    if request.method in WRITE_METHODS and not _same_origin():
        return jsonify({'success': False, 'message': '拒绝跨站请求'}), 403
    return None


@app.after_request
def record_audit(response):
    """写操作审计：落 JSONL + 一行摘要到 journald（不记录 GET）"""
    audit.record(response)
    return response


@app.after_request
def add_security_headers(response):
    """基础安全响应头（不引入 CSP，避免影响页面内联脚本）"""
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'same-origin')
    return response


@app.before_request
def require_basic_auth():
    """平台基础认证：BASIC_AUTH_USER/PASSWORD 都配置时才启用，默认不改变现有访问方式"""
    user = config.BASIC_AUTH_USER
    password = config.BASIC_AUTH_PASSWORD
    if not user or not password:
        return None
    auth = request.authorization
    if auth and auth.username == user and auth.password == password:
        return None
    return Response('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="web2026"'})


# ==================== 路由定义 ====================

@app.route(f'{config.BASE_PATH}/')
def index():
    """首页"""
    return render_template("index.html")


@app.route(f'{config.BASE_PATH}/healthz')
def healthz():
    """健康检查：默认只反映进程存活；带 ?db=1 时额外探测数据库"""
    payload = {'status': 'ok', 'service': 'web2026'}
    if request.args.get('db') == '1':
        db_ok = db.ping()
        payload['db'] = 'ok' if db_ok else 'error'
        if not db_ok:
            payload['status'] = 'degraded'
            return jsonify(payload), 503
    return jsonify(payload)


@app.route(f'{config.BASE_PATH}/add', methods=['GET', 'POST'])
@form_validator({
    'uid': validate_uid,
    'money': lambda x: validate_money(x, config.MAX_MONEY)
})
def add_money():
    """添加金额"""
    if request.method == 'GET':
        return render_template("addMoney.html")
    
    data = request.validated_data
    # 业务口径：加钻石时把其余币种一并清零（沿用旧行为，避免测试环境残留金额干扰）
    db.update_money(
        data['uid'], money=data['money'], money_b=0, money_cash=0,
        money_cash_b=0, gold_coin=0, money_debts=0
    )
    return handle_success(f"恭喜你，金额：{data['money']}钻 已到账！！！")


@app.route(f'{config.BASE_PATH}/idChange', methods=['GET', 'POST'])
@form_validator({
    'uid': validate_uid,
    'app_id': lambda x: int(x) if x and str(x).isdigit() else 66
})
def id_change():
    """修改身份证"""
    if request.method == 'GET':
        return render_template("idChange.html")
    
    data = request.validated_data
    if db.insert_id_card(data['uid'], data['app_id']):
        return handle_success("恭喜你，身份信息修改成功！！！")
    return handle_form_error("修改失败")


@app.route(f'{config.BASE_PATH}/insertPerson', methods=['GET', 'POST'])
@form_validator({
    'rid': validate_rid,
    'num': lambda x: validate_num(x, max_val=config.MAX_PEOPLE_NUM, default=10),
    'app_id': lambda x: int(x) if x and str(x).isdigit() else 66
})
def insert_person():
    """插入房间人员"""
    if request.method == 'GET':
        return render_template("insertPerson.html")
    
    data = request.validated_data
    if db.insert_people(data['num'], data['rid'], data['app_id']):
        return handle_success("恭喜你，加人成功，刷新下room.config即可！！！")
    return handle_form_error("提交失败")


@app.route(f'{config.BASE_PATH}/sqlDemo', methods=['GET', 'POST'])
@form_validator({'id': lambda x: validate_num(x)})
def sql_demo():
    """SQL演示"""
    if request.method == 'GET':
        return render_template('sqlDemo.html')

    data = request.validated_data
    result = db.sql_demo(data['id'])
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': f'查询结果：{result}'})
    return f'<h3>当前查询结果：{result}</h3>'


@app.route(f'{config.BASE_PATH}/createRoom', methods=['GET', 'POST'])
@form_validator({
    'uid': validate_uid,
    'name': lambda x: x if x else '测试',
    'factoryType': lambda x: x if x else 'business-normal8',
    'settlement_channel': lambda x: x if x else 'joy-man',
    'app_id': lambda x: int(x) if x and str(x).isdigit() else 66
})
def create_room():
    """创建房间"""
    if request.method == 'GET':
        return render_template('createRoom.html')
    
    data = request.validated_data
    url = config.ROOM_CREATE_URL
    headers = {
        'X-RPCX-SerializeType': '1',
        'Content-Type': 'application/rpcx'
    }
    payload = {
        'uid': data['uid'],
        'factoryType': data['factoryType'],
        'is_create': True,
        'property': 'business',
        'settlement_channel': data['settlement_channel'],
        'app_id': data['app_id'],
        'name': data['name'],
        'sex': 1  # 默认值，可根据需要调整
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
        if res.status_code == 200:
            return handle_success(f"创建成功：{res.json()}")
        return handle_form_error(f"创建失败，状态码：{res.status_code}")
    except requests.RequestException as e:
        return handle_form_error(f"请求失败：{str(e)}")


@app.route(f'{config.BASE_PATH}/pay', methods=['GET', 'POST'])
@form_validator({
    'uid': validate_uid,
    'money': lambda x: validate_money(x, config.MAX_RECHARGE)
})
def pay():
    """模拟充值"""
    if request.method == 'GET':
        return render_template("pay.html")
    
    data = request.validated_data
    order_id = db.pay(data['uid'], data['money'])
    if not order_id:
        return handle_form_error("充值记录写入失败，请重试")
    db.insert_pay_change(data['uid'], data['money'])
    return handle_success("恭喜你，充值成功（money不会到账）！！！")


@app.route(f'{config.BASE_PATH}/addCommodity', methods=['GET', 'POST'])
@form_validator({
    'uid': validate_uid,
    'cid': validate_cids,
    'num': lambda x: validate_num(x, default=3)
})
def add_commodity():
    """添加商品"""
    if request.method == 'GET':
        data = db.select_gift_info()
        return render_template('addCommodity.html', data=data)
    
    data = request.validated_data
    cids = data.get('cid') or None
    db.add_commodity(data['uid'], cids, data['num'])
    return handle_success("恭喜你，背包请查收！！！")


@app.route(f'{config.BASE_PATH}/addExp', methods=['GET', 'POST'])
@form_validator({
    'uid': validate_uid,
    'app_id': lambda x: int(x) if x and str(x).isdigit() else 66,
    'exp_type': lambda x: x if x in ['rq', 'vip', 'gz'] else None,
    'exp': lambda x: int(x) if x and str(x).isdigit() else 0,
    'level': lambda x: x if x else '0',
    'identity_type': lambda x: x if x in ['anchor', 'user'] else 'user'  # 身份类型：anchor=主播, user=用户
})
def add_exp():
    """添加经验/人气/VIP等"""
    if request.method == 'GET':
        return render_template("addExp.html")
    
    data = request.validated_data
    exp_type = data.get('exp_type')
    exp_val = data.get('exp', 0)
    
    if exp_type == 'rq':
        db.update_popularity(data['uid'], exp_val)
    elif exp_type == 'vip':
        db.update_vip(data['uid'], exp_val, data['app_id'])
    elif exp_type == 'gz':
        level = data.get('level', '0')
        app_id = data['app_id']
        identity_type = data.get('identity_type', 'user')

        # 按 (app_id, 身份类型) 取对应的成长值基数，未匹配到的用默认配置
        growth_map = TITLE_GROWTH_BASE.get((str(app_id), identity_type), DEFAULT_TITLE_GROWTH)
        base_exp = growth_map.get(level, 0)
        total_exp = (base_exp + exp_val) * 100
        db.update_title(data['uid'], total_exp, level, data['app_id'])
    else:
        return handle_form_error("未知的类型")
    
    return handle_success("恭喜你，刷新请查收！！！")


@app.route(f'{config.BASE_PATH}/addfragment', methods=['GET', 'POST'])
@form_validator({
    'uid': validate_uid,
    'num': lambda x: validate_num(x),
    'app_id': lambda x: int(x) if x and str(x).isdigit() else 66
})
def update_user_fragment():
    """更新用户碎片"""
    if request.method == 'GET':
        return render_template('addfragment.html')
    
    data = request.validated_data
    if db.update_user_fragment(data['uid'], data['num'], data['app_id']):
        return handle_success("恭喜你，刷新查收！！！")
    return handle_form_error("添加碎片失败")


@app.route(f'{config.BASE_PATH}/insertbroker', methods=['GET', 'POST'])
@form_validator({
    'uid': validate_uid,
    'bid': lambda x: validate_uid(x) if x else 200000030,
    'app_id': lambda x: int(x) if x and str(x).isdigit() else 66,
    'want_type': lambda x: x if x in ['join', 'exit'] else 'exit'
})
def insert_broker():
    """公会操作"""
    if request.method == 'GET':
        return render_template("insertbroker.html")
    
    data = request.validated_data
    want_type = data.get('want_type', 'exit')

    # 删除旧关系与加入新公会在同一事务内，避免中途失败把用户误退会
    if not db.switch_broker(data['uid'], data['bid'], data['app_id'], join=(want_type == 'join')):
        return handle_form_error("公会操作失败，请重试")

    return handle_success(f"恭喜你，{want_type}成功，刷新下room.config即可！！！")


@app.route(f'{config.BASE_PATH}/addGames', methods=['GET', 'POST'])
@form_validator({
    'rid': validate_rid,
    'type': lambda x: x if x else None
})
def add_games():
    """添加游戏"""
    if request.method == 'GET':
        data = db.select_games_info()
        return render_template('addGames.html', data=data)
    
    data = request.validated_data
    factory_type = data.get('type')
    if not factory_type:
        return handle_form_error("请选择游戏类型")
    
    if db.insert_games(data['rid'], factory_type):
        return handle_success("恭喜你，刷新查收！！！")
    return handle_form_error("创建失败")


@app.route(f'{config.BASE_PATH}/cropPrice', methods=['GET', 'POST'])
def crop_price():
    """作物价格计算器"""
    if request.method == 'GET':
        return render_template('cropPriceCalculator.html')

    # POST请求处理表单提交（保存配置）
    return handle_success("配置已保存！！！")


@app.route(f'{config.BASE_PATH}/api/cropMature', methods=['POST'])
def crop_mature():
    """一键成熟（农场/加工/钓鱼）：服务端固定 SQL + 参数化，替代前端拼接 SQL 调 /api/sql"""
    data = request.get_json(silent=True) or {}
    action = data.get('action')
    if action not in db.CROP_MATURE_ACTIONS:
        return jsonify({'success': False, 'message': '不支持的操作类型'}), 400

    try:
        uid = validate_uid(str(data.get('uid', '')).strip())
    except ValidationError as e:
        return jsonify({'success': False, 'message': str(e)}), 400

    result = db.crop_mature(action, uid)
    if result is None:
        return jsonify({'success': False, 'message': '未找到该用户的农场信息'}), 404
    if result is False:
        return jsonify({'success': False, 'message': '执行失败，请查看服务端日志'}), 500
    return jsonify({'success': True, 'rowcount': result, 'message': f'影响 {result} 行'})


@app.route(f'{config.BASE_PATH}/api/sql', methods=['POST'])
def execute_sql():
    """执行SQL查询（只读；需配置 SQL_API_TOKEN 才开放，未配置时接口关闭）"""
    expected_token = config.SQL_API_TOKEN
    if not expected_token:
        return jsonify({'success': False, 'message': '该接口未开放'}), 403
    if request.headers.get('X-API-Token') != expected_token:
        return jsonify({'success': False, 'message': '无权访问'}), 401

    data = request.get_json(silent=True)
    if not data or 'sql' not in data:
        return jsonify({'success': False, 'message': '缺少SQL语句'}), 400

    try:
        result = db.execute_sql(data['sql'])
        return jsonify({'success': True, 'data': result})
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        print(f'执行SQL失败: {e}')
        return jsonify({'success': False, 'message': '执行失败，请查看服务端日志'}), 500


# ==================== 错误处理 ====================

@app.errorhandler(404)
def not_found(error):
    """404错误处理"""
    if _is_ajax():
        return jsonify({'success': False, 'message': '页面不存在'}), 404
    return handle_form_error("页面不存在", 404)


@app.errorhandler(413)
def request_too_large(error):
    """请求体超限"""
    return jsonify({'success': False, 'message': '请求体过大'}), 413


@app.errorhandler(500)
def internal_error(error):
    """500错误处理"""
    if _is_ajax():
        return jsonify({'success': False, 'message': '服务器内部错误'}), 500
    return handle_form_error("服务器内部错误", 500)


# ==================== 启动入口 ====================

if __name__ == "__main__":
    app.run(port=config.PORT, host=config.HOST, debug=config.DEBUG)
