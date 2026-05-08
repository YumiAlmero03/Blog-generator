from app.services.word_limit_settings import normalize_word_limits


def test_normalize_word_limits_uses_defaults_for_invalid_values():
    assert normalize_word_limits("bad", "", 900, 1200) == (900, 1200)


def test_normalize_word_limits_never_allows_max_below_min():
    assert normalize_word_limits("1000", "700", 900, 1200) == (1000, 1000)


def test_normalize_word_limits_forces_positive_values():
    assert normalize_word_limits("-5", "0", 900, 1200) == (1, 1)
