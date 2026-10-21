# database.py
import aiosqlite
import calendar
from datetime import datetime
from config import WEEKLY_TO_MONTHLY

DB_PATH = "budce.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                salary_day INTEGER DEFAULT 20,
                monthly_income REAL DEFAULT 0,
                income_month TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                note TEXT DEFAULT '',
                date TEXT NOT NULL,
                card_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS fixed_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT DEFAULT 'Digər',
                frequency TEXT DEFAULT 'monthly',
                pay_day INTEGER DEFAULT 1,
                auto_create INTEGER DEFAULT 1,
                last_run TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                total REAL NOT NULL,
                payment REAL NOT NULL,
                paid REAL DEFAULT 0,
                frequency TEXT DEFAULT 'monthly',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                bank TEXT NOT NULL,
                brand TEXT NOT NULL,
                holder TEXT NOT NULL,
                last4 TEXT NOT NULL,
                expiry TEXT NOT NULL,
                apple_pay INTEGER DEFAULT 0,
                google_pay INTEGER DEFAULT 0,
                nfc INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await db.commit()


async def ensure_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_salary_day(user_id: int, day: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET salary_day = ? WHERE user_id = ?", (day, user_id))
        await db.commit()


async def set_monthly_income(user_id: int, amount: float, month: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET monthly_income = ?, income_month = ? WHERE user_id = ?",
            (amount, month, user_id),
        )
        await db.commit()


async def add_transaction(user_id, type_, amount, category, note, date):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO transactions (user_id, type, amount, category, note, date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, type_, amount, category, note, date),
        )
        await db.commit()


async def get_transactions(user_id: int, limit: int = 15):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_totals(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT type, SUM(amount) FROM transactions WHERE user_id = ? GROUP BY type",
            (user_id,),
        )
        rows = await cur.fetchall()
        return {row[0]: row[1] or 0 for row in rows}


async def add_fixed_expense(user_id, name, amount, category, frequency, pay_day):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO fixed_expenses (user_id, name, amount, category, frequency, pay_day)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, name, amount, category, frequency, pay_day),
        )
        await db.commit()


async def get_fixed_expenses(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM fixed_expenses WHERE user_id = ?", (user_id,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def delete_fixed_expense(exp_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM fixed_expenses WHERE id = ? AND user_id = ?", (exp_id, user_id))
        await db.commit()


async def add_debt(user_id, name, total, payment, frequency):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO debts (user_id, name, total, payment, frequency) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, total, payment, frequency),
        )
        await db.commit()


async def get_debts(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM debts WHERE user_id = ?", (user_id,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def pay_debt(debt_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM debts WHERE id = ? AND user_id = ?", (debt_id, user_id))
        debt = await cur.fetchone()
        if not debt:
            return None
        new_paid = min(debt["total"], debt["paid"] + debt["payment"])
        await db.execute("UPDATE debts SET paid = ? WHERE id = ?", (new_paid, debt_id))
        await db.commit()
        return dict(debt)


async def delete_debt(debt_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM debts WHERE id = ? AND user_id = ?", (debt_id, user_id))
        await db.commit()


async def add_card(user_id, bank, brand, holder, last4, expiry):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO cards (user_id, bank, brand, holder, last4, expiry)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, bank, brand, holder, last4, expiry),
        )
        await db.commit()


async def get_cards(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM cards WHERE user_id = ?", (user_id,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def delete_card(card_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM cards WHERE id = ? AND user_id = ?", (card_id, user_id))
        await db.commit()


def to_monthly(amount: float, freq: str) -> float:
    if freq == "weekly":
        return amount * WEEKLY_TO_MONTHLY
    return amount


async def calculate_daily_limit(user_id: int):
    user = await get_user(user_id)
    if not user or user["monthly_income"] <= 0:
        return None

    today = datetime.now()
    current_month = today.strftime("%Y-%m")
    monthly_income = user["monthly_income"] if user["income_month"] == current_month else 0
    if monthly_income <= 0:
        return None

    fixed = await get_fixed_expenses(user_id)
    fixed_total = sum(to_monthly(f["amount"], f["frequency"]) for f in fixed)

    debts = await get_debts(user_id)
    debts_total = sum(to_monthly(d["payment"], d["frequency"]) for d in debts)

    remaining_amount = monthly_income - fixed_total - debts_total

    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_left = max(1, days_in_month - today.day + 1)

    month_start = f"{today.year}-{today.month:02d}-01"
    month_end = f"{today.year}-{today.month:02d}-{days_in_month:02d}"
    today_iso = today.strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM transactions 
               WHERE user_id = ? AND type = 'expense' AND date >= ? AND date <= ?""",
            (user_id, month_start, month_end),
        )
        spent_month = (await cur.fetchone())[0]

        cur = await db.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM transactions 
               WHERE user_id = ? AND type = 'expense' AND date = ?""",
            (user_id, today_iso),
        )
        spent_today = (await cur.fetchone())[0]

    remaining_from_limit = remaining_amount - spent_month
    daily_limit = max(0, remaining_from_limit / days_left)
    today_remaining = daily_limit - spent_today

    return {
        "monthly_income": monthly_income,
        "fixed_total": fixed_total,
        "debts_total": debts_total,
        "remaining_amount": remaining_amount,
        "spent_this_month": spent_month,
        "spent_today": spent_today,
        "remaining_from_limit": remaining_from_limit,
        "days_left": days_left,
        "daily_limit": daily_limit,
        "today_remaining": today_remaining,
    }


def get_salary_info(salary_day: int):
    today = datetime.now()
    y, m = today.year, today.month
    last_day = calendar.monthrange(y, m)[1]
    target_day = min(salary_day, last_day)

    if today.day <= target_day:
        days_left = target_day - today.day
        target = datetime(y, m, target_day)
    else:
        if m == 12:
            ny, nm = y + 1, 1
        else:
            ny, nm = y, m + 1
        next_last = calendar.monthrange(ny, nm)[1]
        next_day = min(salary_day, next_last)
        target = datetime(ny, nm, next_day)
        days_left = (target - today).days

    return {"days_left": days_left, "target_date": target}