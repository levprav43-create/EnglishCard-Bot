import os
from dotenv import load_dotenv
import telebot
import psycopg2
from random import choice, shuffle

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env")

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 5432)),
}

bot = telebot.TeleBot(BOT_TOKEN)


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def add_user_and_common_words(user_id, username, first_name, last_name):
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        INSERT INTO users (user_id, username, first_name, last_name)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id, username, first_name, last_name),
    )
    
    cur.execute("SELECT COUNT(*) FROM user_words WHERE user_id = %s", (user_id,))
    count = cur.fetchone()[0]
    
    if count == 0:
        cur.execute("SELECT word_id FROM words")
        common_word_ids = [row[0] for row in cur.fetchall()]
        for word_id in common_word_ids:
            cur.execute(
                "INSERT INTO user_words (user_id, word_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (user_id, word_id)
            )
        conn.commit()
    
    cur.close()
    conn.close()


def count_user_words(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM user_words WHERE user_id = %s", (user_id,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


def add_user_word(user_id, russian, english):
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        INSERT INTO words (russian_word, english_word)
        VALUES (%s, %s)
        ON CONFLICT (russian_word, english_word) DO NOTHING
        RETURNING word_id
        """,
        (russian, english)
    )
    result = cur.fetchone()
    if result:
        word_id = result[0]
    else:
        cur.execute(
            "SELECT word_id FROM words WHERE LOWER(russian_word) = LOWER(%s) AND LOWER(english_word) = LOWER(%s)",
            (russian, english)
        )
        result = cur.fetchone()
        if result:
            word_id = result[0]
        else:
            cur.execute(
                "INSERT INTO words (russian_word, english_word) VALUES (%s, %s) RETURNING word_id",
                (russian, english)
            )
            word_id = cur.fetchone()[0]
    
    cur.execute(
        "INSERT INTO user_words (user_id, word_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (user_id, word_id)
    )
    conn.commit()
    cur.close()
    conn.close()


def delete_user_word(user_id, russian, english):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM user_words
        WHERE user_id = %s AND word_id = (
            SELECT word_id FROM words WHERE LOWER(russian_word) = LOWER(%s) AND LOWER(english_word) = LOWER(%s)
        )
    """, (user_id, russian, english))
    conn.commit()
    cur.close()
    conn.close()


def get_random_word_for_user(user_id):
    """Возвращает случайное слово пользователя и 4 варианта ответа (1 правильный + 3 случайных)."""
    conn = get_connection()
    cur = conn.cursor()

    # Получаем одно случайное слово пользователя
    cur.execute("""
        SELECT w.russian_word, w.english_word
        FROM user_words uw
        JOIN words w ON uw.word_id = w.word_id
        WHERE uw.user_id = %s
        ORDER BY RANDOM()
        LIMIT 1
    """, (user_id,))
    result = cur.fetchone()
    if not result:
        cur.close()
        conn.close()
        return None, None, []

    russian_word, correct_answer = result

    # Получаем 3 случайных неправильных ответа напрямую из БД
    cur.execute("""
        SELECT english_word
        FROM words
        WHERE english_word != %s
        ORDER BY RANDOM()
        LIMIT 3
    """, (correct_answer,))
    wrong_options = [row[0] for row in cur.fetchall()]

    options = [correct_answer] + wrong_options
    shuffle(options)

    cur.close()
    conn.close()
    return russian_word, correct_answer, options


