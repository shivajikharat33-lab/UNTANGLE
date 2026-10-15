"""Package location for the UNTANGLE database.

SQLite tables are not built yet. Do not treat this module as a database connection.
"""


def init_db() -> None:
    raise RuntimeError(
        "The UNTANGLE database is not built yet. "
        "This file only reserves the package location."
    )
