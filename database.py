import os
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool


def setting(name, default=None):
    filename = os.environ.get(f"{name}_FILE")
    if filename:
        return Path(filename).read_text(encoding="utf-8").rstrip("\r\n")
    return os.environ.get(name, default)


def connection_options():
    return {
        "host": setting("POSTGRES_HOST", "localhost"),
        "port": setting("POSTGRES_PORT", "5432"),
        "dbname": setting("POSTGRES_DB", "pli_service"),
        "user": setting("POSTGRES_USER", "pli_app"),
        "password": setting("POSTGRES_PASSWORD"),
        "connect_timeout": 5,
        "options": "-c statement_timeout=15000 -c lock_timeout=5000",
    }


class Database:
    def __init__(self, dsn=None, max_connections=4):
        self.dsn = dsn
        self.max_connections = max_connections
        self.pool = None
        self.lock = Lock()

    def get_pool(self):
        with self.lock:
            if self.pool is None:
                args = {"dsn": self.dsn} if self.dsn else connection_options()
                self.pool = ThreadedConnectionPool(1, self.max_connections, **args)
            return self.pool

    @contextmanager
    def transaction(self):
        pool = self.get_pool()
        connection = pool.getconn()
        try:
            with connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
                yield cursor
        finally:
            pool.putconn(connection, close=bool(connection.closed))


@contextmanager
def migration_connection():
    options = connection_options() | {"options": "-c statement_timeout=0 -c lock_timeout=10000"}
    connection = psycopg2.connect(**options)
    try:
        yield connection
    finally:
        connection.close()
