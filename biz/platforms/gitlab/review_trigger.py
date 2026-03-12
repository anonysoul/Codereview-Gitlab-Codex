def should_review_gitlab_merge_request(
    object_attributes: dict,
    action: str,
    changes: dict | None = None,
) -> bool:
    """Review only MR events that introduce or expose a new source-branch commit."""
    if action not in {'open', 'reopen', 'update'}:
        return False

    last_commit_id = object_attributes.get('last_commit', {}).get('id', '')
    if not last_commit_id:
        return False

    if action in {'open', 'reopen'}:
        return True

    changes = changes or {}
    oldrev = object_attributes.get('oldrev', '')
    if oldrev and oldrev != last_commit_id:
        return True

    if 'last_commit' in changes or 'oldrev' in changes:
        return True

    return False
