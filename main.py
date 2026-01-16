import os
import telebot
import sqlite3
from telebot import types
from flask import Flask
from threading import Thread
import datetime

# ================== НАСТРОЙКИ ==================
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("❌ TOKEN не найден. Добавь его в Environment Variables")

CHANNEL_USERNAME = "@rzdpodarkov"
BOT_USERNAME = "rzdpodarkov_bot"
MAX_REFS_PER_USER = 1000
MAX_DAILY_REFS = 50
ADMINS = [5762539317]

bot = telebot.TeleBot(TOKEN)

# ================== KEEP-ALIVE ==================
app = Flask('')
@app.route('/')
def home():
    return "Bot is alive!"

Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

# ================== БАЗА ДАННЫХ ==================
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    ref_by INTEGER,
    subscribed INTEGER DEFAULT 0,
    refs INTEGER DEFAULT 0,
    username TEXT,
    daily_refs INTEGER DEFAULT 0,
    blocked INTEGER DEFAULT 0,
    ref_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_ref_by ON users(ref_by)")
conn.commit()

# ================== ЛОГИ ==================
logs = []
def add_log(action):
    logs.append(action)
    if len(logs) > 20: logs.pop(0)

# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================
def is_admin(user_id): return user_id in ADMINS

def is_subscribed(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member','administrator','creator']
    except:
        return False

def update_referrals(user_id):
    if not is_subscribed(user_id):
        return
    cursor.execute("SELECT blocked, ref_by FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    if not result: return
    blocked, ref_by = result
    if blocked or not ref_by: return
    cursor.execute("SELECT refs, daily_refs FROM users WHERE user_id=?", (ref_by,))
    current_refs, daily_refs = cursor.fetchone()
    if current_refs >= MAX_REFS_PER_USER or daily_refs >= MAX_DAILY_REFS: return
    cursor.execute("UPDATE users SET refs=refs+1, daily_refs=daily_refs+1, ref_time=CURRENT_TIMESTAMP WHERE user_id=?", (ref_by,))
    conn.commit()
    try:
        cursor.execute("SELECT username FROM users WHERE user_id=?", (user_id,))
        nick = cursor.fetchone()[0] or str(user_id)
        bot.send_message(ref_by,f"🎉 Ваш реферал @{nick} подписался! Теперь у вас {current_refs+1} рефералов.")
    except: pass

def get_level(refs):
    if refs >=16: return "🏅 Эксперт"
    elif refs>=6: return "⭐ Продвинутый"
    elif refs>=1: return "🔰 Новичок"
    else: return "🛡 Новичок"

# ================== ТЕКСТОВЫЙ ПРОГРЕСС-БАР ==================
def generate_progress_text(user_id):
    cursor.execute("SELECT refs FROM users WHERE user_id=?", (user_id,))
    refs = cursor.fetchone()[0]
    if refs >= 16:
        level = "Эксперт"
        max_refs = 20
    elif refs >= 6:
        level = "Продвинутый"
        max_refs = 16
    elif refs >= 1:
        level = "Новичок"
        max_refs = 6
    else:
        level = "Новичок"
        max_refs = 1
    progress_ratio = refs / max_refs
    total_blocks = 20
    filled_blocks = int(total_blocks * progress_ratio)
    empty_blocks = total_blocks - filled_blocks
    bar = "🟩" * filled_blocks + "⬜" * empty_blocks
    text = f"🏅 Уровень: {level}\n"
    text += f"Рефералы: {refs}/{max_refs}\n"
    text += f"Прогресс: {bar} ({int(progress_ratio*100)}%)"
    return text

# ================== ЛИДЕРБОРД ==================
PERIOD_NAMES = {
    "day": "сегодня",
    "week": "за неделю",
    "month": "за месяц",
    "all": "за всё время"
}

def get_referrals_by_period(period):
    now = datetime.datetime.now()
    if period=="day": since = now - datetime.timedelta(days=1)
    elif period=="week": since = now - datetime.timedelta(weeks=1)
    elif period=="month": since = now - datetime.timedelta(days=30)
    else: return cursor.execute("SELECT username, refs FROM users ORDER BY refs DESC LIMIT 10").fetchall()
    cursor.execute("SELECT username, refs FROM users WHERE ref_time>=? ORDER BY refs DESC LIMIT 10",(since,))
    return cursor.fetchall()

def leaderboard_menu(chat_id, admin=False):
    markup=types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📅 Сегодня", callback_data="leaderboard_day" if not admin else "admin_top_day"),
        types.InlineKeyboardButton("📅 Неделя", callback_data="leaderboard_week" if not admin else "admin_top_week"),
        types.InlineKeyboardButton("📅 Месяц", callback_data="leaderboard_month" if not admin else "admin_top_month"),
        types.InlineKeyboardButton("🏆 Общий", callback_data="leaderboard_all" if not admin else "admin_top_all")
    )
    bot.send_message(chat_id,"Выберите период топ-лидерборда:",reply_markup=markup)

# ================== /start ==================
@bot.message_handler(commands=['start'])
def start(message):
    user_id=message.from_user.id
    username=message.from_user.username
    cursor.execute("SELECT blocked FROM users WHERE user_id=?",(user_id,))
    blocked=cursor.fetchone()
    if blocked and blocked[0]: bot.send_message(user_id,"❌ Вы заблокированы"); return
    args=message.text.split(); ref_by=None
    if len(args)>1:
        try: candidate=int(args[1]); ref_by=candidate if candidate!=user_id else None
        except: pass
    cursor.execute("SELECT * FROM users WHERE user_id=?",(user_id,))
    if not cursor.fetchone(): cursor.execute("INSERT INTO users(user_id,ref_by,username) VALUES(?,?,?)",(user_id,ref_by,username)); conn.commit()
    else: cursor.execute("UPDATE users SET username=? WHERE user_id=?",(username,user_id)); conn.commit()

    markup=types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📢 Подписаться на канал",url=f"https://t.me/{CHANNEL_USERNAME[1:]}"),
        types.InlineKeyboardButton("✅ Проверить подписку",callback_data="check_sub"),
        types.InlineKeyboardButton("📋 Мои рефералы",callback_data="my_refs"),
        types.InlineKeyboardButton("🏆 Топ-лидерборд",callback_data="leaderboard"),
        types.InlineKeyboardButton("📊 Мой прогресс",callback_data="show_progress")
    )
    if is_admin(user_id):
        markup.add(types.InlineKeyboardButton("⚙ Админ-панель", callback_data="admin"))

    ref_link=f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.send_message(user_id,f"👋 Привет, @{username}!\n\n🎁 Подпишись на канал и нажми кнопку ниже 👇\n\n🔗 Ваша реферальная ссылка:\n{ref_link}",reply_markup=markup)

