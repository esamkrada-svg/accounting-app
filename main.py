from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, text
from datetime import datetime, date
import pandas as pd
import io

# --------------------
# App & Templates
# --------------------
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --------------------
# Database
# --------------------
engine = create_engine(
    "sqlite:///database.db",
    connect_args={"check_same_thread": False}
)

# --------------------
# Create Tables
# --------------------
with engine.begin() as conn:
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS journal_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_no INTEGER,
        date TEXT,
        currency TEXT,
        description TEXT,
        account TEXT,
        debit REAL,
        credit REAL,
        person_tag TEXT,
        type_tag TEXT,
        posted INTEGER DEFAULT 0,
        created_at TEXT
    )
    """))

    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )
    """))

    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS persons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )
    """))

    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS currencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE
    )
    """))

# --------------------
# Review Page
# --------------------
@app.get("/", response_class=HTMLResponse)
def review(request: Request):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                entry_no,
                date,
                currency,
                description,
                SUM(debit) AS total_debit,
                SUM(credit) AS total_credit
            FROM journal_entries
            WHERE posted = 0
            GROUP BY entry_no, date, currency, description
            ORDER BY entry_no
        """)).mappings().all()

    return templates.TemplateResponse(
        "review.html",
        {"request": request, "entries": rows}
    )

# --------------------
# Import Excel (JOURNAL_RAW)
# --------------------
@app.post("/import-excel")
async def import_excel(file: UploadFile = File(...)):
    content = await file.read()
    df = pd.read_excel(io.BytesIO(content), sheet_name="JOURNAL_RAW")

    df.columns = [
        "EntryNo",
        "Date",
        "Currency",
        "Description",
        "Account",
        "Debit",
        "Credit",
        "PersonTag",
        "TypeTag"
    ]

    df["Debit"] = df["Debit"].fillna(0)
    df["Credit"] = df["Credit"].fillna(0)

    with engine.begin() as conn:
        # Clean previous data (first import)
        conn.execute(text("DELETE FROM journal_entries"))
        conn.execute(text("DELETE FROM accounts"))
        conn.execute(text("DELETE FROM persons"))
        conn.execute(text("DELETE FROM currencies"))

        for _, r in df.iterrows():
            entry_no = int(r["EntryNo"])

            d = r["Date"]
            if pd.isna(d):
                d = date.today().isoformat()
            else:
                d = pd.to_datetime(d).date().isoformat()

            conn.execute(text("""
                INSERT OR IGNORE INTO accounts(name) VALUES (:a)
            """), {"a": r["Account"]})

            conn.execute(text("""
                INSERT OR IGNORE INTO persons(name) VALUES (:p)
            """), {"p": r["PersonTag"]})

            conn.execute(text("""
                INSERT OR IGNORE INTO currencies(code) VALUES (:c)
            """), {"c": r["Currency"]})

            conn.execute(text("""
                INSERT INTO journal_entries
                (entry_no, date, currency, description,
                 account, debit, credit, person_tag, type_tag,
                 posted, created_at)
                VALUES
                (:e, :d, :c, :desc,
                 :a, :de, :cr, :p, :t,
                 0, :now)
            """), {
                "e": entry_no,
                "d": d,
                "c": r["Currency"],
                "desc": r["Description"],
                "a": r["Account"],
                "de": float(r["Debit"]),
                "cr": float(r["Credit"]),
                "p": r["PersonTag"],
                "t": r["TypeTag"],
                "now": datetime.now().isoformat()
            })

    return RedirectResponse("/", status_code=303)

# --------------------
# Post Entry
# --------------------
@app.post("/post/{entry_no}")
def post_entry(entry_no: int):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE journal_entries
            SET posted = 1
            WHERE entry_no = :e
        """), {"e": entry_no})

    return RedirectResponse("/", status_code=303)
