# database_utils.py
import sqlite3
from contextlib import contextmanager
from errors import AppError, ValidationError, ConflictError, NotFoundError, IntegrityError

@contextmanager
def txn(conn):
    try:
        yield
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        # constraints UNIQUE, CHECK, FK
        raise IntegrityError(str(e))
    except AppError:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise AppError(str(e))
