from flask import Flask, render_template, request
from conMysql import mysql
import requests

app = Flask(__name__)
mysql = mysql()

base_path = "/qatest2023"


@app.route(f'{base_path}/')
def index():
    return render_template("index.html")


@app.route(f'{base_path}/add', methods=['GET', 'POST'])
def add():
    if request.method == 'GET':
        return render_template("addMoney.html")
    else:
        uid = request.form['uid']
        money = request.form['money']
    if len(uid) == 9 and int(money) < 2000000000:
        mysql.updateMoneySql(uid, money)
        return '<h3>---------恭喜你，金额：{}钻 已到账！！！----------</h3>'.format(money)
    return '<h3>---------------打款失败!!!---------------</h3>'


@app.route(f'{base_path}/idChange', methods=['GET', 'POST'])
def idChange():
    if request.method == 'GET':
        return render_template("idChange.html")
    else:
        uid = request.form['uid']
    if len(uid) == 9:
        mysql.insertIdCard(uid)
        return '<h3>---------恭喜你，身份信息修改成功！！！----------</h3>'
    return '<h3>--------------修改失败!!!---------------</h3>'


@app.route(f'{base_path}/insertPerson', methods=['GET', 'POST'])
def insertPerson():
    if request.method == 'GET':
        return render_template("insertPerson.html")
    else:
        num = request.form['num']
        if not num:
            num = 10
        rid = request.form['rid']
    if len(rid) == 9 and int(num) <= 12:
        mysql.insertPeople(int(num), int(rid))
        return '<h3>---------恭喜你，加人成功，刷新下room.config即可！！！----------</h3>'
    return '<h3>--------------提交失败!!!---------------</h3>'


@app.route(f'{base_path}/sqlDemo', methods=['GET', 'POST'])
def sqlDemo():
    if request.method == 'GET':
        return render_template('sqlDemo.html')
    else:
        user_id = request.form['id']
    if len(user_id) == 3:
        user_name = mysql.sqlDemo(user_id)
    else:
        return '<h3>No</h3>'
    return '<h3>当前查询结果：{}</h3>'.format(user_name)


@app.route(f'{base_path}/createRoom', methods=['GET', 'POST'])
def createRoom():
    if request.method == 'GET':
        return render_template('createRoom.html')
    else:
        uid = request.form['uid']
        factory_type = request.form['type']
    if len(uid) == 9:
        #url = 'http://192.168.11.46/test/changeRoom?uid={}&factory_type={}&property=business'.\
        url = 'https://127.0.0.1/test/changeRoom?uid={}&factory_type={}&property=business'.\
            format(int(uid), factory_type)
        res = requests.get(url,verify=False)
        if res.status_code == 200:
            return '<h3>---------创建成功：{}----------</h3>'.format(res.json())
    return '<h3>---------创建失败：{}----------</h3>'


@app.route(f'{base_path}/pay', methods=['GET', 'POST'])
def pay():
    if request.method == 'GET':
        return render_template("pay.html")
    else:
        uid = request.form['uid']
        money = request.form['money']
    if len(uid) == 9 and int(money) < 100000000:
        mysql.pay(uid, int(money))
        return '<h3>---------恭喜你，充值成功（money不会到账）！！！----------</h3>'.format(money)
    return '<h3>---------------充值失败!!!---------------</h3>'


@app.route(f'{base_path}/addCommodity', methods=['GET', 'POST'])
def addCommodity():
    if request.method == 'GET':
        data = mysql.selectGiftInfo()
        # data = [(1, 1, 1), (2, 2, 2)]
        return render_template('addCommodity.html', data=data)

        # return render_template("addCommodity.html")
    else:
        uid = request.form['uid']
        cids = request.form['cid'].split(',') if request.form['cid'] else []
        num = request.form['num']
    if len(uid) == 9:
        if cids and num:
            mysql.addCommodity(uid, cids, num)
        else:
            mysql.addCommodity(uid)
        return '<h3>---------恭喜你，背包请查收！！！----------</h3>'
    return '<h3>---------------加物品失败!!!---------------</h3>'


@app.route(f'{base_path}/addExp', methods=['GET', 'POST'])
def addExp():
    if request.method == 'GET':
        return render_template("addExp.html")
    else:
        exp_type = request.form['exp_type']
        uid = request.form['uid']
        exp = request.form['exp']

    if len(uid) == 9:
        if exp_type == 'rq':
            mysql.updateRqSql(uid, exp)
        if exp_type == 'vip':
            mysql.updateVipSql(uid, exp)
        if exp_type == 'gz':
            level = request.form['level']
            config = {
                "0": 0,
                "10": 0,
                "20": 200,
                "30": 800,
                "40": 2500,
                "50": 10000,
                "60": 25000,
                "70": 65000,
                "80": 150000,
                "90": 500000,
                "100": 2000000,
            }
            data = (config[level] + int(exp)) * 100
            mysql.updateJueweiSql(uid, data, level)

        return '<h3>---------恭喜你，刷新请查收！！！----------</h3>'
    return '<h3>---------------!!!---------------</h3>'


@app.route(f'{base_path}/addfragment', methods=['GET', 'POST'])
def updateUserFragment():
    if request.method == 'GET':
        return render_template('addfragment.html')
    else:
        uid = request.form['uid']
        num = request.form['num']
    if len(uid) == 9:
        mysql.updateUserFragment(uid, num)
        return '<h3>---------恭喜你，刷新查收！！！----------</h3>'
    return '<h3>---------------添加碎片失败!!!---------------</h3>'


@app.route(f'{base_path}/insertbroker', methods=['GET', 'POST'])
def insertBroker():
    if request.method == 'GET':
        return render_template("insertbroker.html")
    else:
        uid = request.form['uid']
        bid = request.form['bid']
        want_type = request.form['want_type']
        if not bid:
            bid = 200000030
    if len(uid) == 9 and len(bid) == 9:
        if want_type == 'join':
            mysql.delBrokerUser(int(uid))
            mysql.insertJoinBroker(int(uid), int(bid))
        else:
            mysql.delBrokerUser(int(uid))
        return f'<h3>---------恭喜你，{want_type}成功，刷新下room.config即可！！！----------</h3>'
    return '<h3>--------------提交失败!!!---------------</h3>'

@app.route(f'{base_path}/addGames', methods=['GET', 'POST'])
def addGames():
    if request.method == 'GET':
        data = mysql.selectGamesInfo()
        return render_template('addGames.html', data=data)
    else:
        rid = request.form['rid']
        factory_type = request.form['type']
    if len(rid) == 9:
        mysql.insertGames(rid, factory_type)
        return '<h3>---------恭喜你，刷新查收！！！----------</h3>'
    return '<h3>---------创建失败：{}----------</h3>'

if __name__ == "__main__":
    # app.run(port=2023, host="192.168.11.57", debug=False)
    app.run(port=2023, host='127.0.0.1', debug=True)
