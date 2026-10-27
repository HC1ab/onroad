import psycopg

from .settings import get_settings


def ping() -> bool:
    """DB에 연결해 SELECT 1 이 되는지 본다. 실패 이유는 밖으로 내보내지 않는다."""
    try:
        with psycopg.connect(get_settings().db_dsn) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False
