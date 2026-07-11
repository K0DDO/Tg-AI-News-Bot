from app.services.filter import RuleBasedFilter


def test_filter_passes_normal_news():
    f = RuleBasedFilter()
    result = f.evaluate(
        "Apple представила новый MacBook Pro с обновлённым чипом M4 и улучшенным дисплеем."
    )
    assert result.passed is True
    assert result.reason is None


def test_filter_blocks_promocode():
    f = RuleBasedFilter()
    result = f.evaluate("Лови промокод SALE2024 на все курсы прямо сейчас!")
    assert result.passed is False
    assert result.reason == "promocode"


def test_filter_blocks_subscribe_cta():
    f = RuleBasedFilter()
    result = f.evaluate("Друзья, подпишитесь на наш канал чтобы не пропустить новости технологий")
    assert result.passed is False
    assert result.reason == "subscribe_cta"


def test_filter_blocks_empty():
    assert RuleBasedFilter().evaluate("   ").passed is False
