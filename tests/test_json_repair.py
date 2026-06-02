import json
from ai.logic import clean_ai_json

def test_clean_ai_json_valid():
    raw = '{"text": "Hello"}'
    assert json.loads(clean_ai_json(raw)) == {"text": "Hello"}

def test_clean_ai_json_markdown():
    raw = '```json\n{"text": "Hello"}\n```'
    assert json.loads(clean_ai_json(raw)) == {"text": "Hello"}

def test_clean_ai_json_repair_missing_brace():
    raw = '{"text": "Hello"'
    cleaned = clean_ai_json(raw)
    assert cleaned.endswith('}')
    assert json.loads(cleaned) == {"text": "Hello"}

def test_clean_ai_json_repair_missing_quote_and_brace():
    raw = '{"text": "Hello'
    cleaned = clean_ai_json(raw)
    assert cleaned.endswith('"}')
    assert json.loads(cleaned) == {"text": "Hello"}

def test_clean_ai_json_repair_nested_array():
    raw = '{"facts": ["one", "two"'
    cleaned = clean_ai_json(raw)
    assert json.loads(cleaned) == {"facts": ["one", "two"]}

def test_clean_ai_json_with_garbage():
    raw = 'Some text before {"text": "Hello"} and after'
    assert json.loads(clean_ai_json(raw)) == {"text": "Hello"}

def test_clean_ai_json_incomplete_array():
    raw = '["item1", "item2"'
    cleaned = clean_ai_json(raw)
    assert json.loads(cleaned) == ["item1", "item2"]
