-- create_tables.sql — создание структуры базы данных

CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS words (
    word_id SERIAL PRIMARY KEY,
    russian_word VARCHAR(255) NOT NULL,
    english_word VARCHAR(255) NOT NULL,
    UNIQUE(russian_word, english_word)
);

CREATE TABLE IF NOT EXISTS user_words (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    word_id INT REFERENCES words(word_id) ON DELETE CASCADE,
    added_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, word_id)
);