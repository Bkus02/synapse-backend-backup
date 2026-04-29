from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Numeric, Text
from sqlmodel import Field, SQLModel


class HabitMatrix(SQLModel, table=True):
    __tablename__ = "habit_matrix"

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(max_length=8, foreign_key="users.id")
    trigger_event: str = Field(sa_column=Column(Text, nullable=False))
    target_event: str = Field(sa_column=Column(Text, nullable=False))
    context: str = Field(sa_column=Column(Text, nullable=False))
    probability: float = Field(sa_column=Column(Numeric(6, 5), nullable=False))
    last_updated: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

