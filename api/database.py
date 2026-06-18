import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, scoped_session

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_engine = None
_Session = None


def init_db(database_url: str):
    global _engine, _Session
    _engine = create_engine(
        database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # reconnect after Postgres restart
        echo=False,
    )
    _Session = scoped_session(sessionmaker(bind=_engine))

    # Import models so Base knows about them before create_all
    import models  # noqa: F401

    Base.metadata.create_all(_engine)
    logger.info("Database tables created / verified")


def get_session():
    if _Session is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _Session()


def remove_session():
    if _Session:
        _Session.remove()
