def should_review_gitlab_merge_request(object_attributes: dict, action: str) -> bool:
    """Review MR events that carry a concrete source-branch commit."""
    if action not in {'open', 'reopen', 'update'}:
        return False

    last_commit_id = object_attributes.get('last_commit', {}).get('id', '')
    return bool(last_commit_id)
