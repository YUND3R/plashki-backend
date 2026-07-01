from sqlalchemy import Select, asc, desc, func, or_


def apply_sort(stmt: Select, column, sort_order: str) -> Select:
    ordering = asc(column) if sort_order == "asc" else desc(column)
    return stmt.order_by(ordering)


def apply_pagination(stmt: Select, *, limit: int | None, offset: int) -> Select:
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return stmt


def ilike_pattern(value: str) -> str:
    return f"%{value.strip()}%"


def jsonb_array_length(column):
    return func.coalesce(func.jsonb_array_length(column), 0)
