# models.py
from sqlalchemy import Column, BigInteger, String, Integer, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(255))
    first_name = Column(String(255))
    last_name = Column(String(255))
    created_at = Column(DateTime, default=func.now())

class Word(Base):
    __tablename__ = 'words'
    word_id = Column(Integer, primary_key=True, autoincrement=True)
    russian_word = Column(String(255), nullable=False)
    english_word = Column(String(255), nullable=False)
    __table_args__ = (UniqueConstraint('russian_word', 'english_word', name='uq_words'),)

class UserWord(Base):
    __tablename__ = 'user_words'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id', ondelete='CASCADE'))
    word_id = Column(Integer, ForeignKey('words.word_id', ondelete='CASCADE'))
    added_at = Column(DateTime, default=func.now())
    __table_args__ = (UniqueConstraint('user_id', 'word_id', name='uq_user_word'),)