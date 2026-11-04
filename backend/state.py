"""The process-wide database handle (bound once by server.create_app or by tests)."""
_db = {"db": None}


def set_db(db) -> None:
    _db["db"] = db


def db():
    if _db["db"] is None:
        raise RuntimeError("database not bound")
    return _db["db"]
