# main.py
import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

from config import BOT_TOKEN, CATEGORIES_EXPENSE, CATEGORIES_INCOME
from database import (
    init_db, ensure_user, get_user, set_salary_day, set_monthly_income,
    add_transaction, get_transactions, get_totals,
    add_fixed_expense, get_fixed_expenses, delete_fixed_expense,
    add_debt, get_debts, pay_debt, delete_debt,
    add_card, get_cards, delete_card,
    calculate_daily_limit, get_salary_info, to_monthly,
)

logging.basicConfig(level=logging.INFO)
router = Router()


class TxForm(StatesGroup):
    amount = State()
    category = State()
    note = State()


class IncomeForm(StatesGroup):
    amount = State()
    salary_day = State()


class FixedForm(StatesGroup):
    name = State()
    amount = State()
    frequency = State()
    pay_day = State()


class DebtForm(StatesGroup):
    name = State()
    total = State()
    payment = State()
    frequency = State()


class CardForm(StatesGroup):
    bank = State()
    brand = State()
    holder = State()
    last4 = State()
    expiry = State()


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Balans"), KeyboardButton(text="➕ Xərc")],
            [KeyboardButton(text="💰 Gəlir"), KeyboardButton(text="📌 Mütəmadi")],
            [KeyboardButton(text="🏦 Borclar"), KeyboardButton(text="💳 Kartlar")],
            [KeyboardButton(text="📋 Tarixçə"), KeyboardButton(text="⚙️ Ayarlar")],
        ],
        resize_keyboard=True,
    )


def fmt(v):
    return f"{v:,.2f} AZN".replace(",", " ")


@router.message(CommandStart())
async def cmd_start(message: Message):
    await ensure_user(message.from_user.id)
    await message.answer(
        f"👋 Salam, {message.from_user.first_name}!\n\n"
        f"💰 **Büdcə Pro** botuna xoş gəlmisən.\n\n"
        f"Başlamaq üçün:\n"
        f"1. ⚙️ Ayarlar → Aylıq gəlir + maaş günü\n"
        f"2. ➕ Xərc ilə xərcləri qeyd et\n"
        f"3. 📊 Balans ilə izlə\n\n"
        f"Uğurlar! 🚀",
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )


@router.message(F.text == "📊 Balans")
async def show_balance(message: Message):
    user_id = message.from_user.id
    await ensure_user(user_id)
    user = await get_user(user_id)
    daily = await calculate_daily_limit(user_id)
    totals = await get_totals(user_id)

    income_total = totals.get("income", 0)
    expense_total = totals.get("expense", 0)
    balance = income_total - expense_total

    text = f"📊 **BALANS**\n\n"
    text += f"💵 Mədaxil: **{fmt(income_total)}**\n"
    text += f"💸 Məxaric: **{fmt(expense_total)}**\n"
    text += f"{'📈' if balance >= 0 else '📉'} Balans: **{fmt(balance)}**\n"

    if daily:
        salary = get_salary_info(user["salary_day"])
        text += f"\n{'━'*20}\n\n"
        text += f"📅 **GÜNDƏLİK LİMİT**\n\n"
        text += f"💰 Aylıq gəlir: {fmt(daily['monthly_income'])}\n"
        text += f"📌 Mütəmadi: −{fmt(daily['fixed_total'])}\n"
        text += f"🏦 Borclar: −{fmt(daily['debts_total'])}\n"
        text += f"─────────────────\n"
        text += f"💡 Qalan pul: **{fmt(daily['remaining_amount'])}**\n\n"
        text += f"📆 Bu ay xərclənib: {fmt(daily['spent_this_month'])}\n"
        text += f"⏳ Qalan gün: **{daily['days_left']}**\n"
        text += f"🎯 Gündəlik limit: **{fmt(daily['daily_limit'])}**\n\n"

        if daily["today_remaining"] >= 0:
            text += f"✅ Bugün qalıb: **{fmt(daily['today_remaining'])}**\n"
        else:
            text += f"⚠️ Bugün artıq: **{fmt(abs(daily['today_remaining']))}**\n"

        text += f"\n🥹 Maaşa qalan: **{salary['days_left']} gün** ({salary['target_date'].strftime('%d.%m.%Y')})"
    else:
        text += f"\n⚙️ Aylıq gəliri təyin etmək üçün **⚙️ Ayarlar**"

    await message.answer(text, parse_mode="Markdown")


