from modules.utils.logic import get_safe_tags

def test_get_safe_tags_from_list():
    user = {"tags": ["поиск-любви", "свобода"]}
    assert get_safe_tags(user) == ["поиск-любви", "свобода"]

def test_get_safe_tags_from_string_json():
    user = {"tags": '["поиск-любви", "свобода"]'}
    assert get_safe_tags(user) == ["поиск-любви", "свобода"]

def test_get_safe_tags_from_string_ast():
    user = {"tags": "['поиск-любви', 'свобода']"}
    assert get_safe_tags(user) == ["поиск-любви", "свобода"]

def test_get_safe_tags_filters_junk():
    user = {"tags": ["поиск-любви", "[", "]", "{", "}", "a", "ab", "None", "null"]}
    assert get_safe_tags(user) == ["поиск-любви"]

def test_get_safe_tags_empty_cases():
    assert get_safe_tags({"tags": []}) == []
    assert get_safe_tags({"tags": None}) == []
    assert get_safe_tags({}) == []
    assert get_safe_tags({"tags": ""}) == []
    assert get_safe_tags({"tags": "[]"}) == []
    assert get_safe_tags({"tags": "invalid"}) == ["invalid"]
