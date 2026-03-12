import os
import traceback
from datetime import datetime

from biz.entity.review_entity import MergeRequestReviewEntity
from biz.event.event_manager import event_manager
from biz.platforms.gitlab.repo_cache import GitLabRepoCacheManager
from biz.platforms.gitlab.review_trigger import should_review_gitlab_merge_request
from biz.platforms.gitlab.webhook_handler import MergeRequestHandler
from biz.service.review_service import ReviewService
from biz.utils.codex_runner import CodexReviewRunner
from biz.utils.log import logger


def _fallback_commits_from_webhook(object_attributes: dict) -> list[dict]:
    last_commit = object_attributes.get('last_commit') or {}
    if not last_commit.get('id'):
        return []
    return [last_commit]


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
    handler = None

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

        repo_cache_manager = GitLabRepoCacheManager(gitlab_url, gitlab_token)
        repo_preparation = repo_cache_manager.prepare_merge_request_repo(webhook_data)
        logger.info(
            "Prepared cached repository for MR review: %s (source=%s target=%s commit=%s)",
            repo_preparation.local_path,
            repo_preparation.source_branch,
            repo_preparation.target_branch,
            repo_preparation.last_commit_id,
        )

        diff_stats = repo_cache_manager.collect_diff_stats(
            repo_preparation.local_path,
            repo_preparation.target_branch,
        )
        if not diff_stats.changed_files:
            logger.info('未检测到文件变更，继续交由 Codex 自行审查。')

        commits = handler.get_merge_request_commits()
        if not commits:
            commits = _fallback_commits_from_webhook(object_attributes)
            if commits:
                logger.warning('Failed to get commits from GitLab API, falling back to webhook last_commit.')
            else:
                logger.error('Failed to get commits')
                return

        review_result = CodexReviewRunner().review(
            repo_preparation.local_path,
            repo_preparation.base_ref,
        )
        handler.add_merge_request_notes(review_result)

        event_manager['merge_request_reviewed'].send(
            MergeRequestReviewEntity(
                project_name=webhook_data['project']['name'],
                author=webhook_data['user']['username'],
                source_branch=webhook_data['object_attributes']['source_branch'],
                target_branch=webhook_data['object_attributes']['target_branch'],
                updated_at=int(datetime.now().timestamp()),
                commits=commits,
                score=0,
                url=webhook_data['object_attributes']['url'],
                review_result=review_result,
                url_slug=gitlab_url_slug,
                webhook_data=webhook_data,
                additions=diff_stats.additions,
                deletions=diff_stats.deletions,
                last_commit_id=last_commit_id,
            )
        )
    except Exception as e:
        logger.error('MR review failed: %s\n%s', str(e), traceback.format_exc())
        if handler is not None:
            try:
                handler.add_merge_request_notes(f'自动审查失败：{str(e)}')
            except Exception:
                logger.error('Failed to add failure note to merge request.\n%s', traceback.format_exc())
