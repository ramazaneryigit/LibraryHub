"""Request models for auth."""

from __future__ import annotations

from pydantic import BaseModel, Field


__all__ = ["LoginRequest", "RegisterRequest", "VerifyEmailRequest", "ResendVerificationRequest"]


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=10, max_length=200)
    display_name: str = Field(min_length=2, max_length=300)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResendVerificationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
