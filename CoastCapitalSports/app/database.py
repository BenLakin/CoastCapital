"""
database.py — MySQL connection factory with per-schema connection pooling.

Reads MYSQL_HOST, MYSQL_PORT, MYSQL_USER, and MYSQL_PASSWORD from environment
variables to connect to the database.  Environment separation (dev vs prod) is
handled by running on separate machines, not by in-app routing.

Usage:
    from database import get_connection
    conn = get_connection("nfl_silver")
"""

import logging
import os

import mysql.connector
from mysql.connector import Error as MySQLError
from mysql.connector import pooling

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolve connection settings
# ---------------------------------------------------------------------------

_MYSQL_HOST = os.getenv("MYSQL_HOST", "coastcapital-mysql")
_MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
_MYSQL_USER = os.getenv("MYSQL_USER", "dbadmin")
_MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")

logger.info("database: host=%s  port=%d  user=%s", _MYSQL_HOST, _MYSQL_PORT, _MYSQL_USER)

# ---------------------------------------------------------------------------
# Connection pool registry — one pool per schema
# ---------------------------------------------------------------------------

_pools: dict[str, pooling.MySQLConnectionPool] = {}
_POOL_SIZE = 25


def _get_pool(schema: str | None) -> pooling.MySQLConnectionPool:
    """Return (or create) a connection pool for the given schema."""
    key = schema or "__no_schema__"
    if key not in _pools:
        pool_name = f"sports_{key}"
        try:
            _pools[key] = pooling.MySQLConnectionPool(
                pool_name=pool_name,
                pool_size=_POOL_SIZE,
                host=_MYSQL_HOST,
                port=_MYSQL_PORT,
                user=_MYSQL_USER,
                password=_MYSQL_PASSWORD,
                database=schema,
                autocommit=True,
            )
            logger.info("Created connection pool '%s' (size=%d)", pool_name, _POOL_SIZE)
        except MySQLError as exc:
            logger.error(
                "Failed to create pool '%s' (host=%s, port=%d, schema=%s): %s",
                pool_name, _MYSQL_HOST, _MYSQL_PORT, schema, exc,
            )
            raise
    return _pools[key]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_connection(schema: str | None = None):
    """Return a pooled mysql.connector connection pointed at *schema*.

    Parameters
    ----------
    schema:
        MySQL schema/database name to select.  Pass ``None`` to connect
        without selecting a database (useful for admin queries).

    Returns
    -------
    mysql.connector.connection.MySQLConnection

    Raises
    ------
    mysql.connector.Error
        Re-raised after logging if the connection attempt fails.
    """
    try:
        return _get_pool(schema).get_connection()
    except MySQLError as exc:
        logger.error(
            "Failed to get connection from pool (host=%s, port=%d, schema=%s): %s",
            _MYSQL_HOST,
            _MYSQL_PORT,
            schema,
            exc,
        )
        raise