@router.message(F.text == "➕ Xərc")
async def start_expense(message: Message, state: FSMContext):
    await ensure_user(message.from_user.id)
    await state.update_data(type="expense")
    await state.set_state(TxForm.amount)
    await message.answer("💸 **Xərc**\n\nMəbləği daxil et (AZN):", parse_mode="Markdown")


@router.message(TxForm.amount)
async def tx_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
        if amount <= 0: raise ValueError
    except:
        await message.answer("❌ Düzgün rəqəm daxil et (məs: 25.50)")
        return
    data = await state.get_data()
    await state.update_data(amount=amount)
    await state.set_state(TxForm.category)
    cats = CATEGORIES_EXPENSE if data["type"] == "expense" else CATEGORIES_INCOME
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{e} {n}", callback_data=f"cat:{n}")]
            for n, e in cats
        ]
    )
    await message.answer("📁 Kateqoriya seç:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("cat:"), TxForm.category)
async def tx_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    await state.update_data(category=category)
    await state.set_state(TxForm.note)
    await callback.message.edit_text(
        f"✅ Kateqoriya: **{category}**\n\n📝 Qeyd yaz (və ya /skip):",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(TxForm.note)
async def tx_note(message: Message, state: FSMContext):
    note = "" if message.text == "/skip" else (message.text or "")
    data = await state.get_data()
    today = datetime.now().strftime("%Y-%m-%d")
    await add_transaction(
        message.from_user.id, data["type"], data["amount"],
        data["category"], note, today,
    )
    await state.clear()
    emoji = "💸" if data["type"] == "expense" else "💰"
    await message.answer(
        f"✅ **Yadda saxlanıldı**\n\n"
        f"{emoji} {fmt(data['amount'])}\n"
        f"📁 {data['category']}\n"
        f"📝 {note or '—'}\n"
        f"📅 {today}",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


@router.message(F.text == "💰 Gəlir")
async def start_income(message: Message, state: FSMContext):
    await ensure_user(message.from_user.id)
    user = await get_user(message.from_user.id)
    await state.set_state(IncomeForm.amount)
    await message.answer(
        f"💰 **Aylıq gəlir**\n\n"
        f"Ümumi aylıq gəliri daxil et (AZN):\n"
        f"(hazırkı: {fmt(user['monthly_income']) if user['monthly_income'] else 'yoxdur'})",
        parse_mode="Markdown",
    )


@router.message(IncomeForm.amount)
async def income_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
        if amount <= 0: raise ValueError
    except:
        await message.answer("❌ Düzgün rəqəm")
        return
    await state.update_data(amount=amount)
    await state.set_state(IncomeForm.salary_day)
    await message.answer("📅 Maaş günü (1-31):")


@router.message(IncomeForm.salary_day)
async def income_salary_day(message: Message, state: FSMContext):
    try:
        day = int(message.text)
        if day < 1 or day > 31: raise ValueError
    except:
        await message.answer("❌ 1-31 arası rəqəm")
        return
    data = await state.get_data()
    month = datetime.now().strftime("%Y-%m")
    await set_monthly_income(message.from_user.id, data["amount"], month)
    await set_salary_day(message.from_user.id, day)
    await state.clear()
    await message.answer(
        f"✅ **Yadda saxlanıldı**\n\n"
        f"💰 Aylıq gəlir: **{fmt(data['amount'])}**\n"
        f"📅 Maaş günü: **{day}**\n\n"
        f"📊 Balans düyməsini bas!",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


@router.message(F.text == "📌 Mütəmadi")
async def show_fixed(message: Message):
    user_id = message.from_user.id
    await ensure_user(user_id)
    items = await get_fixed_expenses(user_id)

    if not items:
        text = "📌 **Mütəmadi xərclər**\n\nHələ heç bir yoxdur."
    else:
        text = "📌 **Mütəmadi xərclər**\n\n"
        total = 0
        for it in items:
            monthly = to_monthly(it["amount"], it["frequency"])
            total += monthly
            freq = "📆 Həftəlik" if it["frequency"] == "weekly" else "🗓️ Aylıq"
            text += f"• {it['name']}: {fmt(it['amount'])} {freq}\n"
            if it["frequency"] == "weekly":
                text += f"  = {fmt(monthly)}/ay ekvivalent\n"
        text += f"\n💡 **Ümumi aylıq: {fmt(total)}**"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yeni əlavə et", callback_data="fixed:add")],
        [InlineKeyboardButton(text="🗑️ Sil", callback_data="fixed:delete_menu")],
    ])
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@router.callback_query(F.data == "fixed:add")
async def fixed_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FixedForm.name)
    await callback.message.answer("📌 **Yeni mütəmadi xərc**\n\nAdı yaz (məs: Kirayə):", parse_mode="Markdown")
    await callback.answer()


@router.message(FixedForm.name)
async def fixed_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(FixedForm.amount)
    await message.answer("💰 Aylıq məbləği daxil et (AZN):")


@router.message(FixedForm.amount)
async def fixed_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0: raise ValueError
    except:
        await message.answer("❌ Düzgün rəqəm daxil et")
        return
    await state.update_data(amount=amount)
    await state.set_state(FixedForm.frequency)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗓️ Aylıq", callback_data="freq:monthly")],
        [InlineKeyboardButton(text="📆 Həftəlik", callback_data="freq:weekly")],
    ])
    await message.answer("📅 **Tezlik** seç:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("freq:"), FixedForm.frequency)
async def fixed_freq(callback: CallbackQuery, state: FSMContext):
    freq = callback.data.split(":")[1]
    await state.update_data(frequency=freq)
    if freq == "monthly":
        await state.set_state(FixedForm.pay_day)
        await callback.message.answer("📅 Ödəniş günü (1-31):")
    else:
        await state.update_data(pay_day=1)
        await save_fixed(callback.message, state, callback.from_user.id)
    await callback.answer()


@router.message(FixedForm.pay_day)
async def fixed_pay_day(message: Message, state: FSMContext):
    try:
        day = int(message.text)
        if day < 1 or day > 31: raise ValueError
    except:
        await message.answer("❌ 1-31 arası")
        return
    await state.update_data(pay_day=day)
    await save_fixed(message, state, message.from_user.id)


async def save_fixed(message, state, user_id):
    data = await state.get_data()
    await add_fixed_expense(
        user_id, data["name"], data["amount"],
        "Digər", data["frequency"], data["pay_day"],
    )
    await state.clear()
    await message.answer(
        f"✅ **Əlavə edildi**\n\n📌 {data['name']}\n💰 {fmt(data['amount'])}",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "fixed:delete_menu")
async def fixed_delete_menu(callback: CallbackQuery):
    items = await get_fixed_expenses(callback.from_user.id)
    if not items:
        await callback.answer("Heç nə yoxdur", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🗑️ {it['name']}", callback_data=f"fixed:del:{it['id']}")]
        for it in items
    ])
    await callback.message.edit_text("Hansını sil?", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("fixed:del:"))
