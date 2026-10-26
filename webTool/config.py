# -*- coding: utf-8 -*-
"""
配置文件 - 存放所有配置项
"""
import os


class Config:
    """基础配置类"""
    
    # Flask配置
    DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    PORT = int(os.getenv('FLASK_PORT', 2023))
    HOST = os.getenv('FLASK_HOST', '127.0.0.1')
    
    # 基础路径
    BASE_PATH = "/web2026"
    
    # 数据库配置 - 从环境变量读取，如果没有则使用默认值
    DB_HOST = os.getenv('DB_HOST', '192.168.1.24')
    DB_PORT = int(os.getenv('DB_PORT', 3306))
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'root')
    DB_NAME = os.getenv('DB_NAME', 'xianshi')
    DB_CHARSET = 'utf8mb4'
    
    # 数据库连接池配置
    DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', 5))
    DB_POOL_MAX_OVERFLOW = int(os.getenv('DB_POOL_MAX_OVERFLOW', 10))
    DB_POOL_RECYCLE = int(os.getenv('DB_POOL_RECYCLE', 3600))
    
    # API配置
    API_BASE_URL = os.getenv('API_BASE_URL', 'https://127.0.0.1')
    
    # 验证规则
    UID_LENGTH = 9
    MAX_MONEY = 2000000000
    MAX_RECHARGE = 100000000
    MAX_PEOPLE_NUM = 12


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False


# 配置映射
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

# 获取当前配置
ENV = os.getenv('FLASK_ENV', 'development')
current_config = config_map.get(ENV, DevelopmentConfig)
