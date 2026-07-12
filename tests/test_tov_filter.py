from ai.logic import sanitize_premium_tov


def test_tov_filter_phrases():
    # Test specific phrases
    assert "пришло время услышь зов силы" in sanitize_premium_tov(
        "пришло время ХВАТИТ НЫТЬ"
    )
    assert "обрати свой взор на" in sanitize_premium_tov("Разуй Глаза на")
    assert "ты на пороге выбора" in sanitize_premium_tov("ты тормозишь")


def test_tov_filter_procrastination():
    # Test cases/endings of procrastination
    assert "период созерцания" in sanitize_premium_tov("прокрастинация")
    assert "периода созерцания" in sanitize_premium_tov("прокрастинации")
    assert "периодом созерцания" in sanitize_premium_tov("прокрастинацией")


def test_tov_filter_laziness():
    # Test cases/endings of laziness
    assert "замедление" in sanitize_premium_tov("лень")
    assert "замедления" in sanitize_premium_tov("лени")
    assert "замедлением" in sanitize_premium_tov("ленью")


def test_tov_filter_passivity():
    # Test passivity
    assert "созерцательность" in sanitize_premium_tov("пассивность")
    assert "созерцательности" in sanitize_premium_tov("пассивности")
    assert "созерцательностью" in sanitize_premium_tov("пассивностью")


def test_tov_filter_caps_man():
    # Test caps МУЖЧИНА
    assert "Искатель" in sanitize_premium_tov("ТЫ МУЖЧИНА")
    assert "Искатели" in sanitize_premium_tov("ТЫ МУЖЧИНЫ")
    assert "мужчина" in sanitize_premium_tov("ты мужчина")  # Lowercase is allowed


if __name__ == "__main__":
    test_tov_filter_phrases()
    test_tov_filter_procrastination()
    test_tov_filter_laziness()
    test_tov_filter_passivity()
    test_tov_filter_caps_man()
    print("All TOV filter tests passed!")