def find_translation(word):
    """Ищет перевод НЕЗАВИСИМО от регистра."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Ищем как русское слово
    cur.execute(
        "SELECT russian_word, english_word FROM words WHERE LOWER(russian_word) = LOWER(%s)",
        (word.strip(),)
    )
    result = cur.fetchone()
    
    if result:
        cur.close()
        conn.close()
        return result
    
    # Ищем как английское
    cur.execute(
        "SELECT russian_word, english_word FROM words WHERE LOWER(english_word) = LOWER(%s)",
        (word.strip(),)
    )
    result = cur.fetchone()
    
    cur.close()
    conn.close()
    return result


@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    add_user_and_common_words(
        user_id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name
    )
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Дальше ▶", "Добавить слово ➕", "Удалить слово ❌")
    bot.send_message(
        message.chat.id,
        f"Привет, {message.from_user.first_name}! 👋\n"
        "Я помогу тебе учить английские слова.\n"
        "Нажми 'Дальше ▶', чтобы начать тест.\n"
        "Или просто напиши любое слово для перевода!",
        reply_markup=markup,
    )


@bot.message_handler(func=lambda m: m.text == "Дальше ▶")
def next_word(message):
    user_id = message.from_user.id
    result = get_random_word_for_user(user_id)
    if not result[0]:
        bot.send_message(message.chat.id, "У тебя пока нет слов.")
        return

    russian_word, correct_answer, options = result
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [telebot.types.KeyboardButton(opt) for opt in options]
    markup.add(*buttons)
    markup.add("Дальше ▶")
    bot.send_message(
        message.chat.id,
        f"Что значит: {russian_word}?",
        reply_markup=markup
    )
    bot.set_state(message.from_user.id, correct_answer, message.chat.id)


@bot.message_handler(func=lambda m: m.text == "Добавить слово ➕")
def add_prompt(message):
    bot.send_message(
        message.chat.id,
        "Отправь в формате:\nрусское | английский\nПример: Машина | Car"
    )


@bot.message_handler(func=lambda m: "|" in m.text and m.text.count("|") == 1)
def add_word(message):
    try:
        parts = message.text.split("|")
        ru = parts[0].strip()
        en = parts[1].strip()
        if not ru or not en:
            raise ValueError("Пустые поля")

        add_user_word(message.from_user.id, ru, en)
        total = count_user_words(message.from_user.id)
        bot.send_message(
            message.chat.id,
            f"✅ '{ru}' → '{en}' добавлено!\nТеперь у тебя {total} слов(а)."
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")


@bot.message_handler(func=lambda m: m.text == "Удалить слово ❌")
def del_prompt(message):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT w.russian_word, w.english_word
        FROM user_words uw
        JOIN words w ON uw.word_id = w.word_id
        WHERE uw.user_id = %s
    """, (message.from_user.id,))
    words = cur.fetchall()
    cur.close()
    conn.close()
    
    if not words:
        bot.send_message(message.chat.id, "Нечего удалять.")
        return
        
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    for ru, en in words:
        markup.add(f"Удалить: {ru} → {en}")
    bot.send_message(message.chat.id, "Выбери слово:", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text.startswith("Удалить: "))
def delete_word(message):
    text = message.text.replace("Удалить: ", "")
    try:
        ru, en = text.split(" → ", 1)
        delete_user_word(message.from_user.id, ru, en)
        bot.send_message(message.chat.id, "✅ Слово удалено.")
    except Exception:
        bot.send_message(message.chat.id, "❌ Ошибка.")


@bot.message_handler(func=lambda m: True)
def handle_message(message):
    text = message.text.strip()
    user_id = message.from_user.id

    # Если в режиме теста — проверяем ответ
    correct = bot.get_state(user_id, message.chat.id)
    if correct and text not in ["Дальше ▶", "Добавить слово ➕", "Удалить слово ❌"]:
        if text.lower() == correct.lower():
            bot.send_message(message.chat.id, "❤️ Верно!")
            bot.delete_state(user_id, message.chat.id)
        else:
            bot.send_message(message.chat.id, "❌ Неверно. Попробуй ещё раз.")
        return

    # Игнорируем кнопки
    if text in ["Дальше ▶", "Добавить слово ➕", "Удалить слово ❌"]:
        return

    # Перевод (регистронезависимый)
    translation = find_translation(text)
    if translation:
        ru, en = translation
        if text.lower() == ru.lower():
            bot.send_message(message.chat.id, f"🇬🇧 {en}")
        else:
            bot.send_message(message.chat.id, f"🇷🇺 {ru}")
    else:
        bot.send_message(message.chat.id, "🔍 Слово не найдено в словаре.")


if __name__ == "__main__":
    print("🚀 Бот запущен...")
    bot.polling(none_stop=True)