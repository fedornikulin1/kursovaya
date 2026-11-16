"""Shared rules for public chat and marketplace listings."""

import re
import unicodedata

from django.core.exceptions import ValidationError


LOOKALIKES = str.maketrans("acehkmoptxyё", "асенкмортхуе")
RUSSIAN_WORD = re.compile(r"\b[а-я]+\b")
SEPARATED_LETTERS = re.compile(r"(?=\b([а-я](?:[ ._*·-]+[а-я](?!\w)){2,11})\b)")
PROFANITY = re.compile(
    r"бля(?:ть|д[а-я]*)?"
    r"|(?:на|по|о|за|до|под|ни)?ху[йяеюи][а-я]*"
    r"|(?:рас|от|за|на|по|про|с)?пизд[а-я]*"
    r"|(?:за|на|по|вы|от|про|разъ|подъ|съ|долбо)?еб(?:ать|ал|ан|аш|ач|ут|у|уч|ну|ет|ись)[а-я]*"
    r"|(?:муда[кч]|г[ао]ндон|п[ие]д(?:ор|арас))[а-я]*|сука"
)

PROHIBITED_ITEM = re.compile(
    r"\b(?:наркотик|кокаин|мефедрон|амфетамин|метамфетамин|гашиш|марихуан|"
    r"каннабис|экстази|наркозакладк|фентанил|метадон|оружи|пистолет|автоматическ[а-я]*\s+винтовк|боеприпас)[а-я]*\b"
    r"|\bгероин(?:а|у|ом|е)?\b"
    r"|\bпатрон(?:а|у|ом|е|ы|ов|ам|ами|ах)?\b"
    r"|\b(?:вейп|электронн[а-я]*\s+сигарет|никотинов[а-я]*\s+пауч|снюс|сигарет|алкогол|водк|самогон)[а-я]*\b"
    r"|\b(?:поддельн|фальшив)[а-я]*\s+"
    r"(?:паспорт|документ|удостоверени|диплом|студенческ[а-я]*\s+билет)[а-я]*\b"
)
TRANSACTION = re.compile(
    r"(?<!\bне )\b(?:продам|продаю|куплю|покупаю|отдам|обменяю|достану|"
    r"передам|привезу|предлагаю|ищу|нуж(?:ен|на|но|ны)|в наличии|"
    r"(?:могу|хочу|готов[аы]?)\s+(?:продать|купить|отдать|обменять|достать|передать|привезти)|"
    r"у кого(?:-нибудь)? есть|пишите|в личку|цен[ау]|руб(?:лей|ля)?)\b|₽"
)
ACADEMIC_MENTION = re.compile(
    r"\b(?:стать|книг|доклад|реферат|учебник|конспект|лекци|презентаци|материал)[а-я]*"
    r"\s+(?:про|о|об|по теме|по истории)\s+$"
)
HARMLESS_WEAPON = re.compile(r"\b(?:игрушечн|водян|клеев|монтажн)[а-я]*\s+$")
HARMLESS_USE = re.compile(r"\s+для\s+(?:кле|герметик|монтажн[а-я]*\s+пен|краск)")
LIGHTING_USE = re.compile(r"\s+для\s+(?:ламп|люстр|светильник|принтер|дрел)")


def _normalize(body):
    text = unicodedata.normalize("NFKC", body).casefold().translate(LOOKALIKES)
    return "".join(char for char in text if unicodedata.category(char) not in {"Cf", "Mn"})


def _has_profanity(text):
    if any(PROFANITY.fullmatch(word) for word in RUSSIAN_WORD.findall(text)):
        return True
    return any(
        PROFANITY.fullmatch("".join(RUSSIAN_WORD.findall(match[1])))
        for match in SEPARATED_LETTERS.finditer(text)
    )


def _has_prohibited_transaction(text, wanted):
    for sentence in re.split(r"[.!?;]+(?=\s|$)", text):
        sentence = " ".join(sentence.split())
        for item in PROHIBITED_ITEM.finditer(sentence):
            before, after = sentence[:item.start()], sentence[item.end():]
            if ACADEMIC_MENTION.search(before):
                continue
            if item[0].startswith(("пистолет", "оружи")) and (
                HARMLESS_WEAPON.search(before) or HARMLESS_USE.match(after)
            ):
                continue
            if item[0].startswith("патрон") and LIGHTING_USE.match(after):
                continue
            # Keep the match local to the item, so a separate warning need not block a message.
            nearby = sentence[max(0, item.start() - 80):item.end() + 80]
            if wanted or TRANSACTION.search(nearby):
                return True
    return False


def validate_campus_chat_body(body, *, wanted=False):
    text = _normalize(body)
    if _has_profanity(text):
        raise ValidationError(
            "Сообщение содержит ненормативную лексику. Переформулируйте его.",
            code="profanity",
        )
    if _has_prohibited_transaction(text, wanted):
        raise ValidationError(
            "В чате нельзя предлагать или искать запрещённые товары и документы.",
            code="prohibited_transaction",
        )


def validate_listing_text(title, description, exchange_for=""):
    for field, value in (
        ("title", title), ("description", description), ("description", exchange_for)
    ):
        normalized = _normalize(value)
        if _has_prohibited_transaction(normalized, wanted=True):
            raise ValidationError({
                field: "В объявлениях нельзя предлагать или искать запрещённые товары и документы."
            })
        if _has_profanity(normalized):
            raise ValidationError({field: "Уберите ненормативную лексику из объявления."})
