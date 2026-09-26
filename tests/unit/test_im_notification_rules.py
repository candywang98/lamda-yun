import pytest
from cloudctl_api.im_classification import notification_rule


@pytest.mark.parametrize(
    "title,text,category",
    [
        ("lucas", "发来一条新消息", "HUMAN_MESSAGE"),
        ("昵称很长但不应该被丢弃" * 4, "发来一条新消息", "HUMAN_MESSAGE"),
        ("闲鱼官方", "订单已发货", "SYSTEM_NOTICE"),
        ("闲鱼", "为你推荐精选好物", "PROMOTION"),
        ("闲鱼官方", "发来一条新消息，为你推荐精选好物", "PROMOTION"),
        ("闲鱼", "发来一条新消息", "UNKNOWN"),
        ("用户", "我收到系统通知，请问怎么退款？", "UNKNOWN"),
        ("客服", "领取优惠券", "UNKNOWN"),
        ("a", "你好", "UNKNOWN"),
        ("", "发来一条新消息", "UNKNOWN"),
    ],
)
def test_conservative_rules_without_nickname_or_channel_only_proof(title, text, category):
    assert notification_rule(title, text, {"category": "msg", "channelId": "chat"})[0] == category
