from __future__ import annotations

import hashlib
import hmac
import os

from .storage import Storage


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, salt, digest = password_hash.split("$", 2)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    candidate = hash_password(password, salt).split("$", 2)[2]
    return hmac.compare_digest(candidate, digest)


class AuthService:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def register(self, username: str, password: str, interests: str = "") -> tuple[bool, str]:
        username = username.strip()
        if len(username) < 2 or len(password) < 4:
            return False, "用户名至少 2 位，密码至少 4 位"
        if self.storage.get_user_by_username(username):
            return False, "用户名已存在"
        self.storage.create_user(username, hash_password(password), interests)
        return True, "注册成功"

    def login(self, username: str, password: str) -> tuple[bool, str, str | None]:
        user = self.storage.get_user_by_username(username.strip())
        if not user or not verify_password(password, user["password_hash"]):
            return False, "用户名或密码错误", None
        token = self.storage.create_session(int(user["id"]))
        return True, "登录成功", token

