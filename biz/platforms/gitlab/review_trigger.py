def should_review_gitlab_merge_request(object_attributes: dict, action: str) -> bool:
    """Only review MR updates caused by source-branch commit changes."""
    if action != 'update':
        return False

    last_commit_id = object_attributes.get('last_commit', {}).get('id', '')
    oldrev = object_attributes.get('oldrev', '')
    if not last_commit_id or not oldrev:
        return False

    return last_commit_id != oldrev
