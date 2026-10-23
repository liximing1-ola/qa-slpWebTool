# -*- coding: utf-8 -*-
"""
验证器模块 - 统一处理参数验证
"""
from functools import wraps
from flask import request, jsonify

from config import current_config as config


class ValidationError(Exception):
    """验证错误异常"""
    pass


def validate_uid(uid):
    """验证用户ID"""
    if not uid:
        raise ValidationError("用户ID不能为空")
    if len(str(uid)) != config.UID_LENGTH:
        raise ValidationError(f"用户ID必须是{config.UID_LENGTH}位数字")
    try:
        int(uid)
    except ValueError:
        raise ValidationError("用户ID必须是数字")
    return int(uid)


def validate_rid(rid):
    """验证房间ID"""
    return validate_uid(rid)  # 房间ID和用户ID规则相同


def validate_money(money, max_amount=None):
    """验证金额"""
    if not money:
        raise ValidationError("金额不能为空")
    try:
        amount = int(money)
    except ValueError:
        raise ValidationError("金额必须是数字")
    if amount < 0:
        raise ValidationError("金额不能为负数")
    if max_amount and amount > max_amount:
        raise ValidationError(f"金额不能超过{max_amount}")
    return amount


def validate_num(num, max_val=None, default=None):
    """验证数量"""
    if not num:
        if default is not None:
            return default
        raise ValidationError("数量不能为空")
    try:
        val = int(num)
    except ValueError:
        raise ValidationError("数量必须是数字")
    if val < 0:
        raise ValidationError("数量不能为负数")
    if max_val and val > max_val:
        raise ValidationError(f"数量不能超过{max_val}")
    return val


def validate_cids(cid_str):
    """验证商品ID列表"""
    if not cid_str:
        return []
    try:
        return [int(x.strip()) for x in cid_str.split(',') if x.strip()]
    except ValueError:
        raise ValidationError("商品ID格式错误")


def handle_form_error(error_msg):
    """处理表单错误响应"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': False, 'message': error_msg})
    return f'<h3 style="color: red;">---------------{error_msg}---------------</h3>'


def handle_success(msg):
    """处理成功响应"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': msg})
    return f'<h3 style="color: green;">---------{msg}----------</h3>'


def form_validator(rules):
    """
    表单验证装饰器
    
    使用示例:
    @form_validator({
        'uid': validate_uid,
        'money': lambda x: validate_money(x, config.MAX_MONEY)
    })
    def add():
        ...
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if request.method == 'POST':
                validated_data = {}
                for field, validator in rules.items():
                    value = request.form.get(field)
                    try:
                        validated_data[field] = validator(value)
                    except ValidationError as e:
                        return handle_form_error(str(e))
                # 将验证后的数据存储在request对象中
                request.validated_data = validated_data
            return f(*args, **kwargs)
        return wrapper
    return decorator
