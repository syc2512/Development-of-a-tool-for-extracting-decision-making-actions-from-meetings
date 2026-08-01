# -*- coding: utf-8 -*-
"""一键启动脚本 (bash/git-bash 版)"""
import os
import sys
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

# 检查依赖
deps = {'flask': 'flask', 'openai': 'openai', 'pandas': 'pandas'}
missing = []
for mod in deps:
    try:
        __import__(mod)
    except ImportError:
        missing.append(deps[mod])

if missing:
    print(f"[安装依赖] {', '.join(missing)}")
    subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + missing + ['-i', 'https://mirrors.aliyun.com/pypi/simple/'])

# 启动
from app import app
app.run(host='127.0.0.1', port=5000, debug=True)
