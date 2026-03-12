"""Webhook 路由模块"""
import json
import os
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request

from biz.platforms.gitlab.webhook_handler import slugify_url
from biz.queue.worker import handle_merge_request_event
from biz.utils.log import logger
from biz.utils.queue import handle_queue

webhook_bp = Blueprint('webhook', __name__)


@webhook_bp.route('/review/webhook', methods=['POST'])
def handle_webhook():
    """处理 Webhook 请求的主路由。"""
    if not request.is_json:
        return jsonify({'message': 'Invalid data format'}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    return handle_gitlab_webhook(data)


def handle_gitlab_webhook(data):
    """处理 GitLab Webhook。"""
    object_kind = data.get("object_kind")

    gitlab_url = os.getenv('GITLAB_URL') or request.headers.get('X-Gitlab-Instance')
    if not gitlab_url:
        repository = data.get('repository')
        if not repository:
            return jsonify({'message': 'Missing GitLab URL'}), 400
        homepage = repository.get("homepage")
        if not homepage:
            return jsonify({'message': 'Missing GitLab URL'}), 400
        try:
            parsed_url = urlparse(homepage)
            gitlab_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
        except Exception as e:
            return jsonify({"error": f"Failed to parse homepage URL: {str(e)}"}), 400

    gitlab_token = os.getenv('GITLAB_ACCESS_TOKEN') or request.headers.get('X-Gitlab-Token')
    if not gitlab_token:
        return jsonify({'message': 'Missing GitLab access token'}), 400

    gitlab_url_slug = slugify_url(gitlab_url)

    logger.info(f'Received event: {object_kind}')
    logger.info(f'Payload: {json.dumps(data)}')

    if object_kind != "merge_request":
        error_message = (
            f'Only GitLab merge_request events are supported, but received: {object_kind}.'
        )
        logger.error(error_message)
        return jsonify(error_message), 400

    handle_queue(handle_merge_request_event, data, gitlab_token, gitlab_url, gitlab_url_slug)
    return jsonify(
        {'message': f'Request received(object_kind={object_kind}), will process asynchronously.'}
    ), 200
