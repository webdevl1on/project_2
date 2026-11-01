import pytest
from app.database.settings import Settings

@pytest.mark.parametrize('mode,url',[('production','sqlite:///main.db'),('testing','postgresql+psycopg://example@localhost/project2_prod'),('testing','postgresql+psycopg://example@localhost/project2_dev'),('development','postgresql+psycopg://example@localhost/project2_prod')])
def test_environment_rejects_unsafe_database(mode,url,monkeypatch):
    monkeypatch.setenv('PROJECT2_ENV',mode);monkeypatch.setenv('DATABASE_URL',url)
    with pytest.raises(ValueError):Settings.read()


def test_absent_config_never_falls_back(monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    with pytest.raises(ValueError,match='DATABASE_URL'):Settings.read()


def test_production_requires_auth_paths_and_stable_key(monkeypatch,tmp_path):
    monkeypatch.setenv('PROJECT2_ENV','production');monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://example@localhost/project2_prod')
    for flag in ('PROJECT2_DEV_ADMIN_OPEN','PROJECT2_DEV_AUTH_BYPASS'):monkeypatch.delenv(flag,raising=False)
    monkeypatch.setenv('STAFF_SIGNING_KEY','synthetic-test-only-key-0123456789')
    for key in ('DOCUMENT','PHOTO','TEMP','EXPORT','BACKUP'):monkeypatch.setenv('PROJECT2_'+key+'_STORAGE',str(tmp_path/key))
    monkeypatch.setenv('PROJECT2_AUTH_ENABLED','0')
    with pytest.raises(ValueError):Settings.read()
    monkeypatch.setenv('PROJECT2_AUTH_ENABLED','1');assert Settings.read().environment=='production'
    monkeypatch.setenv('PROJECT2_DEV_ADMIN_OPEN','1')
    with pytest.raises(ValueError):Settings.read()


def test_reset_rejects_configured_postgresql_before_any_io(monkeypatch,tmp_path):
    import reset
    monkeypatch.setenv('PROJECT2_ENV','testing')
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://example@localhost/project2_ci')
    target=tmp_path/'untouched-test.sqlite3'
    with pytest.raises(SystemExit) as stopped:
        reset.main(['--database',str(target),'--dry-run'])
    assert stopped.value.code==2 and not target.exists()