async def fixed_delete(callback: CallbackQuery):
    item_id = int(callback.data.split(":")[-1])
    await delete_fixed_expense(item_id, callback.from_user.id)
    await callback.message.edit_text("✅ Silindi")
    await callback.answer()


@router.message(F.text == "🏦 Borclar")
async def show_debts(message: Message):
    user_id = message.from_user.id
    await ensure_user(user_id)
    items = await get_debts(user_id)

    if not items:
        text = "🏦 **Borclar**\n\nHələ heç bir yoxdur."
    else:
        text = "🏦 **Borclar**\n\n"
        for it in items:
            remaining = it["total"] - it["paid"]
            pct = (it["paid"] / it["total"] * 100) if it["total"] > 0 else 0
            text += f"• **{it['name']}**\n"
            text += f"  Qalıq: {fmt(remaining)} / {fmt(it['total'])} ({pct:.0f}%)\n"
            text += f"  Ödəniş: {fmt(it['payment'])} ({it['frequency']})\n\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yeni borc", callback_data="debt:add")],
        [InlineKeyboardButton(text="💳 Ödəniş et", callback_data="debt:pay_menu")],
        [InlineKeyboardButton(text="🗑️ Sil", callback_data="debt:delete_menu")],
    ])
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@router.callback_query(F.data == "debt:add")
async def debt_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DebtForm.name)
    await callback.message.answer("🏦 **Yeni borc**\n\nAdı yaz (məs: Kredit):", parse_mode="Markdown")
    await callback.answer()


@router.message(DebtForm.name)
async def debt_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(DebtForm.total)
    await message.answer("💰 Ümumi borc (AZN):")


