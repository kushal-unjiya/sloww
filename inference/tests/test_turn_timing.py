from src.shared.turn_timing import timeline_segments


def test_timeline_segments() -> None:
    marks = [
        {"phase": "a", "elapsed_ms": 3000},
        {"phase": "b", "elapsed_ms": 5000},
        {"phase": "c", "elapsed_ms": 12000},
    ]
    segs = timeline_segments(marks)
    assert segs[0]["phase"] == "a" and segs[0]["segment_ms"] == 3000
    assert segs[1]["phase"] == "b" and segs[1]["segment_ms"] == 2000
    assert segs[2]["phase"] == "c" and segs[2]["segment_ms"] == 7000
