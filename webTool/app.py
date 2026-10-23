# -*- coding: utf-8 -*-
"""
Flask应用主入口 - 优化版本
"""
import urllib3
from flask import Flask, render_template, request, jsonify
import requests

from config import current_config as config
from database import db
from validators import (
    validate_uid, validate_rid, validate_money, validate_num, 
    validate_cids, handle_form_error, handle_success, form_validator
)

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)


# ==================== 路由定义 ====================

@app.route(f'{config.BASE_PATH}/')
def index():
    """首页"""
    return render_template("index.html")


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
    db.update_money(data['uid'], money=data['money'])
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
    url = f"http://127.0.0.1/rpc/Room.Busi/CreateBusiness"
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
    db.pay(data['uid'], data['money'])
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
        
        # 根据 app_id 和 identity_type 区分配置
        if app_id == 66:
            # 不夜 - 按现有配置执行
            config_map = {
                "0": 0, "10": 0, "20": 200, "30": 800, "40": 2500,
                "50": 10000, "60": 25000, "70": 65000, "80": 150000,
                "90": 500000, "100": 2000000,
            }
        elif app_id == 70:
            # 小拾光 - 根据身份类型区分配置
            if identity_type == 'anchor':
                # 主播配置（占位，后续手动修改）
                config_map = {
                    "0": 0, "10": 0, "20": 200, "30": 1000, "40": 3000,
                    "50": 12000, "60": 30000, "70": 80000, "80": 200000,
                    "90": 600000, "100": 2600000,
                }
            else:
                # 用户配置（占位，后续手动修改）
                config_map = {
                    "0": 0, "10": 0, "20": 600, "30": 3000, "40": 10000,
                    "50": 40000, "60": 100000, "70": 250000, "80": 600000,
                    "90": 2000000, "100": 8000000,
                }
        else:
            # 默认配置
            config_map = {
                "0": 0, "10": 0, "20": 200, "30": 800, "40": 2500,
                "50": 10000, "60": 25000, "70": 65000, "80": 150000,
                "90": 500000, "100": 2000000,
            }
        
        base_exp = config_map.get(level, 0)
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
    
    print(f'[DEBUG] insert_broker 被调用: uid={data["uid"]}, bid={data["bid"]}, app_id={data["app_id"]}, want_type={want_type}')
    
    db.delete_broker_user(data['uid'], data['app_id'])
    if want_type == 'join':
        db.insert_join_broker(data['uid'], data['bid'], data['app_id'])
    
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


@app.route(f'{config.BASE_PATH}/api/sql', methods=['POST'])
def execute_sql():
    """执行SQL查询"""
    data = request.get_json()
    if not data or 'sql' not in data:
        return jsonify({'success': False, 'message': '缺少SQL语句'}), 400

    sql = data['sql']
    try:
        result = db.execute_sql(sql)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== 错误处理 ====================

@app.errorhandler(404)
def not_found(error):
    """404错误处理"""
    return handle_form_error("页面不存在"), 404


@app.errorhandler(500)
def internal_error(error):
    """500错误处理"""
    return handle_form_error("服务器内部错误"), 500


# ==================== 启动入口 ====================

if __name__ == "__main__":
    app.run(port=config.PORT, host=config.HOST, debug=config.DEBUG)
