# main.py
import os
from dotenv import load_dotenv
import telebot
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from random import shuffle
from models import Base, User, Word, UserWord

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env")

# Для Render: DATABASE_URL задаётся автоматически
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    # Render даёт URL вида postgres://user:pass@host:port/db
    DB_URL = DATABASE_URL
else:
    # Локальный запуск
    DB_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)

bot = telebot.TeleBot(BOT_TOKEN)


def init_db():
    """Создаёт таблицы, если их нет."""
    Base.metadata.create_all(engine)


def add_user_and_common_words(user_id, username, first_name, last_name):
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            user = User(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            session.add(user)
            session.commit()

        count = session.query(UserWord).filter(UserWord.user_id == user_id).count()
        if count == 0:
            all_words = session.query(Word).all()
            for word in all_words:
                user_word = UserWord(user_id=user_id, word_id=word.word_id)
                session.add(user_word)
            session.commit()
    finally:
        session.close()


def get_random_word_for_user(user_id):
    session = SessionLocal()
    try:
        result = session.execute(text("""
            SELECT w.russian_word, w.english_word
            FROM user_words uw
            JOIN words w ON uw.word_id = w.word_id
            WHERE uw.user_id = :user_id
            ORDER BY RANDOM()
            LIMIT 1
        """), {"user_id": user_id}).fetchone()

        if not result:
            return None, None, []

        russian_word, correct_answer = result

        wrong = session.execute(text("""
            SELECT english_word
            FROM words
            WHERE english_word != :correct
            ORDER BY RANDOM()
            LIMIT 3
        """), {"correct": correct_answer}).fetchall()

        options = [correct_answer] + [w[0] for w in wrong]
        shuffle(options)
        return russian_word, correct_answer, options
    finally:
        session.close()


def add_user_word(user_id, russian, english):
    session = SessionLocal()
    try:
        word = session.query(Word).filter(
            Word.russian_word.ilike(russian),
            Word.english_word.ilike(english)
        ).first()

        if not word:
            word = Word(russian_word=russian, english_word=english)
            session.add(word)
            session.commit()

        user_word = UserWord(user_id=user_id, word_id=word.word_id)
        session.add(user_word)
        session.commit()
    except IntegrityError:
        session.rollback()
    finally:
        session.close()


def delete_user_word(user_id, russian, english):
    session = SessionLocal()
    try:
        word = session.query(Word).filter(
            Word.russian_word.ilike(russian),
            Word.english_word.ilike(english)
        ).first()
        if word:
            session.query(UserWord).filter(
                UserWord.user_id == user_id,
                UserWord.word_id == word.word_id
            ).delete()
            session.commit()
    finally:
        session.close()


def find_translation(word):
    session = SessionLocal()
    try:
        result = session.query(Word).filter(Word.russian_word.ilike(word)).first()
        if result:
            return result.russian_word, result.english_word
        result = session.query(Word).filter(Word.english_word.ilike(word)).first()
        if result:
            return result.russian_word, result.english_word
        return None
    finally:
        session.close()


def count_user_words(user_id):
    session = SessionLocal()
    try:
        return session.query(UserWord).filter(UserWord.user_id == user_id).count()
    finally:
        session.close()


# === ОБРАБОТЧИКИ TELEBOT ===
@bot.message_handler(commands=["start"])
def start(message):
    add_user_and_common_words(
        message.from_user.id,
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
    result = get_random_word_for_user(message.from_user.id)
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
    session = SessionLocal()
    try:
        words = session.execute(text("""
            SELECT w.russian_word, w.english_word
            FROM user_words uw
            JOIN words w ON uw.word_id = w.word_id
            WHERE uw.user_id = :user_id
        """), {"user_id": message.from_user.id}).fetchall()
    finally:
        session.close()

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

    correct = bot.get_state(user_id, message.chat.id)
    if correct and text not in ["Дальше ▶", "Добавить слово ➕", "Удалить слово ❌"]:
        if text.lower() == correct.lower():
            bot.send_message(message.chat.id, "❤️ Верно!")
            bot.delete_state(user_id, message.chat.id)
        else:
            bot.send_message(message.chat.id, "❌ Неверно. Попробуй ещё раз.")
        return

    if text in ["Дальше ▶", "Добавить слово ➕", "Удалить слово ❌"]:
        return

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
    init_db()
    print("🚀 Бот запущен...")
    bot.polling(none_stop=True)