# ================== ОБРАБОТКА КНОПОК ==================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id=call.from_user.id
    bot.answer_callback_query(call.id, text="✅ Выполнено")  # кнопки больше не виснут

    if call.data=="show_progress":
        cursor.execute("SELECT blocked FROM users WHERE user_id=?",(user_id,))
        if cursor.fetchone()[0]: bot.send_message(user_id,"❌ Вы заблокированы"); return
        progress_text = generate_progress_text(user_id)
        bot.send_message(user_id, progress_text)

    elif call.data=="check_sub":
        sub=is_subscribed(user_id)
        bot.answer_callback_query(call.id,"✅ Подписка подтверждена" if sub else "❌ Вы не подписаны",show_alert=True)
        if sub: update_referrals(user_id)

    elif call.data=="my_refs":
        cursor.execute("SELECT username FROM users WHERE ref_by=?",(user_id,))
        refs=cursor.fetchall()
        text="📋 Ваши рефералы:\n"+("\n".join([f"@{r[0]}" if r[0] else f"User_{i+1}" for i,r in enumerate(refs)]) if refs else "Пока нет")
        bot.send_message(user_id,text)

    elif call.data=="leaderboard":
        leaderboard_menu(user_id)

    elif call.data.startswith("leaderboard") or call.data.startswith("admin_top"):
        period = call.data.split("_")[-1]
        rows=get_referrals_by_period(period)
        period_name = PERIOD_NAMES.get(period, period)
        text=f"🏆 Топ пользователей {period_name}:\n"
        for i,r in enumerate(rows,1):
            nick = r[0] if r[0] else f"User_{i}"
            text+=f"{i}. @{nick} — {r[1]} рефералов\n"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id)

    elif call.data=="admin":
        admin_main_menu(user_id)

# ================== АДМИН-ПАНЕЛЬ ==================
def admin_main_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Статистика пользователей", callback_data="admin_stats"),
        types.InlineKeyboardButton("🏆 Топ-лидерборд", callback_data="admin_leaderboard"),
        types.InlineKeyboardButton("📢 Массовая рассылка", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("🚫 Блокировка/Разблокировка", callback_data="admin_block_user"),
        types.InlineKeyboardButton("⚙ Управление пользователем", callback_data="admin_manage_user"),
        types.InlineKeyboardButton("🗑 Сброс статистики", callback_data="admin_reset"),
        types.InlineKeyboardButton("📜 Логи действий", callback_data="admin_logs")
    )
    bot.send_message(chat_id,"⚙️ Панель администратора:",reply_markup=markup)

@bot.message_handler(commands=['admin'])
def open_admin_panel(message):
    if not is_admin(message.from_user.id): bot.reply_to(message,"❌ Нет доступа"); return
    admin_main_menu(message.chat.id)

# ================== ЗАПУСК БОТА ==================
bot.infinity_polling()
