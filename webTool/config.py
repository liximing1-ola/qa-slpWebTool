# -*- coding: utf-8 -*-
"""
配置文件 - 存放所有配置项
"""
import os


class Config:
    """基础配置类"""
    
    # Flask配置
    DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    # Flask 自带的开发服务器参数，仅 `python app.py` 本地调试时生效；
    # 线上由 systemd unit 的 `gunicorn -b 0.0.0.0:9090` 决定监听地址，与这里无关
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
    # 建立连接的超时时间（秒），数据库不可达时不要一直挂着
    DB_CONNECT_TIMEOUT = int(os.getenv('DB_CONNECT_TIMEOUT', 5))
    # 连接池耗尽的等待时间（秒），超时直接报错
    DB_POOL_TIMEOUT = int(os.getenv('DB_POOL_TIMEOUT', 10))

    # 请求体大小上限（字节），防止超大表单把内存吃满
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 2 * 1024 * 1024))

    # 操作审计日志目录（按天生成 audit-YYYYMMDD.jsonl），容器化时可指向 /var/log/web2026
    AUDIT_LOG_DIR = os.getenv(
        'AUDIT_LOG_DIR',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    )

    # 操作记录查询页（/web2026/sqlDemo）的访问密码；留空则该页面关闭（返回 403）
    AUDIT_VIEW_PASSWORD = os.getenv('AUDIT_VIEW_PASSWORD', '')
    # 该页面一次展示的记录条数
    AUDIT_VIEW_RECENT = int(os.getenv('AUDIT_VIEW_RECENT', 10))
    # 会话签名密钥；留空则由 AUDIT_VIEW_PASSWORD 派生，保证多 worker / 重启后会话不失效
    SECRET_KEY = os.getenv('SECRET_KEY', '')
    
    # API配置
    # 创建商业房间的 RPC 地址
    ROOM_CREATE_URL = os.getenv('ROOM_CREATE_URL', 'http://127.0.0.1/rpc/Room.Busi/CreateBusiness')

    # /api/sql 接口访问口令（为空则接口关闭，不对外提供服务）
    SQL_API_TOKEN = os.getenv('SQL_API_TOKEN', '')

    # 平台基础认证（用户名和密码都配置才生效，留空则不启用）
    BASIC_AUTH_USER = os.getenv('BASIC_AUTH_USER', '')
    BASIC_AUTH_PASSWORD = os.getenv('BASIC_AUTH_PASSWORD', '')

    # 验证规则
    UID_LENGTH = 9
    MAX_MONEY = 2000000000
    MAX_RECHARGE = 100000000
    # 房间加人上限，必须与 database.ROOM_SEED_UIDS 的数量一致
    MAX_PEOPLE_NUM = 10


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
