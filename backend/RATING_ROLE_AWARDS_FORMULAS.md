# Рейтинг: лучший игрок по каждой роли

Логика для `GET /ratings/{rating_id}/table`.  
Номинации **раздельные** — мафия, дон, мирный и шериф **не смешиваются** с «лучший красный/чёрный».

| Роль в игре | Сторона | Номинация | Флаг в API |
|-------------|---------|-----------|------------|
| `mafia` | чёрная | Лучший мафия | `is_best_mafia` |
| `don` | чёрная | Лучший дон | `is_best_don` |
| `peaceful` | красная | Лучший мирный | `is_best_peaceful` |
| `sheriff` | красная | Лучший шериф | `is_best_sheriff` |

Источник данных: `rating_game_result.total_points` и `role` по всем играм рейтинга.

---

## Общий алгоритм (одинаковый для всех 4 ролей)

Для каждого игрока и каждой роли `R ∈ {mafia, don, peaceful, sheriff}`:

### Шаг 1 — число игр в роли

```
games_R = количество результатов, где role = R
```

Поля API:
- `games_mafia`, `games_don`, `games_peaceful`, `games_sheriff`

### Шаг 2 — сумма итоговых баллов в роли

```
total_points_R_sum = Σ total_points
  по всем играм рейтинга, где у этого игрока role = R
```

Поля API:
- `total_points_mafia_sum`
- `total_points_don_sum`
- `total_points_peaceful_sum`
- `total_points_sheriff_sum`

`total_points` — итог за партию (победа + доп. баллы), **не** только `bonus_points`.

### Шаг 3 — средний балл в роли

```
avg_points_R = total_points_R_sum / games_R   (если games_R > 0)
```

Округление до **0.01**.

Поля API:
- `avg_points_mafia`, `avg_points_don`, `avg_points_peaceful`, `avg_points_sheriff`

### Шаг 4 — допуск в номинацию

```
игрок участвует в сравнении по роли R  ⇔  games_R >= 3
```

Константа в коде: `_MIN_GAMES_FOR_ROLE_AWARD = 3`.

Если ни у кого `games_R < 3` не выполняется для всех — флаг `is_best_*` для этой роли **никому** не ставится.

### Шаг 5 — выбор победителя по роли R

Среди допущенных игроков максимум по ключу (по убыванию):

1. `avg_points_R`
2. `games_R`
3. `total_points_R_sum`

При полном равенстве ключа — **ничья** (несколько `is_best_* = true`).

---

## По каждой роли отдельно

### Лучший мафия (`is_best_mafia`)

```
games_mafia           = игры, где role = mafia
total_points_mafia_sum = сумма total_points только в этих играх
avg_points_mafia      = total_points_mafia_sum / games_mafia

Участие: games_mafia >= 3
Победитель: max(avg_points_mafia, games_mafia, total_points_mafia_sum)
```

### Лучший дон (`is_best_don`)

```
games_don           = игры, где role = don
total_points_don_sum = сумма total_points только в этих играх
avg_points_don      = total_points_don_sum / games_don

Участие: games_don >= 3
Победитель: max(avg_points_don, games_don, total_points_don_sum)
```

### Лучший мирный (`is_best_peaceful`)

```
games_peaceful           = игры, где role = peaceful
total_points_peaceful_sum = сумма total_points только в этих играх
avg_points_peaceful      = total_points_peaceful_sum / games_peaceful

Участие: games_peaceful >= 3
Победитель: max(avg_points_peaceful, games_peaceful, total_points_peaceful_sum)
```

### Лучший шериф (`is_best_sheriff`)

```
games_sheriff           = игры, где role = sheriff
total_points_sheriff_sum = сумма total_points только в этих играх
avg_points_sheriff      = total_points_sheriff_sum / games_sheriff

Участие: games_sheriff >= 3
Победитель: max(avg_points_sheriff, games_sheriff, total_points_sheriff_sum)
```

---

## Пример

Игрок **A** — 3 игры мафией: `2.0`, `1.0`, `4.0`  
→ `games_mafia = 3`, `total_points_mafia_sum = 7.0`, `avg_points_mafia = 2.33`

Игрок **B** — 4 игры мафией: `2.0`, `2.0`, `2.0`, `2.0`  
→ `games_mafia = 4`, `total_points_mafia_sum = 8.0`, `avg_points_mafia = 2.0`

**Лучший мафия: A** (2.33 > 2.0).

Игрок **C** — 2 игры доном → в номинации «лучший дон» **не участвует** (`games_don < 3`).

---

## Что не входит в номинации по роли

- `games_black` / `games_red` — только счётчики стороны, **не** используются для `is_best_*`
- `bonus_points` отдельно — в формуле победителя **не** участвует, только `total_points`
- ЛХ (`best_move_*`) — отдельная статистика, на `is_best_*` не влияет

---

## Что можно поменить позже

| Параметр | Сейчас | Варианты |
|----------|--------|----------|
| Минимум игр | 3 | 1, 2, 5… |
| Критерий | средний `total_points` | сумма, % побед, гибрид |
| Ничья | все с max-ключом | один победитель по доп. правилу |
| Источник баллов | `total_points` | только `bonus_points` или формула победы |

Файл с логикой в коде: `app/ratings/application/ratings.py` — `_assign_role_award_flags`, `_MIN_GAMES_FOR_ROLE_AWARD`.
