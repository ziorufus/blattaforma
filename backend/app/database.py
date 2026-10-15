from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def add_missing_column(table: str, column: str, ddl: str) -> None:
    """create_all crea solo le tabelle mancanti, non aggiunge colonne a quelle
    esistenti: questa è la (minima) migrazione per i DB creati prima che la
    colonna esistesse. `ddl` è la definizione SQL, es. "BOOLEAN NOT NULL DEFAULT 1"."""
    if column in {c["name"] for c in inspect(engine).get_columns(table)}:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    except OperationalError:
        # Gli altri worker uvicorn eseguono lo stesso bootstrap in parallelo:
        # se uno ha appena aggiunto la colonna, l'ALTER qui fallisce.
        if column not in {c["name"] for c in inspect(engine).get_columns(table)}:
            raise
