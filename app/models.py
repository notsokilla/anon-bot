from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, LargeBinary
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    is_premium = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    sent_messages = relationship("AnonymousMessage", foreign_keys="AnonymousMessage.sender_id", back_populates="sender")
    received_messages = relationship("AnonymousMessage", foreign_keys="AnonymousMessage.recipient_id", back_populates="recipient")

class AnonymousMessage(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey('users.id'), nullable=True) # Null если от неизвестного (через ссылку)
    recipient_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    content_text = Column(Text, nullable=True)
    content_file_id = Column(String, nullable=True) # ID фото/видео/стикера
    content_type = Column(String, default='text') # text, photo, video, voice, video_note, sticker
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_messages")
    recipient = relationship("User", foreign_keys=[recipient_id], back_populates="received_messages")

class PendingMessage(Base):
    """Сообщения для пользователей, которых еще нет в боте"""
    __tablename__ = 'pending_messages'
    
    id = Column(Integer, primary_key=True)
    recipient_tg_id = Column(Integer, nullable=False, index=True)  # Убрали ForeignKey, т.к. это TG ID, а не PK users
    sender_tg_id = Column(Integer, nullable=True) # Кто отправил (если известен)
    content_text = Column(Text, nullable=True)
    content_file_id = Column(String, nullable=True)
    content_type = Column(String, default='text')
    created_at = Column(DateTime, default=datetime.utcnow)

class AdminSession(Base):
    __tablename__ = 'admin_sessions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    token = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

class BroadcastTemplate(Base):
    """Шаблоны для рассылок"""
    __tablename__ = 'broadcast_templates'
    
    id = Column(Integer, primary_key=True)
    text = Column(Text, nullable=False)
    image_id = Column(String, nullable=True) # file_id изображения
    use_in_auto = Column(Boolean, default=False) # Использовать в авто-рассылке
    has_button = Column(Boolean, default=False) # Показывать кнопку
    button_text = Column(String, default="Узнать") # Текст кнопки
    button_url = Column(String, nullable=True) # URL кнопки
    created_at = Column(DateTime, default=datetime.utcnow)