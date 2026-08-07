import datetime
import pytest

def check_inactivity(last_active, now):
    if last_active:
        # Обрабатываем как ISO строку (может быть с Z или без)
        last_active_clean = last_active.replace('Z', '+00:00')
        last_date = datetime.datetime.fromisoformat(last_active_clean)
        # Приводим now к тому же типу (offset-aware)
        days_since = (now - last_date).days
        if days_since > 7:
            return True  # Skip user
    return False  # Process user

def test_inactivity_check_active_now():
    now = datetime.datetime.now(datetime.timezone.utc)
    last_active = now.isoformat()
    assert check_inactivity(last_active, now) is False

def test_inactivity_check_active_3_days_ago():
    now = datetime.datetime.now(datetime.timezone.utc)
    last_active = (now - datetime.timedelta(days=3)).isoformat()
    assert check_inactivity(last_active, now) is False

def test_inactivity_check_active_7_days_ago():
    now = datetime.datetime.now(datetime.timezone.utc)
    last_active = (now - datetime.timedelta(days=7)).isoformat()
    assert check_inactivity(last_active, now) is False

def test_inactivity_check_active_7_days_and_half_ago():
    now = datetime.datetime.now(datetime.timezone.utc)
    last_active = (now - datetime.timedelta(days=7, hours=12)).isoformat()
    assert check_inactivity(last_active, now) is False

def test_inactivity_check_active_8_days_ago_skips():
    now = datetime.datetime.now(datetime.timezone.utc)
    last_active = (now - datetime.timedelta(days=8)).isoformat()
    assert check_inactivity(last_active, now) is True

def test_inactivity_check_active_10_days_ago_skips():
    now = datetime.datetime.now(datetime.timezone.utc)
    last_active = (now - datetime.timedelta(days=10)).isoformat()
    assert check_inactivity(last_active, now) is True

def test_inactivity_check_z_suffix():
    now = datetime.datetime.now(datetime.timezone.utc)
    # Simulate a Z-suffixed ISO string from PostgreSQL/Supabase
    last_active = (now - datetime.timedelta(days=8)).isoformat().replace('+00:00', 'Z')
    assert check_inactivity(last_active, now) is True
