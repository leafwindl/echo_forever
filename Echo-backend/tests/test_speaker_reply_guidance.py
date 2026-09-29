import pytest

from features.chat.application.generate_reply import _speaker_guidance


@pytest.mark.parametrize("score", [0.65, 0.70, 0.75])
def test_tentative_match_can_ask(score):
    assert "试探性确认" in _speaker_guidance("known", score, "Alice", "我是谁？")


@pytest.mark.parametrize("score", [0.751, 0.786, 0.799])
def test_middle_band_is_cautious(score):
    assert "听起来像" in _speaker_guidance("known", score, "Alice", "我是谁？")


@pytest.mark.parametrize("score", [0.80, 0.836, 1.0])
def test_strong_match_uses_name_without_identity_question(score):
    text = _speaker_guidance("known", score, "Alice", "我是谁？")
    assert "直接回答匹配称呼" in text
    assert "不是身份授权" in text
    assert "Alice" in text


@pytest.mark.parametrize("role,score,name", [
    ("unknown", 0.9, "Alice"),
    ("known", 0.64, "Alice"),
    ("known", 0.9, ""),
    ("known", float("nan"), "Alice"),
])
def test_unreliable_match_does_not_expose_candidate(role, score, name):
    text = _speaker_guidance(role, score, name, "我是谁？")
    assert "不猜测" in text
    assert "Alice" not in text


@pytest.mark.parametrize("score", [0.31, 0.65, 0.75, 0.78, 0.80, 0.86])
@pytest.mark.parametrize("message", [
    "今天有点累，想休息一下",
    "然后呢？",
    "你为什么每句话都猜我是谁？不要再猜了",
    "不用确认我是谁，继续刚才的话题",
])
def test_ordinary_turns_never_expose_name_or_score(score, message):
    text = _speaker_guidance("known", score, "Alice", message)
    assert "Alice" not in text
    assert str(score) not in text
    assert "不添加称呼或身份猜测" in text


def test_fluctuating_scores_do_not_change_ordinary_turn_guidance():
    assert len({
        _speaker_guidance("known", score, "Alice", "今天有点累")
        for score in [0.65, 0.75, 0.78, 0.80, 0.86]
    }) == 1
