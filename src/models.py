from __future__ import annotations

from sqlalchemy import (
    Boolean,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False)  # "admin" | "analyst"
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    access_version = Column(Integer, nullable=False, default=0)
    
    category_access = relationship("UserCategoryAccess", back_populates="user", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(512), unique=True, nullable=False, index=True)  # keep long; categories strings can be long
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user_access = relationship("UserCategoryAccess", back_populates="category", cascade="all, delete-orphan")


class UserCategoryAccess(Base):
    __tablename__ = "user_category_access"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="category_access")
    category = relationship("Category", back_populates="user_access")

    __table_args__ = (
        UniqueConstraint("user_id", "category_id", name="uq_user_category"),
    )


class Conversation(Base):
    """
    A conversation groups messages (like a chat session). We keep it generic:
    - who (user_id)
    - optional title
    - timestamps
    """
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(512), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MessageTrace(Base):
    """
    One user query + one assistant response (traceable).
    Store everything needed to reproduce / audit.
    """
    __tablename__ = "message_traces"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    user_query = Column(Text, nullable=False)

    # What we fed the LLM (prompt template, system instructions, etc.)
    prompt_payload = Column(JSONB, nullable=True)

    # What data we used (aggregates, sampled reviews, filters, category constraints)
    retrieval_payload = Column(JSONB, nullable=True)

    # Assistant output (structured + raw)
    response_payload = Column(JSONB, nullable=True)

    # Plot specs (e.g., plotly JSON, or params used to regenerate)
    plot_payload = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReviewSentimentCache(Base):
    __tablename__ = "review_sentiment_cache"

    id = Column(BigInteger, primary_key=True)
    # sha256 hash of normalized review text
    text_hash = Column(String(64), unique=True, nullable=False, index=True)

    model = Column(String(128), nullable=False)

    sentiment = Column(String(16), nullable=False)  # positive|negative|neutral
    reasons = Column(JSONB, nullable=False)         # list[str]

    latency_ms = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)