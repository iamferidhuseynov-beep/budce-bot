# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "BURAYA_TOKEN_YAZ")

WEEKLY_TO_MONTHLY = 4.333

CATEGORIES_EXPENSE = [
    ("Qida", "🍔"),
    ("Nəqliyyat", "🚌"),
    ("Kommunal", "💡"),
    ("Əyləncə", "🎬"),
    ("Digər", "📦"),
]

CATEGORIES_INCOME = [
    ("Maaş", "💼"),
    ("Əlavə Gəlir", "💵"),
    ("Digər", "📦"),
]