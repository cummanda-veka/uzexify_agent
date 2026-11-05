"""Telegram bot profile (name, descriptions, commands, avatar) and its interface texts, RU and UZ.

The profile is applied once at start-up via the Bot API, so @BotFather needs only the token.
"""

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import BotCommand, FSInputFile, InputProfilePhotoStatic

log = logging.getLogger(__name__)

AVATAR = Path(__file__).parent / "assets" / "avatar.jpg"

NAME = {"ru": "UZEXify: сделки биржи", "uz": "UZEXify: birja bitimlari"}

# Shown in the chat before the first message (up to 512 characters).
DESCRIPTION = {
    "ru": (
        "Реестр биржи UZEX: 500 000 сделок с 3 января 2022 по 30 октября 2026 года.\n\n"
        "Спросите, сколько продано, кто покупал больше всех, как менялась цена. Отвечаю по-русски и "
        "по-узбекски, к ответу прикладываю SQL-запрос и строки, из которых взяты цифры."
    ),
    "uz": (
        "UZEX birjasi reyestri: 2022-yil 3-yanvardan 2026-yil 30-oktabrgacha 500 000 ta bitim.\n\n"
        "Qancha sotilgani, kim ko‘p sotib olgani, narx qanday o‘zgargani haqida so‘rang. O‘zbek va rus tilida "
        "javob beraman, javobga SQL so‘rovi va raqamlar olingan qatorlarni ilova qilaman."
    ),
}

# Profile page and share preview (up to 120 characters).
SHORT_DESCRIPTION = {
    "ru": "Сделки биржи UZEX 2022–2026: суммы, объёмы, цены, рейтинги. С SQL-запросом к каждому ответу.",
    "uz": "UZEX birjasi bitimlari 2022–2026: summa, hajm, narx, reyting. Har javobga SQL so‘rovi ilova.",
}

COMMANDS = {
    "ru": [
        BotCommand(command="new", description="Начать новый разговор"),
        BotCommand(command="examples", description="Примеры вопросов"),
        BotCommand(command="help", description="Какие вопросы понимаю"),
    ],
    "uz": [
        BotCommand(command="new", description="Yangi suhbat boshlash"),
        BotCommand(command="examples", description="Savol namunalari"),
        BotCommand(command="help", description="Qanday savollarni tushunaman"),
    ],
}

START = {
    "ru": (
        "Напишите вопрос о сделках биржи UZEX или выберите пример. Данные есть с 3 января 2022 по "
        "30 октября 2026 года.\n\n"
        "Под ответом в блоке «Основание» лежат SQL-запрос и строки, из которых посчитаны цифры."
    ),
    "uz": (
        "UZEX birjasi bitimlari haqida savol yozing yoki namunani tanlang. Ma’lumotlar 2022-yil 3-yanvardan "
        "2026-yil 30-oktabrgacha.\n\n"
        "Javob ostidagi «Asos» blokida SQL so‘rovi va raqamlar hisoblangan qatorlar bor."
    ),
}

HELP = {
    "ru": (
        "Посчитаю сделки, суммы, объёмы и средние цены за любой период; сравню товары, компании, брокеров "
        "и регионы. Компанию найду в любой письменности: «ҲАРАЙЎМ КИМЁ» и «Harayo‘m Kimyo» для меня одно и "
        "то же. Долларовые сделки пересчитываю в сумы по курсу на дату сделки.\n\n"
        "Называйте период: «Сколько пшеницы продали в 2025 году?» Потом можно уточнять: «а по месяцам?», "
        "«покажи на графике».\n\n"
        "В реестре нет руководителей и контактов компаний, прогнозов и сделок после 30.10.2026.\n\n"
        "/new начинает разговор заново."
    ),
    "uz": (
        "Istalgan davr uchun bitimlar soni, summa, hajm va o‘rtacha narxni hisoblayman; tovarlar, kompaniyalar, "
        "brokerlar va viloyatlarni solishtiraman. Kompaniyani istalgan yozuvda topaman: «ҲАРАЙЎМ КИМЁ» va "
        "«Harayo‘m Kimyo» bir kompaniya. Dollardagi bitimlarni bitim kunidagi kurs bo‘yicha so‘mga o‘giraman.\n\n"
        "Davrni ayting: «2025-yilda qancha bug‘doy sotilgan?» Keyin aniqlashtirish mumkin: «oylar bo‘yicha-chi?», "
        "«grafikda ko‘rsat».\n\n"
        "Reyestrda kompaniyalar rahbarlari va kontaktlari, prognozlar va 30.10.2026 dan keyingi bitimlar yo‘q.\n\n"
        "/new suhbatni qaytadan boshlaydi."
    ),
}

NEW_CHAT = {
    "ru": "Новый разговор. Прошлые вопросы больше не учитываются.",
    "uz": "Yangi suhbat. Oldingi savollar endi hisobga olinmaydi.",
}

EXAMPLES_TITLE = {"ru": "Выберите вопрос:", "uz": "Savolni tanlang:"}

EXAMPLES = {
    "ru": [
        "Сколько сделок было заключено в 2024 году?",
        "Какие 5 товаров принесли больше всего денег в 2025 году?",
        "Как менялось число сделок по месяцам в 2025 году?",
        "Сколько в среднем стоила тонна карбамида в 2026 году?",
        "Какие регионы лидируют по продажам хлопка-сырца?",
        "Какая доля сделок 2025 года аннулирована?",
    ],
    "uz": [
        "2023-yilda nechta bitim tuzilgan?",
        "bug‘doy 2025-yilda jami qancha sotilgan?",
        "2025-yilda eng ko‘p pul keltirgan 5 ta tovar qaysilar?",
        "Paxta xomashyosi sotuvi bo‘yicha qaysi viloyatlar yetakchi?",
        "2026-йилда кунига ўртача нечта битим тузилади?",
        "Энг кўп битим тузган сотувчи ким?",
    ],
}


def ui_language(code: str | None) -> str:
    """Interface language from the user's Telegram setting: Uzbek for 'uz', otherwise Russian."""
    return "uz" if (code or "").lower().startswith("uz") else "ru"


async def apply_profile(bot: Bot) -> None:
    """Set name, descriptions, commands and avatar. Russian is the default; Uzbek for 'uz' users.
    Failures are logged, not raised: the bot must answer questions even if the profile call fails."""
    for lang in ("ru", "uz"):
        code = None if lang == "ru" else "uz"
        try:
            await bot.set_my_name(name=NAME[lang], language_code=code)
            await bot.set_my_description(description=DESCRIPTION[lang], language_code=code)
            await bot.set_my_short_description(short_description=SHORT_DESCRIPTION[lang], language_code=code)
            await bot.set_my_commands(commands=COMMANDS[lang], language_code=code)
        except Exception:
            log.exception("bot profile (%s) not applied", lang)
    try:
        await bot.set_my_profile_photo(photo=InputProfilePhotoStatic(photo=FSInputFile(AVATAR)))
    except Exception:
        log.exception("bot avatar not applied")
