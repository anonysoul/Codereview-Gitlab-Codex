"""
路由注册模块
"""
from biz.api.routes import home, webhook


def register_routes(app):
    """
    注册所有路由到 Flask 应用
    """
    app.register_blueprint(home.home_bp)
    app.register_blueprint(webhook.webhook_bp)
