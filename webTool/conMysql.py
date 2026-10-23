#! /usr/bin/python
# coding=utf-8

import pymysql as MySQL
import time
import random

from tools import *


class mysql:
    def __init__(self,
                 host='192.168.1.24',
                 # host='127.0.0.1',
                 user='root',
                 # passwd='123456',
                 passwd='root',
                 db='xianshi',
                 port=3306,
                 charset='utf8'):
        self.cursor = None
        self.host = host
        self.user = user
        self.passwd = passwd
        self.db = db
        self.port = port
        self.charset = charset
        self.conn = None
        self._conn()

    def _conn(self):
        try:
            self.conn = MySQL.Connection(host=self.host, user=self.user, passwd=self.passwd, db=self.db, port=self.port,
                                         charset=self.charset)
            print("数据库连接成功")
            return True
        except Exception as e:
            print("数据库连接失败:" + str(e))
            return False

    # 通过ping()实现数据库的长连接
    def _reConn(self, num=28800, stime=3):
        _number = 0
        _status = True
        while _status and _number <= num:
            try:
                # ping校验连接是否异常
                self.conn.ping()
                _status = False
            except:
                print("数据库断开连接，重连")
                if self._conn():
                    _status = False
                    break
                _number += 1
                time.sleep(stime)

    def close(self):
        self._reConn()
        self.conn.close()

    def query(self, sql):
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql)
            results = self.cursor.fetchall()
            self.cursor.close()
            return results
        except Exception as e:
            print("query异常:" + str(e))
            return None

    def insert(self, sql, param):
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            res = self.cursor.execute(sql, param)
            self.conn.commit()
            self.cursor.close()
            return res
        except Exception as e:
            self.conn.rollback()
            print("insert异常:" + str(e))
            return False

    def updateMoneySql(self, uid, money=0, money_cash=0, money_cash_b=0, money_b=0, gold_coin=0, money_debts=0):
        sql = "update xs_user_money set money={}, money_b={}, money_cash={}, money_cash_b={},gold_coin={}, money_debts={} " \
              "where uid={} limit 1".format(money, money_b, money_cash, money_cash_b, gold_coin, money_debts, uid)
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql)
            self.conn.commit()
            self.cursor.close()
        except Exception as error:
            self.conn.rollback()
            print('update fail', error)

    def insertIdCard(self, uid):
        sql = 'select uid from xs_user_idcard order by id desc limit 1'
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql)
            uuid = self.cursor.fetchone()
            print(uuid)
            cardname = randname()
            cardnum = randid()
            sql1 = 'insert into xs_user_idcard(uid, app_id, cardname, cardnum, cardfront, cardback, cardin, state, dateline, update_time) ' \
                   'select {} as uid, app_id, "{}" as cardname, {} as cardnum, cardfront, cardback, cardin, state, dateline, update_time' \
                   ' from xs_user_idcard where uid = {}'.format(uid, cardname, cardnum, uuid[0])
            self.cursor.execute(sql1)
            self.conn.commit()
            self.cursor.close()
        except Exception as error:
            self.conn.rollback()
            print('insert fail', error)

    def insertPeople(self, num, rid):
        # uids = {"0": 200000098, "1": 200000099, "9": 200000100, "3": 200000101, "4": 200000102, "5": 200000104,
        #         "6": 200000105, "7": 200000106, "8": 200000107, "2": 200000108, "10": 200000109, "11": 200000110}
        positions = [i for i in range(int(num))]
        uids = [
            200252633,
            200255313,
            200255189,
            200253752,
            200252282,
            200254479,
            200254521,
            200254593,
            200252041,
            200252274,
        ]
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            # for k, v in uids.items():
            for k, v in zip(positions, uids):
                sql = 'UPDATE xs_chatroom_config SET uid = {} WHERE rid = {} and position = {}'.format(v, rid, int(k))
                self.cursor.execute(sql)
            self.conn.commit()
            self.cursor.close()
        except Exception as error:
            self.conn.rollback()
            print(error)

    def sqlDemo(self, user_id):
        sql = "select username from qa_case.user where id={}".format(user_id)
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql)
            res = self.cursor.fetchall()
            return res
        except Exception as error:
            print(error)
            return 0

    def pay(self, uid, money):
        order_id = '281{}ad0dd8taa00{}'.format(str(random.randint(1, 999999999)),
                                               str(random.choice('abcdefghijklmnopqrstuvwxyz!@#$%^&*()')))
        create_time = end_time = int(time.time())
        sql = "INSERT INTO xs_pay (uid, order_id, money, transaction_id, platform, create_time, end_time, state, ip, type, todo_id, product_name, buyer_account, buyer_id, source, app) VALUES ({}, '{}', {}, '4200000160201809161783627131', 'wechat', {}, {}, 'success',613787442, 'recharge', 1737783, '充值', 'oDe8X0tcPpUATk248lcbbD9C6wV0', 'oDe8XX0tcPpUATk248lcbbD9C6wV0', 'h5', 'iamban')".format(
            uid, order_id, money,create_time,end_time)
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql)
            self.conn.commit()
            self.cursor.close()
        except Exception as error:
            self.conn.rollback()
            print(error)

    def delCommodity(self, uid):
        sql1 = "DELETE FROM xs_user_commodity where uid = {}".format(uid)
        sql2 = 'SELECT * from xs_user_commodity where uid = {}'.format(uid)
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql1)
            self.cursor.execute(sql2)
            res = self.cursor.fetchone()
            self.conn.commit()
            self.cursor.close()
            if res is None:
                print('del success')
        except Exception as error:
            self.conn.rollback()
            print('del fail', error)

    def addCommodity(self, uid, cids=None, num=3):
        # cids = [2, 3, 4, 9, 12, 13, 14, 15, 16, 17, 18, 20, 38, 100, 174, 175, 176, 177, 23629, 23630, 23631, 20878]
        # cids = [329, 330, 331, 339, 1090, 1839, 2000, 19593, 20283, 27361]
        if cids is None:
            cids = [329, 330, 331, 339, 1090, 1839, 2000, 19593, 20283, 27361]
        mysql().delCommodity(uid)
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            for cid in cids:
                cid = int(cid)
                num = int(num)
                dateline = str(int(time.time()))
                sql1 = 'INSERT into xs_user_commodity(uid, cid, state, num, period_end, used, in_use, dateline) ' \
                       'VALUES ({}, {}, 0,{},0,0,0,{})'.format(uid, cid, num, dateline)
                self.cursor.execute(sql1)
            self.conn.commit()
            self.cursor.close()
        except Exception as error:
            self.conn.rollback()
            print(error)

    def updateRqSql(self, uid, data):
        """人气值"""
        sql = f"""update xs_user_popularity set popularity={data} where uid ={uid};"""
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql)
            self.conn.commit()
            self.cursor.close()
        except Exception as error:
            self.conn.rollback()
            print('update fail', error)

    def updateVipSql(self, uid, data):
        """vip"""
        sql = f"""update xs_user_profile set pay_room_money={data} where uid={uid};"""
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql)
            self.conn.commit()
            self.cursor.close()
        except Exception as error:
            self.conn.rollback()
            print('update fail', error)

    def updateJueweiSql(self, uid, data, level):
        """贵族"""
        subscribe_time = int(time.time()) + 30 * 24 * 60 * 60
        sql = f"""update xs_user_title_new set level={level},growth={data},effective_value={data},subscribe_time={subscribe_time},effective_time={subscribe_time} where uid ={uid};"""
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql)
            self.conn.commit()
            self.cursor.close()
        except Exception as error:
            self.conn.rollback()
            print('update fail', error)

    def updateUserFragment(self, uid, fragment_num):
        """添加装扮碎片"""
        update_time = int(time.time())
        sql1 = f"""delete from xs_user_fragment where uid={uid}"""
        sql2 = f"""INSERT INTO xs_user_fragment (uid, star_score, fragment_num, update_time, create_time) VALUES({uid}, 0, {fragment_num}, {update_time}, {update_time}); """
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql1)
            self.conn.commit()
            time.sleep(0.5)
            self.cursor.execute(sql2)
            self.conn.commit()
            self.cursor.close()
        except Exception as error:
            self.conn.rollback()
            print('update fail', error)

    def selectGiftInfo(self):
        sql=f"""select a.id as gid,b.cid,a.name,a.handbook_type,a.awake_vap_size from xs_gift as a left join xs_commodity as b on a.id=b.ext_id where b.cid is not null and b.type='gift';"""
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql)
            results = self.cursor.fetchall()
            self.cursor.close()
            return results
        except Exception as error:
            self.conn.rollback()
            print('update fail', error)

    def insertJoinBroker(self, uid, bid=200000030):
        """加入公会"""
        dateline = apply_time = int(time.time())
        sql = f"""
        INSERT INTO `xianshi`.`xs_broker_user`(`bid`, `uid`, `deleted`, `dateline`, `state`, `exit`, `pack_cal`, `sign`, `corp_cal`, `corp_status`, `is_risk`, `apply_time`) VALUES ({bid}, {uid}, 0, {dateline}, 1, 0, 0, 0, 0, 0, 0, {apply_time});
        """
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql)
            self.conn.commit()
            self.cursor.close()
        except Exception as error:
            self.conn.rollback()
            print('insert fail', error)

    def delBrokerUser(self, uid):
        sql1 = "DELETE FROM xs_broker_user where uid = {}".format(uid)
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql1)
            res = self.cursor.fetchone()
            self.conn.commit()
            self.cursor.close()
            if res is None:
                print('del success')
        except Exception as error:
            self.conn.rollback()
            print('del fail', error)

    def selectGamesInfo(self):
        sql=f"""select play_name as name,room_factory_type as factory_type from config.bbc_room_play_type;"""
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql)
            results = self.cursor.fetchall()
            self.cursor.close()
            return results
        except Exception as error:
            self.conn.rollback()
            print('update fail', error)

    def insertGames(self, rid, factory_type):
        """添加玩法"""
        sql = f"""INSERT INTO `xianshi`.`xs_chatroom_auction_config`(`rid`, `play_type`, `extra`, `start`, `end`, `dateline`, `reback_factory_type`, `reback_tag_id`) VALUES ({int(rid)}, '{str(factory_type)}', '', 1672556400, 1988175600, 0, 'business-friend', 0);"""
        try:
            self._reConn()
            self.cursor = self.conn.cursor()
            self.cursor.execute(sql)
            self.conn.commit()
            self.cursor.close()
        except Exception as error:
            self.conn.rollback()
            print('insert fail', error)

if __name__ == '__main__':
    print(time.time())
    # mysql = mysql()
    # mysql.insertIdCard(uid=193188003)
