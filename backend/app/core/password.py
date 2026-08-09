import bcrypt


def validate_password_strength(plain: str) -> str | None:
    if len(plain) < 8:
        return "Пароль должен содержать минимум 8 символов."
    if len(plain) > 128:
        return "Пароль не должен быть длиннее 128 символов."
    return None


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain.encode("utf-8"),
            hashed.encode("utf-8"),
        )
    except ValueError:
        return False
