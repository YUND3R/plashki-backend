from datetime import datetime, timedelta, timezone

# Платные тарифы: продлевают subscription_until на 24 ч; FREE — без срока (см. UserProfile.is_subscription_active).
SUBSCRIPTION_24H = timedelta(hours=24)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_subscription_until_24h(
    *,
    now: datetime | None = None,
    current_until: datetime | None = None,
    extend_from_end_if_active: bool = True,
) -> datetime:
    """
    Время окончания подписки на 24 часа.
    - Нет активной подписки: от `now` + 24 ч.
    - Активная (current_until > now) и extend_from_end_if_active: от старого конца + 24 ч.
    - Активная и extend_from_end_if_active=False: от now + 24 ч (замена окна).
    """
    start = _as_utc(now or utcnow())
    if (
        extend_from_end_if_active
        and current_until is not None
        and _as_utc(current_until) > start
    ):
        return _as_utc(current_until) + SUBSCRIPTION_24H
    return start + SUBSCRIPTION_24H