@router.message(DebtForm.total)
async def debt_total(message: Message, state: FSMContext):
    try:
        t = float(message.text.replace(",", "."))
        if t <= 0: raise ValueError
    except:
        await message.answer("❌ Düzgün rəqəm")
        return
    await state.update_data(total=t)
    await state.set_state(DebtForm.payment)
    await message.answer("💳 Ödəniş məbləği (AZN):")


@router.message(DebtForm.payment)
async def debt_payment(message: Message, state: FSMContext):
    try:
        p = float(message.text.replace(",", "."))
        if p <= 0: raise ValueError
    except:
        await message.answer("❌ Düzgün rəqəm")
        return
    await state.update_data(payment=p)
    await state.set_state(DebtForm.frequency)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗓️ Aylıq", callback_data="dfreq:monthly")],
        [InlineKeyboardButton(text="📆 Həftəlik", callback_data="dfreq:weekly")],
    ])
    await message.answer("📅 Tezlik:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("dfreq:"), DebtForm.frequency)
async def debt_freq(callback: CallbackQuery, state: FSMContext):
    freq = callback.data.split(":")[1]
    data = await state.get_data()
    await add_debt(callback.from_user.id, data["name"], data["total"], data["payment"], freq)
    await state.clear()
    await callback.message.edit_text(
        f"✅ **Əlavə edildi**\n\n🏦 {data['name']}\n💰 {fmt(data['total'])}\n💳 {fmt(data['payment'])} / {freq}",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "debt:pay_menu")
async def debt_pay_menu(callback: CallbackQuery):
    items = await get_debts(callback.from_user.id)
    if not items:
        await callback.answer("Heç nə yoxdur", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 {it['name']} ({fmt(it['payment'])})", callback_data=f"debt:pay:{it['id']}")]
        for it in items
    ])
    await callback.message.edit_text("Hansını ödəyirsən?", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("debt:pay:"))
async def debt_pay(callback: CallbackQuery):
    debt_id = int(callback.data.split(":")[-1])
    debt = await pay_debt(debt_id, callback.from_user.id)
    if not debt:
        await callback.answer("Tapılmadı", show_alert=True)
        return
    today = datetime.now().strftime("%Y-%m-%d")
    await add_transaction(
        callback.from_user.id, "expense", debt["payment"],
        "Digər", f"{debt['name']} ödənişi", today,
    )
    await callback.message.edit_text(
        f"✅ **Ödəniş qeyd edildi**\n\n🏦 {debt['name']}\n💳 {fmt(debt['payment'])}\n📊 Qalıq: {fmt(debt['total'] - debt['paid'])}",
        parse_mode="Markdown",
    )
    await callback.answer("Ödəniş qeyd edildi")


@router.callback_query(F.data == "debt:delete_menu")
async def debt_delete_menu(callback: CallbackQuery):
    items = await get_debts(callback.from_user.id)
    if not items:
        await callback.answer("Heç nə yoxdur", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🗑️ {it['name']}", callback_data=f"debt:del:{it['id']}")]
        for it in items
    ])
    await callback.message.edit_text("Hansını sil?", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("debt:del:"))
async def debt_delete(callback: CallbackQuery):
    debt_id = int(callback.data.split(":")[-1])
    await delete_debt(debt_id, callback.from_user.id)
    await callback.message.edit_text("✅ Silindi")
    await callback.answer()


@router.message(F.text == "💳 Kartlar")
async def show_cards(message: Message):
    user_id = message.from_user.id
    await ensure_user(user_id)
    items = await get_cards(user_id)

    if not items:
        text = "💳 **Kartlar**\n\nHələ heç bir yoxdur."
    else:
        text = "💳 **Kartlar**\n\n"
        for it in items:
            text += f"• **{it['bank']}** {it['brand']} ••{it['last4']}\n"
            text += f"  {it['holder']} | {it['expiry']}\n\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yeni kart", callback_data="card:add")],
        [InlineKeyboardButton(text="🗑️ Sil", callback_data="card:delete_menu")],
    ])
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@router.callback_query(F.data == "card:add")
async def card_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CardForm.bank)
    await callback.message.answer("💳 **Yeni kart**\n\nBankın adı:", parse_mode="Markdown")
    await callback.answer()


