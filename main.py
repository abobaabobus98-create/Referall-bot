import telebot
import sqlite3
import os
from telebot import types
import threading
import time

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

CHANNEL_USERNAME = "@rzdpodarkov"
CHANNEL_URL = "https://t.me/rzdpodarkov"
BOT_USERNAME = "rzdpodarkov_bot"  # без @
MAX_REFS_PER_USER = 200  # макс. рефералов

# ===== БАЗА ДАННЫХ =====
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    ref_by INTEGER,
    subscribed INTEGER DEFAULT 0,
    refs INTEGER DEFAULT 0,
    username TEXT
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

# ===== ОБНОВЛЕНИЕ РЕФЕРАЛОВ =====
def update_referrals(user_id):
    cursor.execute("SELECT ref_by FROM users WHERE user_id=?", (user_id,))
    ref_by = cursor.fetchone()[0]
    if not ref_by:
        return

    cursor.execute("SELECT refs FROM users WHERE user_id=?", (ref_by,))
    current_refs = cursor.fetchone()[0]

    if current_refs < MAX_REFS_PER_USER:
        cursor.execute(
            "UPDATE users SET refs = refs + 1 WHERE user_id=?",
            (ref_by,)
        )
        conn.commit()

        # уведомляем пригласившего
        try:
            cursor.execute("SELECT username FROM users WHERE user_id=?", (user_id,))
            nick = cursor.fetchone()[0] or str(user_id)
            bot.send_message(
                ref_by,
                f"🎉 Ваш реферал @{nick} подписался! Теперь у вас {current_refs + 1} рефералов."
            )
        except:
            pass

# ===== START =====
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    args = message.text.split()
    ref_by = None

    if len(args) > 1:
        try:
            candidate = int(args[1])
            if candidate != user_id:
                ref_by = candidate
        except:
            pass

    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, ref_by, username) VALUES (?, ?, ?)",
            (user_id, ref_by, username)
        )
        conn.commit()
    else:
        # обновляем username
        cursor.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
        conn.commit()

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📢 Подписаться на канал", url=CHANNEL_URL),
        types.InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub"),
        types.InlineKeyboardButton("📋 Мои рефералы", callback_data="my_refs"),
        types.InlineKeyboardButton("🏆 Топ рефералов", callback_data="leaderboard")
    )

    ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"

    bot.send_message(
        message.chat.id,
        f"👋 Привет, @{username}!\n\n"
        "🎁 Подпишись на канал и нажми кнопку ниже 👇\n\n"
        f"🔗 Твоя реферальная ссылка:\n{ref_link}",
        reply_markup=markup
    )

# ===== ПРОВЕРКА ПОДПИСКИ =====
@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_subscription(call):
    user_id = call.from_user.id

    if not is_subscribed(user_id):
        bot.answer_callback_query(call.id, "❌ Ты не подписан", show_alert=True)
        return

    cursor.execute("SELECT subscribed FROM users WHERE user_id=?", (user_id,))
    subscribed = cursor.fetchone()[0]

    if subscribed == 1:
        bot.answer_callback_query(call.id, "✅ Подписка уже засчитана", show_alert=True)
        return

    cursor.execute("UPDATE users SET subscribed=1 WHERE user_id=?", (user_id,))
    conn.commit()
    update_referrals(user_id)

    bot.edit_message_text(
        "🎉 Подписка подтверждена!\n✅ Реферал засчитан!\n📊 Можете посмотреть своих рефералов кнопкой ниже.",
        call.message.chat.id,
        call.message.message_id
    )

# ===== МОИ РЕФЕРАЛЫ =====
@bot.callback_query_handler(func=lambda call: call.data == "my_refs")
def my_refs(call):
    user_id = call.from_user.id
    cursor.execute("SELECT user_id, username, subscribed FROM users WHERE ref_by=?", (user_id,))
    refs = cursor.fetchall()

    if not refs:
        text = "😔 У вас пока нет рефералов."
    else:
        text = "📋 Ваши рефералы:\n"
        for r in refs:
            nick = r[1] if r[1] else str(r[0])
            status = "✅ Подписан" if r[2] else "❌ Не подписан"
            text += f"- @{nick} — {status}\n"

    bot.answer_callback_query(call.id)
    bot.send_message(user_id, text)

# ===== ТОП ЛИДЕРОВ =====
@bot.callback_query_handler(func=lambda call: call.data == "leaderboard")
def leaderboard(call):
    cursor.execute("SELECT user_id, refs, username FROM users ORDER BY refs DESC LIMIT 10")
    rows = cursor.fetchall()

    if not rows:
        text = "😔 Нет лидеров пока."
    else:
        text = "🏆 Топ рефералов:\n\n"
        for i, r in enumerate(rows, 1):
            nick = r[2] if r[2] else str(r[0])
            text += f"{i}. @{nick} — {r[1]} 👥\n"

    bot.answer_callback_query(call.id)
    bot.send_message(call.from_user.id, text)

# ===== АВТОПРОВЕРКА ОТСУТСТВИЯ ПОДПИСКИ =====
def remove_unsubscribed():
    cursor.execute("SELECT user_id, ref_by, subscribed FROM users")
    users = cursor.fetchall()
    for u in users:
        user_id, ref_by, subscribed = u
        if subscribed == 1 and not is_subscribed(user_id):
            cursor.execute("UPDATE users SET subscribed=0 WHERE user_id=?", (user_id,))
            if ref_by:
                cursor.execute(
                    "UPDATE users SET refs = refs - 1 WHERE user_id=? AND refs>0",
                    (ref_by,)
                )
                # уведомляем пригласившего
                try:
                    cursor.execute("SELECT username FROM users WHERE user_id=?", (user_id,))
                    nick = cursor.fetchone()[0] or str(user_id)
                    bot.send_message(
                        ref_by,
                        f"⚠️ Ваш реферал @{nick} отписался. Теперь у вас меньше рефералов."
                    )
                except:
                    pass
    conn.commit()

def auto_check():
    while True:
        remove_unsubscribed()
        time.sleep(3600)

threading.Thread(target=auto_check, daemon=True).start()
bot.infinity_polling()
