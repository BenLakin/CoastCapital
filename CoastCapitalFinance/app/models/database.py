"""Database connection and session management."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
from typing import Generator
from app.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass


def create_db_engine():
    return create_engine(
        settings.DATABASE_URL,
        poolclass=QueuePool,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
    )


engine = create_db_engine()
SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager for database sessions with automatic commit/rollback."""
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("Database session error", error=str(e))
        raise
    finally:
        session.close()


def init_db() -> None:
    """Initialize the database schema."""
    from app.models import schema  # noqa: F401 - registers models
    logger.info("Initializing database schema")
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized")


def check_db_health() -> dict:
    """Check database connectivity."""
    try:
        with get_db() as db:
            db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": settings.MYSQL_DATABASE}
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return {"status": "unhealthy", "error": str(e)}
