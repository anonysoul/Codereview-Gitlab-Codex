"""
首页路由模块
"""
from flask import Blueprint

home_bp = Blueprint('home', __name__)


@home_bp.route('/')
def home():
    return """<h2>The GitLab code review API server is running.</h2>
              <p>This service accepts GitLab merge_request webhooks at <code>/review/webhook</code>.</p>
              """
