from blinker import Signal

from biz.entity.review_entity import MergeRequestReviewEntity, PushReviewEntity
from biz.service.review_service import ReviewService

# 定义全局事件管理器（事件信号）
event_manager = {
    "merge_request_reviewed": Signal(),
    "push_reviewed": Signal(),
}


# 定义事件处理函数
def on_merge_request_reviewed(mr_review_entity: MergeRequestReviewEntity):
    # 记录到数据库
    ReviewService().insert_mr_review_log(mr_review_entity)


def on_push_reviewed(entity: PushReviewEntity):
    # 记录到数据库
    ReviewService().insert_push_review_log(entity)


# 连接事件处理函数到事件信号
event_manager["merge_request_reviewed"].connect(on_merge_request_reviewed)
event_manager["push_reviewed"].connect(on_push_reviewed)
