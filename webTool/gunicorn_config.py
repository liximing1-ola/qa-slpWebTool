# -*- encoding=utf8 -*-
__author__ = "Wu.Zhenxing"
__title__ = ""
__desc__ = ""

# gunicorn.py
import os
import sys

# 添加项目根目录到 Python 路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import gevent.monkey
gevent.monkey.patch_all()
import multiprocessing
debug = True#每次启动会显示，配置参数，生产环境可以设置为False
#日志记录等级，有warining,debug等
loglevel = 'debug'
#ip和端口绑定
bind = "127.0.0.1:2023"
###############以下的日志路径，都得根据根目录来写，找不到该路径，就不能启动gunicorn，最坑的是，没有任何错误提示。

#gunicorn进程id，kill掉该文件的id，gunicorn就停止
pidfile = "log/gunicorn.pid"
#接入服务的日志记录地址
accesslog = "log/access.log"
#启动和调用出现错误的日志地址
errorlog = "log/debug.log"
# 设置守护进程,将进程交给supervisor管理
daemon = True
# 启动的进程数
#workers = int(multiprocessing.cpu_count()/2)
workers = 2
# 工作模式协程
worker_class = 'gevent'
x_forwarded_for_header = 'X-FORWARDED-FOR'
