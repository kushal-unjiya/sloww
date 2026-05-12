from src.orchestration.nodes import _heuristic_chitchat_intent


def test_heuristic_who_are_you() -> None:
    tag = _heuristic_chitchat_intent("who are you?")
    assert tag is not None
    assert tag.is_chitchat is True
    assert tag.needs_retrieval is False


def test_heuristic_not_biography_query() -> None:
    assert _heuristic_chitchat_intent("who is Kushal?") is None


def test_heuristic_hi() -> None:
    tag = _heuristic_chitchat_intent("hi")
    assert tag is not None and tag.is_chitchat
