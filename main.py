from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, text
from datetime import datetime

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --------------------
# Database (SQLite)
# --------------------
engine = create_engine(
    "sqlite:///database.db",
    connect_args={"check_same_thread": False}
)

# --------------------
# Create Tables
# --------------------
with engine.begin() as conn:
    # Chart of Accounts
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        is_postable INTEGER DEFAULT 1,
        created_at TEXT
    )
    """))

    # Persons
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS persons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        category TEXT,
        created_at TEXT
    )
    """))

    # Currencies
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS currencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT
    )
    """))

    # Journal Header
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS journal_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_no INTEGER UNIQUE,
        entry_date TEXT,
        description TEXT,
        currency TEXT,
        status TEXT DEFAULT 'DRAFT',
        created_at TEXT
    )
    """))

    # Journal Lines
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS journal_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        journal_id INTEGER,
        account_id INTEGER,
        debit REAL DEFAULT 0,
        credit REAL DEFAULT 0,
        person_id INTEGER,
        note TEXT
    )
    """))

# --------------------
# Home - List Entries
# --------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with engine.connect() as conn:
        entries = conn.execute(text("""
            SELECT id, entry_no, entry_date, description, currency, status
            FROM journal_entries
            ORDER BY entry_no DESC
        """)).mappings().all()

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "entries": entries}
    )

# --------------------
# New Journal Entry
# --------------------
@app.post("/entry/new")
def new_entry(
    entry_no: int = Form(...),
    entry_date: str = Form(...),
    description: str = Form(...),
    currency: str = Form(...)
):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO journal_entries
            (entry_no, entry_date, description, currency, status, created_at)
            VALUES (:n, :d, :desc, :c, 'DRAFT', :t)
        """), {
            "n": entry_no,
            "d": entry_date,
            "desc": description,
            "c": currency,
            "t": datetime.now().isoformat()
        })

    return RedirectResponse("/", status_code=303)

# --------------------
# Add Line to Entry
# --------------------
@app.post("/entry/{entry_id}/line")
def add_line(
    entry_id: int,
    account_id: int = Form(...),
    debit: float = Form(0),
    credit: float = Form(0),
    person_id: int = Form(None),
    note: str = Form("")
):
    with engine.begin() as conn:
        status = conn.execute(
            text("SELECT status FROM journal_entries WHERE id=:i"),
            {"i": entry_id}
        ).scalar()

        if status != "DRAFT":
            return {"error": "Entry already posted"}

        conn.execute(text("""
            INSERT INTO journal_lines
            (journal_id, account_id, debit, credit, person_id, note)
            VALUES (:j, :a, :d, :c, :p, :n)
        """), {
            "j": entry_id,
            "a": account_id,
            "d": debit,
            "c": credit,
            "p": person_id,
            "n": note
        })

    return RedirectResponse("/", status_code=303)

# --------------------
# Post Journal Entry
# --------------------
@app.post("/entry/{entry_id}/post")
def post_entry(entry_id: int):
    with engine.begin() as conn:
        totals = conn.execute(text("""
            SELECT SUM(debit), SUM(credit)
            FROM journal_lines
            WHERE journal_id=:j
        """), {"j": entry_id}).fetchone()

        if totals[0] != totals[1]:
            return {"error": "Debit and Credit not balanced"}

        conn.execute(text("""
            UPDATE journal_entries
            SET status='POSTED'
            WHERE id=:j
        """), {"j": entry_id})

    return RedirectResponse("/", status_code=303)
