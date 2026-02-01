from fastapi import FastAPI, Request, UploadFile, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, text
from datetime import datetime, date
import pandas as pd
import io

app = FastAPI()
templates = Jinja2Templates(directory="templates")

engine = create_engine(
    "sqlite:///database.db",
    connect_args={"check_same_thread": False}
)

# --- Create tables ---
with engine.begin() as conn:
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS journal_header (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_no INTEGER,
        date TEXT,
        currency TEXT,
        description TEXT,
        created_at TEXT
    )
    """))

    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS journal_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_no INTEGER,
        account TEXT,
        debit REAL,
        credit REAL,
        person TEXT,
        type_tag TEXT
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

# --- Home / Review ---
@app.get("/", response_class=HTMLResponse)
def review(request: Request):
    with engine.connect() as conn:
        rows = conn.execute(text("""
        SELECT h.entry_no, h.date, h.currency, h.description,
               COUNT(l.id) AS lines,
               SUM(l.debit) AS debit,
               SUM(l.credit) AS credit
        FROM journal_header h
        JOIN journal_lines l ON h.entry_no = l.entry_no
        GROUP BY h.entry_no, h.date, h.currency, h.description
        ORDER BY h.entry_no
        """)).fetchall()

    return templates.TemplateResponse(
        "review.html",
        {"request": request, "rows": rows}
    )

# --- Import Excel ---
@app.post("/import")
async def import_excel(file: UploadFile):
    content = await file.read()
    df = pd.read_excel(io.BytesIO(content), sheet_name="JOURNAL_RAW")

    with engine.begin() as conn:
        # clear old data
        conn.execute(text("DELETE FROM journal_header"))
        conn.execute(text("DELETE FROM journal_lines"))
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

            currency = r["Currency"]
            desc = r["Description"]
            acc = r["Account"]
            debit = float(r["Debit"]) if not pd.isna(r["Debit"]) else 0
            credit = float(r["Credit"]) if not pd.isna(r["Credit"]) else 0
            person = r["PersonTag"]
            tag = r["TypeTag"]

            conn.execute(text("""
            INSERT OR IGNORE INTO accounts(name) VALUES(:a)
            """), {"a": acc})

            conn.execute(text("""
            INSERT OR IGNORE INTO persons(name) VALUES(:p)
            """), {"p": person})

            conn.execute(text("""
            INSERT OR IGNORE INTO currencies(code) VALUES(:c)
            """), {"c": currency})

            exists = conn.execute(
                text("SELECT COUNT(*) FROM journal_header WHERE entry_no=:e"),
                {"e": entry_no}
            ).scalar()

            if exists == 0:
                conn.execute(text("""
                INSERT INTO journal_header
                (entry_no, date, currency, description, created_at)
                VALUES (:e, :d, :c, :desc, :t)
                """), {
                    "e": entry_no,
                    "d": d,
                    "c": currency,
                    "desc": desc,
                    "t": datetime.now().isoformat()
                })

            conn.execute(text("""
            INSERT INTO journal_lines
            (entry_no, account, debit, credit, person, type_tag)
            VALUES (:e, :a, :de, :cr, :p, :t)
            """), {
                "e": entry_no,
                "a": acc,
                "de": debit,
                "cr": credit,
                "p": person,
                "t": tag
            })

    return RedirectResponse("/", status_code=303)
from fastapi import UploadFile, File
import pandas as pd

@app.post("/import-excel")
async def import_excel(file: UploadFile = File(...)):
    # قراءة ملف Excel
    df = pd.read_excel(file.file, sheet_name="JOURNAL_RAW")

    # تأكد من ترتيب الأعمدة (اختياري للحماية)
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

    # تنظيف البيانات
    df["Debit"] = df["Debit"].fillna(0)
    df["Credit"] = df["Credit"].fillna(0)

    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(text("""
                INSERT INTO journal_entries
                (entry_no, date, currency, description,
                 account, debit, credit, person_tag, type_tag)
                VALUES
                (:entry_no, :date, :currency, :description,
                 :account, :debit, :credit, :person_tag, :type_tag)
            """), {
                "entry_no": row["EntryNo"],
                "date": row["Date"],
                "currency": row["Currency"],
                "description": row["Description"],
                "account": row["Account"],
                "debit": row["Debit"],
                "credit": row["Credit"],
                "person_tag": row["PersonTag"],
                "type_tag": row["TypeTag"]
            })

    return {"status": "success", "rows_imported": len(df)}
