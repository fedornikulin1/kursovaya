# Контракт API v1

Базовый путь `/api/v1/`. Время — ISO 8601 с часовым поясом; деньги — десятичные строки,
не float. Списки пагинированы: `{count, next, previous, results}`. Размер страницы — 20.
Категории возвращаются обычным массивом. Схема OpenAPI: `/api/schema/`, Swagger: `/api/docs/`.

| Метод | Путь относительно v1 | Назначение |
|---|---|---|
| POST | auth/register/ | username, first_name, email, password1, password2 |
| POST | auth/token/ | Вход: username, password → access, refresh |
| POST | auth/token/refresh/ | refresh → новая пара токенов; прежний refresh отзывается |
| POST | auth/logout/ | Отзыв refresh |
| GET/PATCH | me/ | Собственный профиль и настройки контактов |
| GET | users/{username}/ | Публичный профиль без email/телефона |
| GET | categories/ | Категории |
| GET/POST | ads/ | Каталог / создание |
| GET/PATCH/PUT/DELETE | ads/{id}/ | Просмотр / изменение / удаление |
| GET | ads/mine/ | Все свои объявления, включая черновики |
| GET | ads/favorites/ | Активные объявления из избранного |
| POST/DELETE | ads/{id}/favorite/ | Добавить / убрать, идемпотентно |
| GET | ads/{id}/contacts/ | Контакты после входа; phone=null, если скрыт |
| POST | ads/{id}/photos/ | Дополнительные фото: multipart с повторяющимся ключом images |
| DELETE | photos/{id}/ | Удаление дополнительного фото владельцем |
| GET/POST | conversations/ | Свои диалоги / начать: ad, text |
| GET | conversations/{id}/ | Свой диалог |
| GET/POST | conversations/{id}/messages/ | Сообщения / отправить: text |
| POST | conversations/{id}/read/ | Отметить входящие сообщения прочитанными |
| POST | conversations/{id}/accept/ | Принять отклик (только автор объявления) |
| GET/POST | reviews/ | Отзывы / создать: to_user, rating, text |
| GET | reviews/{id}/ | Один отзыв |

## Примеры

Создать объявление (требуется авторизация):

```json
{
  "title": "Учебник по математическому анализу",
  "description": "Без пометок. Могу встретиться у библиотеки.",
  "category": 1,
  "kind": "sell",
  "price_type": "fixed",
  "price": "450.00",
  "location": "Библиотека СВФУ",
  "condition": "used",
  "status": "active"
}
```

`author` назначает сервер. Обложка `image` загружается через multipart.
Для удаления обложки передайте `image: null` в JSON PATCH или используйте форму сайта с флагом очистки.
Дополнительные фото удаляются через `photos/{id}/`.

Форматы цены: `fixed` — обязательна неотрицательная сумма, `free` — сервер задаёт 0,
`negotiable` — сервер задаёт null. Типы: `sell`, `buy`, `service`, `roommate`.
Статусы: `draft`, `active`, `closed`, `archived`.

Фильтры каталога: `q`, `category`, `kind`, `price_type`, `price_min`, `price_max`,
`ordering=-date|date|price|-price`, `page`. Параметр `title` поддержан для старых ссылок.
Пример: `/api/v1/ads/?q=учебник&price_max=1000&ordering=price`.

Получение новых сообщений: `GET conversations/{id}/messages/?after=123` возвращает
сообщения с id > 123 в возрастающем порядке. Без `after` сначала идут новые сообщения.
При наличии `next` нужно прочитать следующие страницы; после показа выполнить `POST read/`.
Возвращается только переписка пользователя. Текст следует выводить как текст, без HTML.

## Ошибки и доступ

400 — ошибка ввода, 401 — нет действующего JWT/входа, 403 — недостаточно прав либо
нет CSRF у сессионного POST, 404 — объект отсутствует или недоступен, 429 — превышение лимита.
Поля ошибок возвращаются объектом; ошибки бизнес-правил могут возвращаться списком.
Не показывайте клиенту произвольный HTML из ответов.

Public GET доступны без токена. Для мобильного клиента:
`Authorization: Bearer <access>`. Для браузерной сессии: cookie сессии и
`X-CSRFToken` при изменении данных. CORS намеренно не открыт всем источникам.
Нативный мобильный клиент не требует CORS; отдельный веб-домен потребует явной настройки.

Отзыв refresh не аннулирует уже выданный access мгновенно. Новый вход выдаёт отдельную
пару токенов. Для режима «выйти со всех устройств» потребуется дополнительная функция.
