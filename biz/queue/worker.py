import os
import traceback
from datetime import datetime

from biz.entity.review_entity import MergeRequestReviewEntity
from biz.event.event_manager import event_manager
from biz.platforms.gitlab.review_trigger import should_review_gitlab_merge_request
from biz.platforms.gitlab.webhook_handler import MergeRequestHandler, filter_changes
from biz.service.review_service import ReviewService
from biz.utils.code_reviewer import CodeReviewer
from biz.utils.log import logger


def handle_merge_request_event(
    webhook_data: dict,
    gitlab_token: str,
    gitlab_url: str,
    gitlab_url_slug: str,
):
    """处理 GitLab Merge Request Hook 事件。"""
    merge_review_only_protected_branches = (
        os.environ.get('MERGE_REVIEW_ONLY_PROTECTED_BRANCHES_ENABLED', '0') == '1'
    )

    try:
        handler = MergeRequestHandler(webhook_data, gitlab_token, gitlab_url)
        logger.info('Merge Request Hook event received')

        object_attributes = webhook_data.get('object_attributes', {})
        is_draft = object_attributes.get('draft') or object_attributes.get('work_in_progress')
        if is_draft:
            msg = (
                f"[通知] MR为草稿（draft），未触发AI审查。\n项目: {webhook_data['project']['name']}"
                f"\n作者: {webhook_data['user']['username']}"
                f"\n源分支: {object_attributes.get('source_branch')}"
                f"\n目标分支: {object_attributes.get('target_branch')}"
                f"\n链接: {object_attributes.get('url')}"
            )
            logger.info("%s", msg)
            return

        if merge_review_only_protected_branches and not handler.target_branch_protected():
            logger.info("Merge Request target branch not match protected branches, ignored.")
            return

        if not should_review_gitlab_merge_request(object_attributes, handler.action):
            logger.info(
                "Merge Request Hook event ignored: action=%s, oldrev=%s, last_commit_id=%s.",
                handler.action,
                object_attributes.get('oldrev', ''),
                object_attributes.get('last_commit', {}).get('id', ''),
            )
            return

        last_commit_id = object_attributes.get('last_commit', {}).get('id', '')
        if last_commit_id:
            project_name = webhook_data['project']['name']
            source_branch = object_attributes.get('source_branch', '')
            target_branch = object_attributes.get('target_branch', '')
            if ReviewService.check_mr_last_commit_id_exists(
                project_name,
                source_branch,
                target_branch,
                last_commit_id,
            ):
                logger.info(
                    "Merge Request with last_commit_id %s already exists, skipping review for %s.",
                    last_commit_id,
                    project_name,
                )
                return

        changes = handler.get_merge_request_changes()
        logger.info('changes: %s', changes)
        changes = filter_changes(changes)
        if not changes:
            logger.info('未检测到有关代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。')
            return

        additions = 0
        deletions = 0
        for item in changes:
            additions += item.get('additions', 0)
            deletions += item.get('deletions', 0)

        commits = handler.get_merge_request_commits()
        if not commits:
            logger.error('Failed to get commits')
            return

        commits_text = ';'.join(commit['title'] for commit in commits)
        review_result = CodeReviewer().review_and_strip_code(str(changes), commits_text)
        handler.add_merge_request_notes(f'Auto Review Result: \n{review_result}')

        event_manager['merge_request_reviewed'].send(
            MergeRequestReviewEntity(
                project_name=webhook_data['project']['name'],
                author=webhook_data['user']['username'],
                source_branch=webhook_data['object_attributes']['source_branch'],
                target_branch=webhook_data['object_attributes']['target_branch'],
                updated_at=int(datetime.now().timestamp()),
                commits=commits,
                score=CodeReviewer.parse_review_score(review_text=review_result),
                url=webhook_data['object_attributes']['url'],
                review_result=review_result,
                url_slug=gitlab_url_slug,
                webhook_data=webhook_data,
                additions=additions,
                deletions=deletions,
                last_commit_id=last_commit_id,
            )
        )
    except Exception as e:
        error_message = f'AI Code Review 服务出现未知错误: {str(e)}\n{traceback.format_exc()}'
        logger.error('出现未知错误: %s', error_message)
