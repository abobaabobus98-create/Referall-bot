import telebot
import sqlite3
import os
from telebot import types

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

CHANNEL_USERNAME = "@rzdpodarkov"
CHANNEL_URL = "https://t.me/rzdpodarkov"
BOT_USERNAME = "ТВОЙ_БОТ_USERNAME"  # без @

# ===== БАЗА ДАННЫХ =====
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    ref_by INTEGER,
    subscribed INTEGER DEFAULT 0,
    refs INTEGER DEFAULT 0
)
""")
conn.commit()

# ===== ПРОВЕРКА ПОДПИСКИ =====
def is_subscribed(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

# ===== START =====
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    args = message.text.split()
    ref_by = None

    if len(args) > 1:
        try:
            ref_by = int(args[1])
            if ref_by == user_id:
                ref_by = None
        except:
            ref_by = None

    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, ref_by) VALUES (?, ?)",
            (user_id, ref_by)
        )
        conn.commit()

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL),
        types.InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")
    )

    ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"

    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать!\n\n"
        "🎁 Чтобы участвовать, подпишись на канал:\n"
        f"{CHANNEL_URL}\n\n"
        "После подписки нажми кнопку ниже 👇\n\n"
        f"🔗 Твоя реферальная ссылка:\n{ref_link}",
        reply_markup=markup
    )

# ===== ПРОВЕРКА ПОДПИСКИ (КНОПКА) =====
@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_subscription(call):
    user_id = call.from_user.id

    if not is_subscribed(user_id):
        bot.answer_callback_query(
            call.id,
            "❌ Ты ещё не подписан на канал",
            show_alert=True
        )
        return

    cursor.execute(
        "SELECT subscribed, ref_by FROM users WHERE user_id=?",
        (user_id,)
    )
    user = cursor.fetchone()

    if user[0] == 1:
        bot.answer_callback_query(
            call.id,
            "✅ Подписка уже засчитана",
            show_alert=True
        )
        return

    # Засчитываем подписку
    cursor.execute(
        "UPDATE users SET subscribed=1 WHERE user_id=?",
        (user_id,)
    )

    # Начисляем рефералу
    if user[1]:
        cursor.execute(
            "UPDATE users SET refs = refs + 1 WHERE user_id=?",
            (user[1],)
        )

    conn.commit()

    bot.edit_message_text(
        "🎉 Подписка подтверждена!\n\n"
        "✅ Реферал засчитан.\n"
        "📊 Посмотри /top",
        call.message.chat.id,
        call.message.message_id
    )

# ===== ТОП =====
@bot.message_handler(commands=['top'])
def top(message):
    cursor.execute(
        "SELECT user_id, refs FROM users ORDER BY refs DESC LIMIT 10"
    )
    rows = cursor.fetchall()

    text = "🏆 ТОП рефералов:\n\n"
    for i, row in enumerate(rows, 1):
        text += f"{i}. ID {row[0]} — {row[1]} 👥\n"

    bot.send_message(message.chat.id, text)

# ===== RUN =====
bot.infinity_polling()
