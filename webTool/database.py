# -*- coding: utf-8 -*-
"""
数据库模块 - 使用 SQLAlchemy 连接池和参数化查询
"""
import time
import random
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError

from config import current_config as config
from tools import randname, randid


class Database:
    """数据库操作类 - 使用连接池和参数化查询"""
    
    _instance = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 创建连接池
        db_url = (
            f"mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}"
            f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
            f"?charset={config.DB_CHARSET}"
        )
        
        self.engine = create_engine(
            db_url,
            poolclass=QueuePool,
            pool_size=config.DB_POOL_SIZE,
            max_overflow=config.DB_POOL_MAX_OVERFLOW,
            pool_recycle=config.DB_POOL_RECYCLE,
            pool_pre_ping=True,  # 自动检测断开的连接
            echo=False
        )
        self._initialized = True
        print("数据库连接池初始化成功")
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = None
        try:
            conn = self.engine.connect()
            yield conn
        except SQLAlchemyError as e:
            if conn:
                conn.rollback()
            print(f"数据库操作异常: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def execute(self, sql, params=None):
        """执行SQL语句（参数化查询）"""
        with self.get_connection() as conn:
            result = conn.execute(text(sql), params or {})
            conn.commit()
            return result
    
    def query(self, sql, params=None):
        """查询操作"""
        with self.get_connection() as conn:
            result = conn.execute(text(sql), params or {})
            return result.fetchall()
    
    def query_one(self, sql, params=None):
        """查询单条记录"""
        with self.get_connection() as conn:
            result = conn.execute(text(sql), params or {})
            return result.fetchone()
    
    def insert(self, sql, params=None):
        """插入操作"""
        with self.get_connection() as conn:
            result = conn.execute(text(sql), params or {})
            conn.commit()
            return result.rowcount
    
    def update(self, sql, params=None):
        """更新操作"""
        return self.execute(sql, params)

    def execute_sql(self, sql):
        """执行动态SQL（用于快捷操作）"""
        sql = sql.strip()
        is_select = sql.upper().startswith('SELECT')

        with self.get_connection() as conn:
            result = conn.execute(text(sql))
            if is_select:
                rows = result.fetchall()
                # 转换为字典列表
                columns = result.keys()
                return [dict(zip(columns, row)) for row in rows]
            else:
                conn.commit()
                return {'rowcount': result.rowcount}

    # ==================== 业务方法 ====================
    
    def update_money(self, uid, money=0, money_cash=0, money_cash_b=0, money_b=0, 
                     gold_coin=0, money_debts=0):
        """更新用户金额 - 使用参数化查询防止SQL注入"""
        sql = """
            UPDATE xs_user_money 
            SET money=:money, money_b=:money_b, money_cash=:money_cash, 
                money_cash_b=:money_cash_b, gold_coin=:gold_coin, money_debts=:money_debts
            WHERE uid=:uid LIMIT 1
        """
        params = {
            'money': money, 'money_b': money_b, 'money_cash': money_cash,
            'money_cash_b': money_cash_b, 'gold_coin': gold_coin,
            'money_debts': money_debts, 'uid': uid
        }
        try:
            return self.update(sql, params)
        except Exception as e:
            print(f'更新金额失败: {e}')
            return None
    
    def insert_id_card(self, uid, app_id=66):
        """插入身份证信息"""
        try:
            # 获取最后一个uid
            sql = 'SELECT uid FROM xs_user_idcard ORDER BY id DESC LIMIT 1'
            row = self.query_one(sql)
            if not row:
                print('没有找到参考记录')
                return False
            
            uuid = row[0]
            cardname = randname()
            cardnum = randid()
            
            # 使用参数化查询
            sql = """
                INSERT INTO xs_user_idcard 
                (uid, app_id, cardname, cardnum, cardfront, cardback, cardin, state, dateline, update_time)
                SELECT :uid as uid, :app_id as app_id, :cardname as cardname, :cardnum as cardnum, 
                       cardfront, cardback, cardin, state, dateline, update_time
                FROM xs_user_idcard WHERE uid = :uuid
            """
            self.insert(sql, {'uid': uid, 'app_id': app_id, 'cardname': cardname, 'cardnum': cardnum, 'uuid': uuid})
            return True
        except Exception as e:
            print(f'插入身份证信息失败: {e}')
            return False
    
    def insert_people(self, num, rid, app_id=66):
        """插入房间人员"""
        positions = list(range(int(num)))
        uids = [
            200252633, 200255313, 200255189, 200253752, 200252282,
            200254479, 200254521, 200254593, 200252041, 200252274,
        ]
        
        try:
            for position, uid in zip(positions, uids):
                sql = """
                    UPDATE xs_chatroom_config 
                    SET uid = :uid 
                    WHERE rid = :rid AND position = :position AND app_id = :app_id
                """
                self.update(sql, {'uid': uid, 'rid': rid, 'position': position, 'app_id': app_id})
            return True
        except Exception as e:
            print(f'插入人员失败: {e}')
            return False
    
    def sql_demo(self, user_id):
        """SQL演示查询"""
        sql = "SELECT username FROM qa_case.user WHERE id = :user_id"
        try:
            result = self.query(sql, {'user_id': user_id})
            return result
        except Exception as e:
            print(f'查询失败: {e}')
            return []
    
    def pay(self, uid, money):
        """模拟支付 - 分两步：
        1. 插入支付记录(state=sent)
        2. 等待1秒后更新状态为success
        返回 order_id 供后续操作使用
        """
        order_id = f"281{random.randint(1, 999999999)}ad0dd8taa00{random.choice('abcdefghijklmnopqrstuvwxyz')}"
        timestamp = int(time.time())

        insert_sql = """
            INSERT INTO xs_pay
            (uid, order_id, money, transaction_id, platform, create_time, end_time, state,
             ip, `type`, todo_id, product_name, buyer_account, buyer_id, source, app)
            VALUES
            (:uid, :order_id, :money, '4200000160201809161783627131', 'wechat',
             :create_time, :end_time, 'sent', 613787442, 'recharge', 1737783, '充值',
             'oDe8X0tcPpUATk248lcbbD9C6wV0', 'oDe8XX0tcPpUATk248lcbbD9C6wV0', 'h5', 'iamban')
        """
        insert_params = {
            'uid': uid, 'order_id': order_id, 'money': money,
            'create_time': timestamp, 'end_time': timestamp
        }

        try:
            # 步骤1: 插入支付记录，state='sent'
            result = self.insert(insert_sql, insert_params)
            if not result:
                print('支付记录插入失败')
                return None

            # 步骤2: 等待1秒后更新state为success
            time.sleep(1)
            self.update(
                "UPDATE xs_pay SET state = 'success' WHERE order_id = :order_id",
                {'order_id': order_id}
            )
            return order_id
        except Exception as e:
            print(f'支付记录操作失败: {e}')
            return None

    def insert_pay_change(self, uid, money):
        """插入消费变更记录"""
        sql = """
            INSERT INTO xs_pay_change_new
            (id, uid, dateline, money, op, reason, subject, deleted)
            VALUES
            (0, :uid, :timestamp, :money, 'pay', '', '模拟打赏', 0)
        """
        print(sql)
        try:
            result = self.insert(sql, {
                'uid': uid, 'timestamp': int(time.time()), 'money': money
            })
            return result if result else None
        except Exception as e:
            print(f'消费变更记录插入失败: {e}')
            return None
    
    def delete_commodity(self, uid):
        """删除用户商品"""
        sql = "DELETE FROM xs_user_commodity WHERE uid = :uid"
        try:
            self.execute(sql, {'uid': uid})
            # 验证删除
            check_sql = "SELECT * FROM xs_user_commodity WHERE uid = :uid LIMIT 1"
            result = self.query_one(check_sql, {'uid': uid})
            if result is None:
                print('删除成功')
            return True
        except Exception as e:
            print(f'删除失败: {e}')
            return False
    
    def add_commodity(self, uid, cids=None, num=3):
        """添加商品"""
        if cids is None:
            cids = [329, 330, 331, 339, 1090, 1839, 2000, 19593, 20283, 27361]
        
        # 先删除旧数据
        self.delete_commodity(uid)
        
        try:
            dateline = str(int(time.time()))
            for cid in cids:
                sql = """
                    INSERT INTO xs_user_commodity 
                    (uid, cid, state, num, period_end, used, in_use, dateline)
                    VALUES (:uid, :cid, 0, :num, 0, 0, 0, :dateline)
                """
                self.insert(sql, {
                    'uid': uid, 'cid': int(cid), 'num': int(num), 'dateline': dateline
                })
            return True
        except Exception as e:
            print(f'添加商品失败: {e}')
            return False
    
    def update_popularity(self, uid, data):
        """更新人气值"""
        sql = "UPDATE xs_user_popularity SET popularity = :data WHERE uid = :uid"
        try:
            return self.update(sql, {'data': data, 'uid': uid})
        except Exception as e:
            print(f'更新人气值失败: {e}')
            return None
    
    def update_vip(self, uid, data, app_id=66):
        """更新VIP"""
        sql = "UPDATE xs_user_profile SET pay_room_money = :data WHERE uid = :uid AND app_id = :app_id"
        try:
            return self.update(sql, {'data': data, 'uid': uid, 'app_id': app_id})
        except Exception as e:
            print(f'更新VIP失败: {e}')
            return None
    
    def update_title(self, uid, data, level, app_id=66):
        """更新爵位"""
        subscribe_time = int(time.time()) + 30 * 24 * 60 * 60
        sql = """
            UPDATE xs_user_title_new 
            SET level = :level, growth = :data, effective_value = :data,
                subscribe_time = :subscribe_time, effective_time = :subscribe_time
            WHERE uid = :uid AND app_id = :app_id
        """
        try:
            return self.update(sql, {
                'level': level, 'data': data,
                'subscribe_time': subscribe_time, 'uid': uid, 'app_id': app_id
            })
        except Exception as e:
            print(f'更新爵位失败: {e}')
            return None
    
    def update_user_fragment(self, uid, fragment_num, app_id=66):
        """更新用户碎片"""
        update_time = int(time.time())
        try:
            # 删除旧记录
            delete_sql = "DELETE FROM xs_user_fragment WHERE uid = :uid AND app_id = :app_id"
            self.execute(delete_sql, {'uid': uid, 'app_id': app_id})
            
            # 插入新记录
            insert_sql = """
                INSERT INTO xs_user_fragment 
                (uid, app_id, star_score, fragment_num, update_time, create_time)
                VALUES (:uid, :app_id, 0, :fragment_num, :update_time, :update_time)
            """
            self.insert(insert_sql, {
                'uid': uid, 'app_id': app_id, 'fragment_num': fragment_num, 'update_time': update_time
            })
            return True
        except Exception as e:
            print(f'更新碎片失败: {e}')
            return False
    
    def select_gift_info(self):
        """查询礼物信息"""
        sql = """
            SELECT a.id as gid, b.cid, a.name, a.handbook_type, a.awake_vap_size 
            FROM xs_gift AS a 
            LEFT JOIN xs_commodity AS b ON a.id = b.ext_id 
            WHERE b.cid IS NOT NULL AND b.type = 'gift'
        """
        try:
            return self.query(sql)
        except Exception as e:
            print(f'查询礼物信息失败: {e}')
            return []
    
    def insert_join_broker(self, uid, bid=200000030, app_id=66):
        """加入公会"""
        dateline = apply_time = int(time.time())
        sql = """
            INSERT INTO xianshi.xs_broker_user 
            (bid, uid, app_id, deleted, dateline, state, `exit`, pack_cal, sign, corp_cal, 
             corp_status, is_risk, apply_time)
            VALUES 
            (:bid, :uid, :app_id, 0, :dateline, 1, 0, 0, 0, 0, 0, 0, :apply_time)
        """
        params = {
            'bid': bid, 'uid': uid, 'app_id': app_id, 'dateline': dateline, 'apply_time': apply_time
        }
        try:
            print(f'[DEBUG] 插入公会记录: uid={uid}, bid={bid}, app_id={app_id}')
            result = self.insert(sql, params)
            print(f'[DEBUG] 插入结果: {result}')
            return result
        except Exception as e:
            print(f'[ERROR] 加入公会失败: {e}')
            print(f'[ERROR] SQL参数: {params}')
            import traceback
            traceback.print_exc()
            return None
    
    def delete_broker_user(self, uid, app_id=66):
        """删除公会用户"""
        sql = "DELETE FROM xs_broker_user WHERE uid = :uid AND app_id = :app_id"
        params = {'uid': uid, 'app_id': app_id}
        try:
            print(f'[DEBUG] 删除公会用户: uid={uid}, app_id={app_id}')
            result = self.execute(sql, params)
            print(f'[DEBUG] 删除结果: {result}')
            return result
        except Exception as e:
            print(f'[ERROR] 删除公会用户失败: {e}')
            print(f'[ERROR] SQL参数: {params}')
            return None
    
    def select_games_info(self):
        """查询游戏信息"""
        sql = """
            SELECT play_name as name, room_factory_type as factory_type 
            FROM config.bbc_room_play_type
        """
        try:
            return self.query(sql)
        except Exception as e:
            print(f'查询游戏信息失败: {e}')
            return []
    
    def insert_games(self, rid, factory_type):
        """添加游戏"""
        sql = """
            INSERT INTO xianshi.xs_chatroom_auction_config 
            (rid, play_type, extra, start, end, dateline, reback_factory_type, reback_tag_id)
            VALUES 
            (:rid, :factory_type, '', 1672556400, 1988175600, 0, 'business-friend', 0)
        """
        try:
            return self.insert(sql, {'rid': int(rid), 'factory_type': str(factory_type)})
        except Exception as e:
            print(f'添加游戏失败: {e}')
            return None


# 全局数据库实例
db = Database()

if __name__ == '__main__':
    db = Database()
    db.pay(200259587,1200)
    db.insert_pay_change(200259587, 1200)