@router.message(CardForm.bank)
async def card_bank(message: Message, state: FSMContext):
    await state.update_data(bank=message.text)
    await state.set_state(CardForm.brand)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Visa", callback_data="brand:Visa")],
        [InlineKeyboardButton(text="Mastercard", callback_data="brand:Mastercard")],
        [InlineKeyboardButton(text="Digər", callback_data="brand:Digər")],
    ])
    await message.answer("Kart növü:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("brand:"), CardForm.brand)
async def card_brand(callback: CallbackQuery, state: FSMContext):
    brand = callback.data.split(":")[1]
    await state.update_data(brand=brand)
    await state.set_state(CardForm.holder)
    await callback.message.answer("👤 AD SOYAD:")
    await callback.answer()


@router.message(CardForm.holder)
async def card_holder(message: Message, state: FSMContext):
    await state.update_data(holder=message.text.upper())
    await state.set_state(CardForm.last4)
    await message.answer("🔢 Son 4 rəqəm:")


@router.message(CardForm.last4)
async def card_last4(message: Message, state: FSMContext):
    last4 = message.text.strip()
    if len(last4) != 4 or not last4.isdigit():
        await message.answer("❌ 4 rəqəm daxil et")
        return
    await state.update_data(last4=last4)
    await state.set_state(CardForm.expiry)
    await message.answer("📅 Bitmə tarixi (AA/İİ, məs: 12/28):")


@router.message(CardForm.expiry)
async def card_expiry(message: Message, state: FSMContext):
    expiry = message.text.strip()
    if "/" not in expiry or len(expiry) != 5:
        await message.answer("❌ AA/İİ formatı")
        return
    data = await state.get_data()
    await add_card(
        message.from_user.id, data["bank"], data["brand"],
        data["holder"], data["last4"], expiry,
    )
    await state.clear()
    await message.answer(
        f"✅ **Kart əlavə edildi**\n\n💳 {data['bank']} {data['brand']}\n•••• {data['last4']}\n👤 {data['holder']}",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "card:delete_menu")
async def card_delete_menu(callback: CallbackQuery):
    items = await get_cards(callback.from_user.id)
    if not items:
        await callback.answer("Heç nə yoxdur", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🗑️ {it['bank']} ••{it['last4']}", callback_data=f"card:del:{it['id']}")]
        for it in items
    ])
    await callback.message.edit_text("Hansını sil?", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("card:del:"))
async def card_delete(callback: CallbackQuery):
    card_id = int(callback.data.split(":")[-1])
    await delete_card(card_id, callback.from_user.id)
    await callback.message.edit_text("✅ Silindi")
    await callback.answer()


@router.message(F.text == "📋 Tarixçə")
async def show_history(message: Message):
    items = await get_transactions(message.from_user.id, limit=15)
    if not items:
        await message.answer("📋 Hələ heç bir tranzaksiya yoxdur.")
        return
    text = "📋 **Son 15 tranzaksiya**\n\n"
    for t in items:
        emoji = "💰" if t["type"] == "income" else "💸"
        sign = "+" if t["type"] == "income" else "−"
        text += f"{emoji} {sign}{fmt(t['amount'])} · {t['category']}\n"
        text += f"   {t['date']}"
        if t["note"]:
            text += f" · {t['note'][:30]}"
        text += "\n"
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text == "⚙️ Ayarlar")
async def show_settings(message: Message):
    user = await get_user(message.from_user.id)
    text = f"⚙️ **Ayarlar**\n\n"
    text += f"💰 Aylıq gəlir: {fmt(user['monthly_income']) if user['monthly_income'] else 'təyin edilməyib'}\n"
    text += f"📅 Maaş günü: **{user['salary_day']}**\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Aylıq gəliri dəyiş", callback_data="set:income")],
        [InlineKeyboardButton(text="📅 Maaş gününü dəyiş", callback_data="set:salary")],
    ])
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@router.callback_query(F.data == "set:income")
async def set_income_btn(callback: CallbackQuery, state: FSMContext):
    await state.set_state(IncomeForm.amount)
    await callback.message.answer("💰 Aylıq gəliri daxil et (AZN):")
    await callback.answer()


@router.callback_query(F.data == "set:salary")
async def set_salary_btn(callback: CallbackQuery, state: FSMContext):
    await state.set_state(IncomeForm.salary_day)
    await callback.message.answer("📅 Maaş günü (1-31):")
    await callback.answer()


@router.message()
async def fallback(message: Message):
    await message.answer("😅 Bilmədim. Aşağıdakı düymələri istifadə et:", reply_markup=main_menu())


async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    print("🤖 Bot işə düşdü!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())