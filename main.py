from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, text
from datetime import datetime

app = FastAPI()
templates = Jinja2Templates(directory="templates")

engine = create_engine(
    "sqlite:///database.db",
    connect_args={"check_same_thread": False}
)

# Create tables
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
        updated_at TEXT
    )
    """))

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    with engine.connect() as conn:
        entries = conn.execute(
            text("SELECT * FROM journal_entries ORDER BY entry_no")
        ).fetchall()

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "entries": entries}
    )

@app.post("/add")
def add_entry(
    date: str = Form(...),
    currency: str = Form(...),
    description: str = Form(...),
    account: str = Form(...),
    amount: float = Form(...),
    entry_type: str = Form(...),
    person: str = Form(...),
    type_tag: str = Form("")
):
    debit = amount if entry_type == "Debit" else 0
    credit = amount if entry_type == "Credit" else 0

    with engine.begin() as conn:
        next_no = conn.execute(
            text("SELECT COALESCE(MAX(entry_no),0)+1 FROM journal_entries")
        ).scalar()

        conn.execute(text("""
        INSERT INTO journal_entries
        (entry_no, date, currency, description, account,
         debit, credit, person_tag, type_tag, updated_at)
        VALUES (:en, :d, :c, :desc, :acc,
                :deb, :cred, :p, :t, :u)
        """), {
            "en": next_no,
            "d": date,
            "c": currency,
            "desc": description,
            "acc": account,
            "deb": debit,
            "cred": credit,
            "p": person,
            "t": type_tag,
            "u": datetime.now().isoformat()
        })

    return RedirectResponse("/", status_code=303)
