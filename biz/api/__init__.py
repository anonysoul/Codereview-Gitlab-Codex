"""
API 应用初始化模块
"""
from flask import Flask

# 创建 Flask 应用
api_app = Flask(__name__)


def init_app(app):
    """
    初始化应用，注册所有路由
    """
    from biz.api.routes import register_routes
    register_routes(app)
