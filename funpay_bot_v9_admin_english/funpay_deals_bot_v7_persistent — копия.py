import asyncio
import html
import json
import logging
import os
import random
import re
from pathlib import Path
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

BOT_TOKEN = "8228122380:AAHMoVMhMzVwIp--oHfWFJASh6bWwMWT8D8"
BOT_USERNAME = "funpayDeallsRobot"
SUPPORT_USERNAME = "Relayar_Funpay"
BANNER_PATH = Path(__file__).with_name("funpay_banner.jpg")
LANGUAGE_BANNER_PATH = Path(__file__).with_name("language_selection.jpg")
SCREEN_BANNERS = {
    "faq": {
        "ru": Path(__file__).with_name("screen_faq_ru.jpg"),
        "en": Path(__file__).with_name("screen_faq_en.jpg"),
    },
    "profile": {
        "ru": Path(__file__).with_name("screen_profile_ru.jpg"),
        "en": Path(__file__).with_name("screen_profile_en.jpg"),
    },
    "requisites": {
        "ru": Path(__file__).with_name("screen_requisites_ru.jpg"),
        "en": Path(__file__).with_name("screen_requisites_en.jpg"),
    },
    "create_deal": {
        "ru": Path(__file__).with_name("screen_create_deal_ru.jpg"),
        "en": Path(__file__).with_name("screen_create_deal_en.jpg"),
    },
    "withdraw": {
        "ru": Path(__file__).with_name("screen_withdraw_ru.jpg"),
        "en": Path(__file__).with_name("screen_withdraw_en.jpg"),
    },
    "active_deals": {
        "ru": Path(__file__).with_name("screen_active_deals_ru.jpg"),
        "en": Path(__file__).with_name("screen_active_deals_en.jpg"),
    },
    "active_withdrawals": {
        "ru": Path(__file__).with_name("screen_active_withdrawals_ru.jpg"),
        "en": Path(__file__).with_name("screen_active_withdrawals_en.jpg"),
    },
}
DATA_PATH = Path(os.getenv("BOT_DATA_PATH", str(Path(__file__).with_name("bot_data.json"))))
TEST_MODE = os.getenv("TEST_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}
ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}
SUPPORTED_CURRENCIES = {
    "EUR", "RUB", "UAH", "KZT", "USD", "BYN", "AZN",
    "AMD", "GEL", "KGS", "TJS", "UZS", "Ton", "stars"
}

CURRENCY_BUTTONS = [
    ("EUR", "5228784522924930237"),
    ("RUB", "5449408995691341691"),
    ("UAH", "5447309366568953338"),
    ("KZT", "5228718354658769982"),
    ("USD", "5202021044105257611"),
    ("BYN", "5382219601054544127"),
    ("AZN", "5224254431939275524"),
    ("AMD", "5411455658186778270"),
    ("GEL", "5440371950708864925"),
    ("KGS", "5427268877367130483"),
    ("TJS", "5427304285077516492"),
    ("UZS", "5449829434334912605"),
]

CREATE_GAME_CATEGORIES = [
    ("Rust", "5433725703566669596"),
    ("Counter-strike 2", "5431628883352895287"),
    ("Roblox", "5318760565902947324"),
    ("Standoff 2", "5318760565902947324"),
    ("Brawl Stars", "5431537486448835478"),
    ("Clash of Clans", "5318760565902947324"),
    ("Fortnite", "5431699131837985981"),
    ("PUBG", "5406897443755275286"),
    ("Подарок", "5361986358015463601"),
    ("Аккаунт", "5271604874419647061"),
]
CREATE_GAME_OTHER_EMOJI_ID = "5416117059207572332"
ACTIVE_DEALS_EMOJI_ID = "5395732581780040886"
WITHDRAW_EMOJI_ID = "5201691993775818138"
REFERRALS_EMOJI_ID = "5271604874419647061"
REFERRAL_COUNT_EMOJI_ID = "5453957997418004470"
REFERRAL_EARNINGS_EMOJI_ID = "5409048419211682843"

router = Router()

# Рабочие словари автоматически загружаются из bot_data.json и сохраняются
# после каждого изменения, поэтому реквизиты, балансы и сделки не теряются
# после перезапуска бота.
deals: dict[str, dict] = {}
profiles: dict[int, dict] = {}
promocodes: dict[str, dict] = {}
withdrawals: dict[str, dict] = {}


def load_persistent_data() -> None:
    global deals, profiles, promocodes, withdrawals
    if not DATA_PATH.is_file():
        return
    try:
        payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        deals = payload.get("deals", {}) if isinstance(payload.get("deals", {}), dict) else {}
        raw_profiles = payload.get("profiles", {})
        profiles = {
            int(user_id): profile
            for user_id, profile in raw_profiles.items()
            if str(user_id).isdigit() and isinstance(profile, dict)
        } if isinstance(raw_profiles, dict) else {}
        promocodes = payload.get("promocodes", {}) if isinstance(payload.get("promocodes", {}), dict) else {}
        withdrawals = payload.get("withdrawals", {}) if isinstance(payload.get("withdrawals", {}), dict) else {}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        logging.exception("Не удалось загрузить данные из %s", DATA_PATH)


def save_persistent_data() -> None:
    payload = {
        "deals": deals,
        "profiles": {str(user_id): profile for user_id, profile in profiles.items()},
        "promocodes": promocodes,
        "withdrawals": withdrawals,
    }
    temporary_path = DATA_PATH.with_name(f"{DATA_PATH.name}.tmp")
    try:
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary_path, DATA_PATH)
    except OSError:
        logging.exception("Не удалось сохранить данные в %s", DATA_PATH)
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


load_persistent_data()


def premium_emoji(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def display_username(user) -> str:
    return f"@{html.escape(user.username)}" if user.username else str(user.id)


def stored_username(user) -> str:
    return user.username or str(user.id)


def get_profile(user_id: int, username: str | None = None) -> dict:
    created = user_id not in profiles
    profile = profiles.setdefault(
        user_id,
        {
            "username": username or str(user_id),
            "balances": {},
            "successful_deals": 0,
            "requisites": {},
            "used_promocodes": [],
            "language": "ru",
            "language_selected": False,
            "referrer_id": None,
            "referrals": [],
            "referral_earnings_ton": "0",
        },
    )
    changed = created
    if username and profile.get("username") != username:
        profile["username"] = username
        changed = True
    profile.setdefault("balances", {})
    profile.setdefault("requisites", {})
    profile.setdefault("used_promocodes", [])
    profile.setdefault("successful_deals", 0)
    if "language" not in profile:
        profile["language"] = "ru"
        changed = True
    if profile.get("language") not in {"ru", "en"}:
        profile["language"] = "ru"
        changed = True
    if "language_selected" not in profile:
        # Profiles from previous bot versions have already passed the language step.
        profile["language_selected"] = not created
        changed = True
    if "referrer_id" not in profile:
        profile["referrer_id"] = None
        changed = True
    if not isinstance(profile.get("referrals"), list):
        profile["referrals"] = []
        changed = True
    if "referral_earnings_ton" not in profile:
        profile["referral_earnings_ton"] = "0"
        changed = True
    if changed:
        save_persistent_data()
    return profile


def format_decimal(value: str | Decimal) -> str:
    number = Decimal(str(value))
    normalized = format(number.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def register_referral(user_id: int, referrer_id: int) -> bool:
    if user_id <= 0 or referrer_id <= 0 or user_id == referrer_id:
        return False

    user_profile = get_profile(user_id)
    if user_profile.get("referrer_id") not in {None, ""}:
        return False

    referrer_profile = get_profile(referrer_id)
    referrals = referrer_profile.setdefault("referrals", [])
    if user_id not in referrals:
        referrals.append(user_id)

    user_profile["referrer_id"] = referrer_id
    save_persistent_data()
    return True


def referral_text(user) -> str:
    profile = get_profile(user.id, stored_username(user))
    referrals = profile.get("referrals", [])
    referral_count = len({int(value) for value in referrals if str(value).isdigit()})
    try:
        earnings = Decimal(str(profile.get("referral_earnings_ton", "0")))
    except (InvalidOperation, TypeError, ValueError):
        earnings = Decimal("0")
    earnings_text = format_decimal(earnings)
    if "." not in earnings_text:
        earnings_text += ".0"
    referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user.id}"

    return (
        f'{premium_emoji(REFERRALS_EMOJI_ID, "🎁")} '
        '<b>Ваша реферальная ссылка:</b>\n\n'
        f'<code>{html.escape(referral_link)}</code>\n\n'
        f'{premium_emoji(REFERRAL_COUNT_EMOJI_ID, "👥")} '
        f'Количество рефералов: {referral_count}\n'
        f'{premium_emoji(REFERRAL_EARNINGS_EMOJI_ID, "💰")} '
        f'Заработано с рефералов: {earnings_text} TON\n'
        '<b>40% от комиссии бота</b>'
    )


def format_balance(profile: dict) -> str:
    balances = profile.get("balances", {})
    non_zero: list[str] = []
    if profile.get("test_unlimited"):
        non_zero.append("<b>TEST:</b> безлимит")
    for currency in sorted(balances):
        amount = Decimal(str(balances[currency]))
        if amount > 0:
            non_zero.append(
                f"<b>{html.escape(currency)}:</b> {format_decimal(amount)}"
            )
    return "\n".join(non_zero) if non_zero else "Нет доступных средств"


def active_deals_count(user_id: int) -> int:
    active_statuses = {"created", "joined", "buyer_paid"}
    return sum(
        1
        for deal in deals.values()
        if deal.get("status", "created") in active_statuses
        and user_id in {deal.get("seller_id"), deal.get("buyer_id")}
    )


def add_balance(user_id: int, currency: str, amount: str) -> None:
    profile = get_profile(user_id)
    balances = profile.setdefault("balances", {})
    current = Decimal(str(balances.get(currency, "0")))
    balances[currency] = str(current + Decimal(str(amount)))
    save_persistent_data()


def get_balance(user_id: int, currency: str) -> Decimal:
    profile = get_profile(user_id)
    return Decimal(str(profile.setdefault("balances", {}).get(currency, "0")))


def has_sufficient_balance(user_id: int, currency: str, amount: str) -> bool:
    profile = get_profile(user_id)
    if profile.get("test_unlimited"):
        return True
    return get_balance(user_id, currency) >= Decimal(str(amount))


def debit_balance(user_id: int, currency: str, amount: str) -> None:
    profile = get_profile(user_id)
    if profile.get("test_unlimited"):
        return
    balances = profile.setdefault("balances", {})
    current = Decimal(str(balances.get(currency, "0")))
    debit = Decimal(str(amount))
    if current < debit:
        raise ValueError("Недостаточно средств")
    balances[currency] = str(current - debit)
    save_persistent_data()


def has_any_requisites(user_id: int) -> bool:
    requisites = get_profile(user_id).get("requisites", {})
    return any(bool(str(value).strip()) for value in requisites.values())


def has_requisite(user_id: int, requisite_type: str) -> bool:
    value = get_profile(user_id).get("requisites", {}).get(requisite_type)
    return bool(str(value).strip()) if value is not None else False


def get_requisite(user_id: int, requisite_type: str) -> str:
    return str(
        get_profile(user_id).get("requisites", {}).get(requisite_type, "")
    ).strip()


def normalize_promocode(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def normalize_currency(value: str) -> str:
    cleaned = value.strip()
    if cleaned.upper() == "TON":
        return "Ton"
    if cleaned.lower() == "stars":
        return "stars"
    return cleaned.upper()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


EN_TRANSLATIONS = {
    "Добро пожаловать в FunPay Deals Bot": "Welcome to FunPay Deals Bot",
    "ваш надёжный сервис безопасных и удобных сделок!": "your reliable service for safe and convenient deals!",
    "Автоматизированные сделки": "Automated deals",
    "Реферальная система": "Referral system",
    "Вывод средств в любой валюте": "Withdrawals in any currency",
    "Поддержка 24/7": "24/7 support",
    "Выберите нужный раздел ниже!": "Choose a section below!",
    "Назад": "Back",
    "Реквизиты": "Payment details",
    "Создать сделку": "Create deal",
    "Профиль": "Profile",
    "Язык": "Language",
    "Поддержка": "Support",
    "Рефералы": "Referrals",
    "Ваша реферальная ссылка:": "Your referral link:",
    "Количество рефералов:": "Number of referrals:",
    "Заработано с рефералов:": "Earned from referrals:",
    "40% от комиссии бота": "40% of the bot commission",
    "Админ панель": "Admin panel",
    "Банковская карта": "Bank card",
    "TON кошелек": "TON wallet",
    "TON-кошелёк": "TON wallet",
    "Указать реквизиты": "Add payment details",
    "Отменить сделку": "Cancel deal",
    "Оплатить": "Pay",
    "Отмена": "Cancel",
    "Отправить деньги продавцу": "Send money to seller",
    "Вывести деньги": "Withdraw funds",
    "Начислить тестовый баланс": "Add test balance",
    "Установить успешные сделки": "Set successful deals",
    "Включить тестовый безлимит": "Enable unlimited test balance",
    "ТЕСТОВАЯ ПАНЕЛЬ": "TEST PANEL",
    "Доступ открыт общим кодом": "Access is enabled with the public code",
    "Код может использовать любой пользователь.": "Any user can use this code.",
    "Информация о профиле": "Profile information",
    "Пользователь:": "User:",
    "Баланс:": "Balance:",
    "Баланс": "Balance",
    "Активные сделки:": "Active deals:",
    "Активные сделки": "Active deals",
    "Активные выводы": "Active withdrawals",
    "Нет активных сделок.": "No active deals.",
    "Нет активных заявок.": "No active withdrawal requests.",
    "Выберите сделку, чтобы открыть её.": "Choose a deal to open it.",
    "Отправить ссылку": "Share join link",
    "Вернуться к списку": "Back to list",
    "Роль:": "Role:",
    "Статус:": "Status:",
    "Продавец": "Seller",
    "Ссылка для присоединения:": "Join link:",
    "Ожидает покупателя": "Waiting for buyer",
    "Покупатель присоединился": "Buyer joined",
    "Оплачена покупателем": "Paid by buyer",
    "Успешные сделки:": "Successful deals:",
    "Успешных сделок:": "Successful deals:",
    "Успешные сделки": "Successful deals",
    "Создание сделки - FunPay": "Creating a deal — FunPay",
    "Создание сделки": "Creating a deal",
    "Выберите игру или категорию товара.": "Choose a game or product category.",
    "Напишите своё название игры или категории товара.": "Enter your game or product category name.",
    "Подарок": "Gift",
    "Аккаунт": "Account",
    "Другое": "Other",
    "Неизвестная категория.": "Unknown category.",
    "Снизу напишите": "Enter below",
    "игру": "the game",
    "или категорию товара.": "or the product category.",
    "Введите подробное описание товара.": "Enter a detailed product description.",
    "Укажите уровень, скины, инвентарь, достижения и другие особенности.": "Specify the level, skins, inventory, achievements, and other details.",
    "Неверная сумма": "Invalid amount",
    "Пожалуйста, введите корректную сумму": "Please enter a valid amount",
    "например": "for example",
    "Укажите сумму сделки в": "Enter the deal amount in",
    "Пример:": "Example:",
    "Указывайте точную сумму, чтобы избежать ошибок при обработке сделки.": "Enter the exact amount to avoid errors while processing the deal.",
    "Не указаны реквизиты": "Payment details are not specified",
    "Введите, сколько хотите вывести": "Enter the amount you want to withdraw",
    "Вывести": "Withdraw",
    "Вывод средств": "Withdraw funds",
    "Выберите способ вывода:": "Choose a withdrawal method:",
    "Выберите валюту для вывода на банковскую карту:": "Choose the currency for withdrawal to a bank card:",
    "Неизвестная валюта.": "Unknown currency.",
    "Неверно указана сумма": "Invalid amount",
    "Недостаточно средств": "Insufficient funds",
    "Сумма вывода": "Withdrawal amount",
    "Способ:": "Method:",
    "Реквизиты:": "Payment details:",
    "Данные заявки устарели. Повторите вывод.": "The withdrawal request has expired. Please try again.",
    "Заявка на вывод создана": "Withdrawal request created",
    "Сумма:": "Amount:",
    "Номер заявки:": "Request ID:",
    "Новая заявка на вывод": "New withdrawal request",
    "Заявка:": "Request:",
    "Язык интерфейса:": "Interface language:",
    "Язык интерфейса: Русский": "Interface language: Russian",
    "Язык интерфейса: Английский": "Interface language: English",
    "Выберите язык интерфейса:": "Choose the interface language:",
    "Язык изменён на русский.": "Language changed to Russian.",
    "Язык изменён на английский.": "Language changed to English.",
    "Промокод не найден или больше не действует": "The promo code was not found or is no longer active",
    "Вы уже использовали этот промокод": "You have already used this promo code",
    "Лимит активаций этого промокода исчерпан": "The activation limit for this promo code has been reached",
    "Формат:": "Format:",
    "Промокод Work активирован": "Work promo code activated",
    "Безлимитный баланс включён.": "Unlimited balance enabled.",
    "Промокод": "Promo code",
    "Промокод ClezzyKryt активирован": "ClezzyKryt promo code activated",
    "Промокод успешно активирован": "Promo code activated successfully",
    "Начислено:": "Credited:",
    "Доступ запрещён.": "Access denied.",
    "Промокод создаётся без привязки к Telegram ID.": "The promo code is created without binding it to a Telegram ID.",
    "Без лимита:": "No limit:",
    "Лимит должен быть целым числом больше нуля.": "The limit must be a positive integer.",
    "Код должен содержать 3–32 символа: буквы, цифры, _ или -.": "The code must contain 3–32 characters: letters, digits, _ or -.",
    "Неверная валюта или сумма.": "Invalid currency or amount.",
    "без ограничений": "unlimited",
    "Промокод создан": "Promo code created",
    "Код:": "Code:",
    "Награда:": "Reward:",
    "Лимит активаций:": "Activation limit:",
    "Промокод не найден.": "Promo code not found.",
    "отключён.": "disabled.",
    "Промокоды ещё не созданы.": "No promo codes have been created yet.",
    "Промокоды:": "Promo codes:",
    "активен": "active",
    "отключён": "disabled",
    "Выберите тип реквизитов:": "Choose the payment details type:",
    "Добавьте банковскую карту": "Add a bank card",
    "Отправьте номер карты в формате:": "Send the card number in this format:",
    "Не верно указаны реквизиты": "Invalid payment details",
    "Банковская карта успешно добавлена": "Bank card added successfully",
    "Добавьте ваш TON-кошелёк:": "Add your TON wallet:",
    "Отправьте адрес кошелька (начинается с UQ или EQ)...": "Send the wallet address (starts with UQ or EQ)...",
    "TON-кошелёк успешно добавлен": "TON wallet added successfully",
    "Укажите ваш телеграм Юзернейм": "Enter your Telegram username",
    "Например Username без @": "For example, Username without @",
    "Telegram Юзернейм успешно добавлен": "Telegram username added successfully",
    "Выберите способ оплаты": "Choose a payment method",
    "Выберите валюту для оплаты банковской картой:": "Choose the bank-card payment currency:",
    "ПРЕДУПРЕЖДЕНИЕ ПЕРЕД СОЗДАНИЕМ СДЕЛКИ": "WARNING BEFORE CREATING A DEAL",
    "Передача любого товара напрямую покупателю — это мошенничество!": "Sending any product directly to the buyer is unsafe and may result in fraud!",
    "Нельзя передавать напрямую. Как только сделка создана, передавайте подарок только на официальный аккаунт": "Do not transfer the product directly. Once the deal is created, send the product only to the official account",
    "Нельзя передавать напрямую. Как только сделка создана, передавайте товар только официальному аккаунту поддержки": "Do not transfer the product directly. Once the deal is created, transfer it only to the official support account",
    "Если вы продаёте канал, передайте владельца канала официальному аккаунту.": "If you are selling a channel, transfer channel ownership to the official account.",
    "Чтобы успешно завершить сделку и получить средства — всегда отправляйте заявленный товар только на": "To complete the deal and receive the funds, always send the listed product only to",
    "Ознакомлен(-а)": "I understand",
    "Сделка успешно создана!": "Deal created successfully!",
    "ID сделки:": "Deal ID:",
    "Описание:": "Description:",
    "Оплата:": "Payment:",
    "Ссылка на вашу сделку:": "Your deal link:",
    "<b>Сделка ": "<b>Deal ",
    "Сделка не найдена.": "Deal not found.",
    "Отменить сделку может только продавец.": "Only the seller can cancel the deal.",
    "Завершённую сделку отменить нельзя.": "A completed deal cannot be canceled.",
    "Оплаченную сделку отменить нельзя.": "A paid deal cannot be canceled.",
    "Сделка была успешно отменена": "The deal was successfully canceled",
    "Сделка была отменена": "The deal was canceled",
    "Средства были возвращены на ваш баланс": "The funds were returned to your balance",
    "отменена": "canceled",
    "Сделка не найдена или была отменена.": "The deal was not found or was canceled.",
    "Сделка уже завершена.": "The deal is already completed.",
    "Вы не можете присоединиться к собственной сделке.": "You cannot join your own deal.",
    "К этой сделке уже присоединился другой покупатель.": "Another buyer has already joined this deal.",
    "Продавец:": "Seller:",
    "Сделка:": "Deal:",
    "Сумма сделки:": "Deal amount:",
    "Товар:": "Product:",
    "Новый участник в сделке": "New participant in deal",
    "Пользователь": "User",
    "присоединился к сделке.": "joined the deal.",
    "Внимание:": "Warning:",
    "Убедитесь, что это именно тот пользователь, с которым вы ранее вели переговоры.": "Make sure this is the same user you previously negotiated with.",
    "Не отправляйте подарок до подтверждения оплаты в этом чате!": "Do not send the product until payment is confirmed in this chat!",
    "Подарок нужно передать только аккаунту поддержки": "The product must be transferred only to the support account",
    "Подарок строго отправляется на аккаунт": "The product must be sent only to the account",
    "В случае если вы отправите подарок напрямую — вернуть подарок будет невозможно.": "If you send the product directly, it may be impossible to recover it.",
    "Вы не являетесь покупателем этой сделки.": "You are not the buyer in this deal.",
    "Оплаченную сделку отменить этой кнопкой нельзя.": "A paid deal cannot be canceled with this button.",
    "Вы отменили участие в сделке": "You canceled your participation in deal",
    "Сделка не найдена или отменена.": "The deal was not found or was canceled.",
    "Оплатить сделку может только её покупатель.": "Only the buyer can pay for the deal.",
    "Недостаточно средств. Баланс:": "Insufficient funds. Balance:",
    "Вы оплатили сделку": "You paid for the deal",
    "Покупатель": "Buyer",
    "Оплатил вашу Сделку на сумму": "Paid your deal in the amount of",
    "Просим передать товар на Аккаунт Поддержки": "Please transfer the product to the support account",
    "Подтвердить перевод может только покупатель.": "Only the buyer can confirm the transfer.",
    "Сделка уже подтверждена.": "The deal has already been confirmed.",
    "Сначала оплатите сделку.": "Pay for the deal first.",
    "Сделка успешно подтверждена": "Deal successfully confirmed",
    "Деньги были отправлены на ваш баланс бота": "The money was credited to your bot balance",
    "Платёж подтверждён": "Payment confirmed",
    "Средства отправлены продавцу": "The funds were sent to the seller",
    "Сначала введите /ClezzyKryt.": "Enter /ClezzyKryt first.",
    "Промокод Work активирован. Безлимитный баланс включён.": "Work promo code activated. Unlimited balance enabled.",
    "Начисление тестового баланса": "Adding test balance",
    "Отправьте одной строкой:": "Send in one line:",
    "КОД": "CODE",
    "ВАЛЮТА": "CURRENCY",
    "СУММА": "AMOUNT",
    "ЛИМИТ": "LIMIT",
    "Неверный формат.": "Invalid format.",
    "Используйте:": "Use:",
    "Тестовый баланс начислен.": "Test balance credited.",
    "Установка тестового количества успешных сделок": "Setting the test number of successful deals",
    "Отправьте:": "Send:",
    "КОЛИЧЕСТВО": "COUNT",
    "Тестовое значение обновлено.": "Test value updated.",
    "Тестовый безлимит включён.": "Unlimited test balance enabled.",
    "Нет доступных средств": "No available funds",
    "безлимит": "unlimited",
}


def get_language(user_id: int | None) -> str:
    if user_id is None or user_id <= 0:
        return "ru"
    return str(get_profile(user_id).get("language", "ru"))


def localize_text(user_id: int | None, text: str | None) -> str | None:
    if text is None or get_language(user_id) != "en":
        return text
    localized = text
    for source, target in sorted(EN_TRANSLATIONS.items(), key=lambda item: len(item[0]), reverse=True):
        localized = localized.replace(source, target)
    return localized


def localize_markup(
    user_id: int | None,
    markup: InlineKeyboardMarkup | None,
) -> InlineKeyboardMarkup | None:
    if markup is None or get_language(user_id) != "en":
        return markup
    return markup.model_copy(
        update={
            "inline_keyboard": [
                [button.model_copy(update={"text": localize_text(user_id, button.text)}) for button in row]
                for row in markup.inline_keyboard
            ]
        }
    )


async def answer_callback(
    callback: CallbackQuery,
    text: str | None = None,
    **kwargs,
):
    try:
        return await callback.answer(localize_text(callback.from_user.id, text), **kwargs)
    except Exception:
        return None


def screen_banner_path(user_id: int | None, screen: str | None = None) -> Path:
    if screen == "language":
        return LANGUAGE_BANNER_PATH
    if screen in SCREEN_BANNERS:
        language = get_language(user_id)
        selected = SCREEN_BANNERS[screen].get(language) or SCREEN_BANNERS[screen]["ru"]
        if selected.is_file():
            return selected
    return BANNER_PATH


def banner_file(path: Path | None = None) -> FSInputFile:
    return FSInputFile(path or BANNER_PATH)


async def send_screen_message(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    screen: str | None = None,
) -> Message:
    user_id = message.from_user.id if message.from_user else message.chat.id
    text = localize_text(user_id, text)
    reply_markup = localize_markup(user_id, reply_markup)
    photo_path = screen_banner_path(user_id, screen)
    if photo_path.is_file():
        return await message.answer_photo(
            photo=banner_file(photo_path),
            caption=text,
            reply_markup=reply_markup,
        )
    return await message.answer(text, reply_markup=reply_markup)


async def send_screen_chat(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    screen: str | None = None,
) -> Message:
    text = localize_text(chat_id, text)
    reply_markup = localize_markup(chat_id, reply_markup)
    photo_path = screen_banner_path(chat_id, screen)
    if photo_path.is_file():
        return await bot.send_photo(
            chat_id=chat_id,
            photo=banner_file(photo_path),
            caption=text,
            reply_markup=reply_markup,
        )
    return await bot.send_message(chat_id, text, reply_markup=reply_markup)


async def edit_screen_message(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    screen: str | None = None,
) -> None:
    user_id = message.chat.id
    text = localize_text(user_id, text)
    reply_markup = localize_markup(user_id, reply_markup)
    photo_path = screen_banner_path(user_id, screen)
    try:
        if message.photo and photo_path.is_file():
            await message.edit_media(
                media=InputMediaPhoto(media=banner_file(photo_path), caption=text),
                reply_markup=reply_markup,
            )
        elif message.photo:
            await message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def delete_user_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def edit_state_message(
    message: Message,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    screen: str | None = None,
) -> None:
    data = await state.get_data()
    user_id = message.from_user.id if message.from_user else message.chat.id
    text = localize_text(user_id, text)
    reply_markup = localize_markup(user_id, reply_markup)
    chat_id = data.get("ui_chat_id", message.chat.id)
    message_id = data.get("ui_message_id")
    ui_has_photo = bool(data.get("ui_has_photo"))
    active_screen = screen or data.get("ui_screen")
    photo_path = screen_banner_path(user_id, active_screen)

    if message_id is None:
        sent = await send_screen_message(message, text, reply_markup, active_screen)
        await state.update_data(
            ui_chat_id=sent.chat.id,
            ui_message_id=sent.message_id,
            ui_has_photo=bool(sent.photo),
            ui_screen=active_screen,
        )
    else:
        try:
            if ui_has_photo and photo_path.is_file():
                await message.bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=message_id,
                    media=InputMediaPhoto(media=banner_file(photo_path), caption=text),
                    reply_markup=reply_markup,
                )
            elif ui_has_photo:
                await message.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=text,
                    reply_markup=reply_markup,
                )
            else:
                await message.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup,
                )
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise

    await delete_user_message(message)


class CreateDeal(StatesGroup):
    waiting_game = State()
    waiting_description = State()
    waiting_amount = State()


class Requisites(StatesGroup):
    waiting_card = State()
    waiting_ton = State()
    waiting_stars = State()


class Withdraw(StatesGroup):
    waiting_amount = State()


class TestAdmin(StatesGroup):
    waiting_balance = State()
    waiting_successful_deals = State()


WELCOME_TEXT = (
    f'{premium_emoji("5325547803936572038", "✨")} '
    '<b>Добро пожаловать в FunPay Deals Bot</b> — ваш надёжный сервис безопасных и удобных сделок!'
    f' {premium_emoji("5325547803936572038", "✨")}\n\n'
    f'{premium_emoji("5312326644764018054", "🌟")} <b>Автоматизированные сделки</b>\n'
    f'{premium_emoji("5361841922560266597", "🌟")} <b>Реферальная система</b>\n'
    f'{premium_emoji("5310191758255099001", "🌟")} <b>Вывод средств в любой валюте</b>\n'
    f'{premium_emoji("5312103894875143512", "🌟")} <b>Поддержка 24/7</b>\n\n'
    f'{premium_emoji("5406745015365943482", "🔽")} Выберите нужный раздел ниже!'
)


FAQ_TEXT = (
    '<b>'
    f'{premium_emoji("5449408995691341691", "❓")} F.A.Q — Часто задаваемые вопросы\n\n'
    f'{premium_emoji("5436113877181941026", "1️⃣")} Что делает бот?\n'
    f'{premium_emoji("5382322671679708881", "🤖")} Бот выступает автоматическим гарантом сделок: он обеспечивает безопасный обмен NFT-подарками, Telegram-каналами, чатами, кодами для ботов и другими цифровыми товарами.\n\n'
    f'{premium_emoji("5381990043642502553", "2️⃣")} Что можно купить или продать?\n'
    f'{premium_emoji("5240228673738527951", "🛍")} Практически всё — от цифровых активов до кодов, подписок и Telegram-ресурсов.\n\n'
    f'{premium_emoji("5381879959335738545", "3️⃣")} Как проходит сделка?\n'
    f'{premium_emoji("5893450623449305489", "⚡")} Все сделки автоматизированы: бот фиксирует товар и оплату, а после подтверждения переводит средства и активы.\n\n'
    f'{premium_emoji("5382054253403577563", "4️⃣")} Как выводить средства?\n'
    f'{premium_emoji("5445353829304387411", "💳")} Вывод доступен в любой удобной валюте.\n\n'
    f'{premium_emoji("5391197405553107640", "5️⃣")} Есть ли поддержка?\n'
    f'{premium_emoji("5388617328504092754", "📞")} Да! Поддержка работает 24/7, чтобы помочь вам в любых вопросах.\n\n'
    f'{premium_emoji("5390966190283694453", "6️⃣")} Безопасно ли это?\n'
    f'{premium_emoji("5197288647275071607", "🔒")} Да, бот использует автоматизированный гарант, что исключает риск обмана.</b>'
)

FAQ_TEXT_EN = (
    '<b>'
    f'{premium_emoji("5449408995691341691", "❓")} F.A.Q — Frequently Asked Questions\n\n'
    f'{premium_emoji("5436113877181941026", "1️⃣")} What does the bot do?\n'
    f'{premium_emoji("5382322671679708881", "🤖")} The bot acts as an automated escrow service: it ensures secure exchanges of NFT gifts, Telegram channels, chats, bot codes, and other digital goods.\n\n'
    f'{premium_emoji("5381990043642502553", "2️⃣")} What can I buy or sell?\n'
    f'{premium_emoji("5240228673738527951", "🛍")} Almost anything — from digital assets to codes, subscriptions, and Telegram resources.\n\n'
    f'{premium_emoji("5381879959335738545", "3️⃣")} How does a deal work?\n'
    f'{premium_emoji("5893450623449305489", "⚡")} All deals are automated: the bot records the item and payment, then transfers the funds and assets after confirmation.\n\n'
    f'{premium_emoji("5382054253403577563", "4️⃣")} How can I withdraw funds?\n'
    f'{premium_emoji("5445353829304387411", "💳")} Withdrawals are available in any convenient currency.\n\n'
    f'{premium_emoji("5391197405553107640", "5️⃣")} Is support available?\n'
    f'{premium_emoji("5388617328504092754", "📞")} Yes! Support is available 24/7 to help with any questions.\n\n'
    f'{premium_emoji("5390966190283694453", "6️⃣")} Is it safe?\n'
    f'{premium_emoji("5197288647275071607", "🔒")} Yes. The bot uses an automated escrow system, which eliminates the risk of fraud.</b>'
)


def back_button(callback_data: str = "back_main") -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text="Назад",
        callback_data=callback_data,
        icon_custom_emoji_id="5195445307441176556",
    )


def main_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Реквизиты",
                callback_data="requisites",
                icon_custom_emoji_id="5359785904535774578",
            ),
            InlineKeyboardButton(
                text="Создать сделку",
                callback_data="create_deal",
                icon_custom_emoji_id="5458603043203327669",
            ),
        ],
        [
            InlineKeyboardButton(
                text="Профиль",
                callback_data="profile",
                icon_custom_emoji_id="5461117441612462242",
            ),
            InlineKeyboardButton(
                text="Язык",
                callback_data="language",
                icon_custom_emoji_id="5447410659077661506",
            ),
        ],
        [
            InlineKeyboardButton(
                text="Рефералы",
                callback_data="referrals",
                icon_custom_emoji_id=REFERRALS_EMOJI_ID,
            )
        ],
    ]
    if user_id is not None and get_profile(user_id).get("clezzy_access"):
        rows.append(
            [
                InlineKeyboardButton(
                    text="Админ панель",
                    callback_data="admin_panel",
                    icon_custom_emoji_id="5440660757194744323",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="F.A.Q",
                callback_data="faq",
                icon_custom_emoji_id="5436113877181941026",
            ),
            InlineKeyboardButton(
                text="Поддержка",
                url=f"https://t.me/{SUPPORT_USERNAME}",
                icon_custom_emoji_id="5251203410396458957",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def requisites_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Банковская карта",
                    callback_data="req_card",
                    icon_custom_emoji_id="5445353829304387411",
                )
            ],
            [
                InlineKeyboardButton(
                    text="TON кошелек",
                    callback_data="req_ton",
                    icon_custom_emoji_id="5427168083074628963",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Stars",
                    callback_data="req_stars",
                    icon_custom_emoji_id="5438496463044752972",
                )
            ],
            [back_button()],
        ]
    )


def no_requisites_keyboard(back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Указать реквизиты",
                    callback_data="requisites",
                    icon_custom_emoji_id="5359785904535774578",
                )
            ],
            [back_button(back_callback)],
        ]
    )


def withdraw_method_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Банковская карта",
                    callback_data="withdraw_card",
                    icon_custom_emoji_id="5445353829304387411",
                )
            ],
            [
                InlineKeyboardButton(
                    text="TON кошелек",
                    callback_data="withdraw_ton",
                    icon_custom_emoji_id="5427168083074628963",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Stars",
                    callback_data="withdraw_stars",
                    icon_custom_emoji_id="5438496463044752972",
                )
            ],
            [back_button("profile")],
        ]
    )


def withdraw_currency_keyboard() -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for currency, emoji_id in CURRENCY_BUTTONS:
        row.append(
            InlineKeyboardButton(
                text=currency,
                callback_data=f"withdraw_currency_{currency}",
                icon_custom_emoji_id=emoji_id,
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([back_button("withdraw")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_game_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for index, (game_name, emoji_id) in enumerate(CREATE_GAME_CATEGORIES):
        row.append(
            InlineKeyboardButton(
                text=game_name,
                callback_data=f"create_game_category_{index}",
                icon_custom_emoji_id=emoji_id,
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(
                text="Другое",
                callback_data="create_game_other",
                icon_custom_emoji_id=CREATE_GAME_OTHER_EMOJI_ID,
            )
        ]
    )
    rows.append([back_button("back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_payment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Банковская карта",
                    callback_data="create_pay_card",
                    icon_custom_emoji_id="5445353829304387411",
                )
            ],
            [
                InlineKeyboardButton(
                    text="TON кошелек",
                    callback_data="create_pay_ton",
                    icon_custom_emoji_id="5427168083074628963",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Stars",
                    callback_data="create_pay_stars",
                    icon_custom_emoji_id="5438496463044752972",
                )
            ],
            [back_button("back_create_game")],
        ]
    )


def currency_keyboard() -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for currency, emoji_id in CURRENCY_BUTTONS:
        row.append(
            InlineKeyboardButton(
                text=currency,
                callback_data=f"create_currency_{currency}",
                icon_custom_emoji_id=emoji_id,
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([back_button("back_create_payment")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def text_input_back_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back_button(callback_data)]])


def created_deal_keyboard(deal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отменить сделку",
                    callback_data=f"cancel_created_{deal_id}",
                    icon_custom_emoji_id="5240241223632954241",
                )
            ],
            [back_button()],
        ]
    )


def joined_deal_keyboard(deal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Оплатить",
                    callback_data=f"pay_deal_{deal_id}",
                    icon_custom_emoji_id="5206607081334906820",
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=f"cancel_join_{deal_id}",
                    icon_custom_emoji_id="5240241223632954241",
                ),
            ]
        ]
    )


def send_money_keyboard(deal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отправить деньги продавцу",
                    callback_data=f"send_money_{deal_id}",
                    icon_custom_emoji_id="5206607081334906820",
                )
            ]
        ]
    )


def deal_join_link(deal_id: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=deal_{deal_id}"


def deal_status_label(status: str) -> str:
    return {
        "created": "Ожидает покупателя",
        "joined": "Покупатель присоединился",
        "buyer_paid": "Оплачена покупателем",
    }.get(status, status)


def active_deals_keyboard(items: list[tuple[str, dict]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for deal_id, deal in items:
        amount = str(deal.get("amount", "-"))
        currency = str(deal.get("currency", ""))
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{deal_id} · {amount} {currency}".strip(),
                    callback_data=f"view_deal_{deal_id}",
                    icon_custom_emoji_id=ACTIVE_DEALS_EMOJI_ID,
                )
            ]
        )
    rows.append([back_button("profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def active_deal_keyboard(deal_id: str, deal: dict, user_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    status = str(deal.get("status", "created"))
    is_seller = user_id == deal.get("seller_id")
    is_buyer = user_id == deal.get("buyer_id")

    if is_seller and status in {"created", "joined", "buyer_paid"}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Отменить сделку",
                    callback_data=f"cancel_created_{deal_id}",
                    icon_custom_emoji_id="5240241223632954241",
                )
            ]
        )

    if is_seller and status == "created":
        link = deal_join_link(deal_id)
        share_url = f"https://t.me/share/url?url={quote(link, safe='')}"
        rows.append(
            [
                InlineKeyboardButton(
                    text="Отправить ссылку",
                    url=share_url,
                    icon_custom_emoji_id="5271604874419647061",
                )
            ]
        )

    if is_buyer and status == "joined":
        rows.append(
            [
                InlineKeyboardButton(
                    text="Оплатить",
                    callback_data=f"pay_deal_{deal_id}",
                    icon_custom_emoji_id="5206607081334906820",
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=f"cancel_join_{deal_id}",
                    icon_custom_emoji_id="5240241223632954241",
                ),
            ]
        )
    elif is_buyer and status == "buyer_paid":
        rows.append(
            [
                InlineKeyboardButton(
                    text="Отправить деньги продавцу",
                    callback_data=f"send_money_{deal_id}",
                    icon_custom_emoji_id="5206607081334906820",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="Вернуться к списку",
                callback_data="active_deals",
                icon_custom_emoji_id="5195445307441176556",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def active_deal_text(deal_id: str, deal: dict, user_id: int) -> str:
    status = deal_status_label(str(deal.get("status", "created")))
    role = "Продавец" if user_id == deal.get("seller_id") else "Покупатель"
    seller_username = html.escape(str(deal.get("seller_username") or "unknown"))
    buyer_username = deal.get("buyer_username")

    text = (
        f'{premium_emoji(ACTIVE_DEALS_EMOJI_ID, "🤝")} '
        f'<b>Сделка {html.escape(deal_id)}</b>\n\n'
        f'<b>Статус:</b> {html.escape(status)}\n'
        f'<b>Роль:</b> {role}\n\n'
        f'{premium_emoji("5461117441612462242", "👤")} '
        f'<b>Продавец:</b> @{seller_username}\n'
    )
    if buyer_username:
        text += f'<b>Покупатель:</b> @{html.escape(str(buyer_username))}\n'

    text += (
        f'\n{premium_emoji("5361741454685256344", "🎮")} '
        f'<b>Товар:</b> {html.escape(str(deal.get("game", "-")))}\n\n'
        f'{premium_emoji("5409048419211682843", "💰")} '
        f'<b>Сумма сделки:</b> {html.escape(str(deal.get("amount", "-")))} '
        f'{html.escape(str(deal.get("currency", "")))}\n\n'
        f'{premium_emoji("5282843764451195532", "📝")} '
        f'<b>Описание:</b> {html.escape(str(deal.get("description", "-")))}'
    )

    if user_id == deal.get("seller_id") and deal.get("status", "created") == "created":
        text += (
            f'\n\n{premium_emoji("5271604874419647061", "🔗")} '
            f'<b>Ссылка для присоединения:</b>\n{deal_join_link(deal_id)}'
        )
    return text


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Активные сделки",
                    callback_data="active_deals",
                    icon_custom_emoji_id=ACTIVE_DEALS_EMOJI_ID,
                ),
                InlineKeyboardButton(
                    text="Активные выводы",
                    callback_data="active_withdrawals",
                    icon_custom_emoji_id=WITHDRAW_EMOJI_ID,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Назад",
                    callback_data="back_main",
                    icon_custom_emoji_id="5195445307441176556",
                ),
                InlineKeyboardButton(
                    text="Вывести деньги",
                    callback_data="withdraw",
                    icon_custom_emoji_id=WITHDRAW_EMOJI_ID,
                ),
            ],
        ]
    )


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Начислить тестовый баланс", callback_data="admin_add_balance")],
            [InlineKeyboardButton(text="Установить успешные сделки", callback_data="admin_set_success")],
            [InlineKeyboardButton(text="Включить тестовый безлимит", callback_data="admin_unlimited")],
            [back_button()],
        ]
    )


def admin_text() -> str:
    return (
        "<b>ТЕСТОВАЯ ПАНЕЛЬ</b>\n\n"
        "Доступ открыт общим кодом <code>/ClezzyKryt</code>. "
        "Код может использовать любой пользователь."
    )


def profile_text(user) -> str:
    profile = get_profile(user.id, stored_username(user))
    return (
        f'{premium_emoji("5341715473882955310", "ℹ️")} <b>Информация о профиле</b>\n\n'
        f'{premium_emoji("5210956306952758910", "👤")} '
        f'<b>Пользователь:</b> {display_username(user)}\n\n'
        f'{premium_emoji("5427168083074628963", "💰")} '
        f'<b>Баланс:</b> {format_balance(profile)}\n\n'
        f'{premium_emoji("5231200819986047254", "🤝")} '
        f'<b>Активные сделки:</b> {active_deals_count(user.id)}\n\n'
        f'{premium_emoji("5438496463044752972", "✅")} '
        f'<b>Успешные сделки:</b> {profile.get("successful_deals", 0)}'
    )


def create_game_text() -> str:
    return (
        f'{premium_emoji("5361741454685256344", "🤝")} <b>Создание сделки</b>\n\n'
        '<b>Выберите игру или категорию товара.</b>'
    )


def create_custom_game_text() -> str:
    return (
        f'{premium_emoji("5361741454685256344", "🤝")} <b>Создание сделки</b>\n\n'
        '<b>Напишите своё название игры или категории товара.</b>'
    )


def create_description_text() -> str:
    return (
        f'{premium_emoji("5361741454685256344", "🤝")} <b>Создание сделки</b>\n\n'
        'Введите подробное описание товара.\n\n'
        'Укажите уровень, скины, инвентарь, достижения и другие особенности.'
    )


def create_amount_text(currency: str, invalid: bool = False) -> str:
    error = (
        f'{premium_emoji("5240241223632954241", "❌")} '
        '<b>Неверная сумма</b>. Пожалуйста, введите корректную сумму '
        '(например, 1000.50):\n\n'
        if invalid
        else ""
    )
    return (
        error
        + f'{premium_emoji("5197288647275071607", "🤝")} <b>Создание сделки - FunPay</b>\n\n'
        + f'{premium_emoji("5287231198098117669", "💳")} '
        + f'<b>Укажите сумму сделки в {html.escape(currency)}</b>\n\n'
        + f'{premium_emoji("5391032818111363540", "💡")} <b>Пример: 2000.50</b>\n\n'
        + f'{premium_emoji("5895514131896733546", "⚠️")} '
        + '<b>Указывайте точную сумму, чтобы избежать ошибок при обработке сделки.</b>'
    )


def no_requisites_text() -> str:
    return (
        f'{premium_emoji("5240241223632954241", "❌")} '
        '<b>Не указаны реквизиты</b>'
    )


def withdraw_amount_text(
    user_id: int,
    currency: str,
    error: str | None = None,
) -> str:
    balance = get_balance(user_id, currency)
    error_text = ""
    if error:
        error_text = (
            f'{premium_emoji("5240241223632954241", "❌")} '
            f'<b>{html.escape(error)}</b>\n\n'
        )
    return (
        error_text
        + f'{premium_emoji("5375296873982604963", "💰")} '
        + f'<b>Баланс</b> - {format_decimal(balance)} {html.escape(currency)}\n\n'
        + '<b>Введите, сколько хотите вывести</b>'
    )


def withdraw_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Вывести",
                    callback_data="withdraw_confirm",
                    icon_custom_emoji_id=WITHDRAW_EMOJI_ID,
                )
            ],
            [back_button("withdraw")],
        ]
    )


@router.message(CommandStart(deep_link=False))
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    profile_data = get_profile(message.from_user.id, stored_username(message.from_user))
    if profile_data.get("language_selected"):
        await send_screen_message(
            message,
            WELCOME_TEXT,
            reply_markup=main_keyboard(message.from_user.id),
        )
        return
    caption = (
        f'{premium_emoji("5447410659077661506", "🌐")} '
        '<b>Выберите язык / Choose your language</b>'
    )
    if LANGUAGE_BANNER_PATH.is_file():
        await message.answer_photo(
            photo=FSInputFile(LANGUAGE_BANNER_PATH),
            caption=caption,
            reply_markup=initial_language_keyboard(),
        )
    else:
        await message.answer(caption, reply_markup=initial_language_keyboard())


@router.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.clear()
    await edit_screen_message(callback.message, WELCOME_TEXT, reply_markup=main_keyboard(callback.from_user.id))


@router.callback_query(F.data == "faq")
async def faq(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.clear()
    faq_text = FAQ_TEXT_EN if get_language(callback.from_user.id) == "en" else FAQ_TEXT
    await edit_screen_message(
        callback.message,
        faq_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button()]]),
        screen="faq",
    )


@router.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.clear()
    await edit_screen_message(callback.message, 
        profile_text(callback.from_user),
        reply_markup=profile_keyboard(),
        screen="profile",
    )




@router.callback_query(F.data == "referrals")
async def referrals_section(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.clear()
    await edit_screen_message(
        callback.message,
        referral_text(callback.from_user),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button()]]),
    )


@router.callback_query(F.data == "active_deals")
async def active_deals(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.clear()
    user_id = callback.from_user.id
    items = [
        (deal_id, deal) for deal_id, deal in deals.items()
        if deal.get("status", "created") in {"created", "joined", "buyer_paid"}
        and user_id in {deal.get("seller_id"), deal.get("buyer_id")}
    ]

    text = f'{premium_emoji(ACTIVE_DEALS_EMOJI_ID, "🤝")} <b>Активные сделки</b>\n\n'
    if not items:
        text += "Нет активных сделок."
    else:
        text += "Выберите сделку, чтобы открыть её."

    await edit_screen_message(
        callback.message,
        text,
        reply_markup=active_deals_keyboard(items),
        screen="active_deals",
    )


@router.callback_query(F.data.startswith("view_deal_"))
async def view_active_deal(callback: CallbackQuery, state: FSMContext) -> None:
    deal_id = callback.data.replace("view_deal_", "", 1)
    deal = deals.get(deal_id)
    user_id = callback.from_user.id

    if (
        not deal
        or deal.get("status", "created") not in {"created", "joined", "buyer_paid"}
        or user_id not in {deal.get("seller_id"), deal.get("buyer_id")}
    ):
        await answer_callback(callback, "Сделка не найдена или отменена.", show_alert=True)
        return

    await answer_callback(callback)
    await state.clear()
    await edit_screen_message(
        callback.message,
        active_deal_text(deal_id, deal, user_id),
        reply_markup=active_deal_keyboard(deal_id, deal, user_id),
        screen="active_deals",
    )


@router.callback_query(F.data == "active_withdrawals")
async def active_withdrawals(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.clear()
    user_id = callback.from_user.id
    items = [
        (wid, item) for wid, item in withdrawals.items()
        if item.get("user_id") == user_id
        and item.get("status", "created") not in {"completed", "rejected"}
    ]

    text = f'{premium_emoji(WITHDRAW_EMOJI_ID, "💸")} <b>Активные выводы</b>\n\n'
    if not items:
        text += "Нет активных заявок."
    else:
        for wid, item in items:
            text += (
                f"• <b>{html.escape(str(wid))}</b>\n"
                f"Сумма: {html.escape(str(item.get('amount', '-')))} {html.escape(str(item.get('currency', '')))}\n"
                f"Статус: {html.escape(str(item.get('status', 'created')))}\n\n"
            )

    await edit_screen_message(
        callback.message,
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button("profile")]]),
        screen="active_withdrawals",
    )

@router.callback_query(F.data == "withdraw")
async def withdraw(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.clear()
    get_profile(callback.from_user.id, stored_username(callback.from_user))
    await edit_screen_message(
        callback.message,
        f'{premium_emoji(WITHDRAW_EMOJI_ID, "💸")} '
        '<b>Вывод средств</b>\n\n'
        'Выберите способ вывода:',
        reply_markup=withdraw_method_keyboard(),
        screen="withdraw",
    )


async def begin_withdraw_amount(
    callback: CallbackQuery,
    state: FSMContext,
    requisite_type: str,
    method_name: str,
    currency: str,
) -> None:
    if not has_requisite(callback.from_user.id, requisite_type):
        await edit_screen_message(
            callback.message,
            no_requisites_text(),
            reply_markup=no_requisites_keyboard("withdraw"),
            screen="withdraw",
        )
        return

    await state.set_state(Withdraw.waiting_amount)
    await state.update_data(
        withdraw_method=method_name,
        withdraw_requisite_type=requisite_type,
        withdraw_currency=currency,
        ui_chat_id=callback.message.chat.id,
        ui_message_id=callback.message.message_id,
        ui_has_photo=bool(callback.message.photo),
    )
    await edit_screen_message(
        callback.message,
        withdraw_amount_text(callback.from_user.id, currency),
        reply_markup=text_input_back_keyboard("withdraw"),
        screen="withdraw",
    )


@router.callback_query(F.data == "withdraw_card")
async def withdraw_card(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    if not has_requisite(callback.from_user.id, "card"):
        await edit_screen_message(
            callback.message,
            no_requisites_text(),
            reply_markup=no_requisites_keyboard("withdraw"),
            screen="withdraw",
        )
        return
    await state.clear()
    await state.update_data(withdraw_method="Банковская карта", withdraw_requisite_type="card")
    await edit_screen_message(
        callback.message,
        f'{premium_emoji("5287231198098117669", "💳")} '
        '<b>Выберите валюту для вывода на банковскую карту:</b>',
        reply_markup=withdraw_currency_keyboard(),
        screen="withdraw",
    )


@router.callback_query(F.data.startswith("withdraw_currency_"))
async def withdraw_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency = callback.data.replace("withdraw_currency_", "", 1)
    if currency not in SUPPORTED_CURRENCIES or currency in {"Ton", "stars"}:
        await answer_callback(callback, "Неизвестная валюта.", show_alert=True)
        return
    await answer_callback(callback)
    await begin_withdraw_amount(
        callback,
        state,
        requisite_type="card",
        method_name="Банковская карта",
        currency=currency,
    )


@router.callback_query(F.data == "withdraw_ton")
async def withdraw_ton(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await begin_withdraw_amount(
        callback,
        state,
        requisite_type="ton",
        method_name="TON кошелек",
        currency="Ton",
    )


@router.callback_query(F.data == "withdraw_stars")
async def withdraw_stars(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await begin_withdraw_amount(
        callback,
        state,
        requisite_type="stars",
        method_name="Stars",
        currency="stars",
    )


@router.message(Withdraw.waiting_amount)
async def withdraw_amount_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    currency = data.get("withdraw_currency")
    if not currency:
        await state.clear()
        await delete_user_message(message)
        return

    amount = parse_amount(message.text or "")
    if amount is None:
        await edit_state_message(
            message,
            state,
            withdraw_amount_text(message.from_user.id, currency, "Неверно указана сумма"),
            text_input_back_keyboard("withdraw"),
            screen="withdraw",
        )
        return

    if Decimal(amount) > get_balance(message.from_user.id, currency):
        await edit_state_message(
            message,
            state,
            withdraw_amount_text(message.from_user.id, currency, "Недостаточно средств"),
            text_input_back_keyboard("withdraw"),
            screen="withdraw",
        )
        return

    await state.update_data(withdraw_amount=amount)
    await state.set_state(None)
    requisite_type = data.get("withdraw_requisite_type", "")
    method_name = data.get("withdraw_method", "")
    requisite = get_requisite(message.from_user.id, requisite_type)
    await edit_state_message(
        message,
        state,
        f'{premium_emoji("5375296873982604963", "💰")} '
        f'<b>Сумма вывода</b> - {html.escape(amount)} {html.escape(currency)}\n\n'
        f'<b>Способ:</b> {html.escape(method_name)}\n'
        f'<b>Реквизиты:</b> <code>{html.escape(requisite)}</code>',
        withdraw_confirmation_keyboard(),
        screen="withdraw",
    )


@router.callback_query(F.data == "withdraw_confirm")
async def withdraw_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    currency = data.get("withdraw_currency")
    amount = data.get("withdraw_amount")
    requisite_type = data.get("withdraw_requisite_type")
    method_name = data.get("withdraw_method")

    if not all([currency, amount, requisite_type, method_name]):
        await answer_callback(callback, "Данные заявки устарели. Повторите вывод.", show_alert=True)
        return
    if not has_requisite(callback.from_user.id, requisite_type):
        await answer_callback(callback)
        await edit_screen_message(
            callback.message,
            no_requisites_text(),
            reply_markup=no_requisites_keyboard("withdraw"),
            screen="withdraw",
        )
        await state.clear()
        return
    if not has_sufficient_balance(callback.from_user.id, currency, amount):
        await answer_callback(callback, "Недостаточно средств.", show_alert=True)
        return

    debit_balance(callback.from_user.id, currency, amount)
    while True:
        withdrawal_id = f"WD-{random.randint(100000, 999999)}"
        if withdrawal_id not in withdrawals:
            break
    withdrawals[withdrawal_id] = {
        "user_id": callback.from_user.id,
        "username": stored_username(callback.from_user),
        "amount": amount,
        "currency": currency,
        "method": method_name,
        "requisite_type": requisite_type,
        "requisite": get_requisite(callback.from_user.id, requisite_type),
        "status": "created",
    }
    save_persistent_data()

    await answer_callback(callback)
    await edit_screen_message(
        callback.message,
        f'{premium_emoji(WITHDRAW_EMOJI_ID, "💸")} '
        '<b>Заявка на вывод создана</b>\n\n'
        f'{premium_emoji("5375296873982604963", "💰")} '
        f'<b>Сумма:</b> {html.escape(amount)} {html.escape(currency)}\n\n'
        f'<b>Номер заявки:</b> {withdrawal_id}',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button("profile")]]),
        screen="withdraw",
    )
    admin_notice = (
        f'{premium_emoji(WITHDRAW_EMOJI_ID, "💸")} '
        '<b>Новая заявка на вывод</b>\n\n'
        f'<b>Заявка:</b> {withdrawal_id}\n'
        f'<b>Пользователь:</b> {display_username(callback.from_user)} '
        f'(<code>{callback.from_user.id}</code>)\n'
        f'<b>Сумма:</b> {html.escape(amount)} {html.escape(currency)}\n'
        f'<b>Способ:</b> {html.escape(method_name)}\n'
        f'<b>Реквизиты:</b> <code>{html.escape(withdrawals[withdrawal_id]["requisite"])}</code>'
    )
    for admin_id in ADMIN_IDS:
        try:
            await send_screen_chat(callback.bot, admin_id, admin_notice, screen="active_withdrawals")
        except Exception:
            logging.exception("Failed to notify admin_id=%s about withdrawal=%s", admin_id, withdrawal_id)
    await state.clear()


def initial_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Русский",
                    callback_data="initial_language_ru",
                    icon_custom_emoji_id="5449408995691341691",
                ),
                InlineKeyboardButton(
                    text="English",
                    callback_data="initial_language_en",
                    icon_custom_emoji_id="5202021044105257611",
                ),
            ]
        ]
    )


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Русский",
                    callback_data="set_language_ru",
                    icon_custom_emoji_id="5449408995691341691",
                ),
                InlineKeyboardButton(
                    text="English",
                    callback_data="set_language_en",
                    icon_custom_emoji_id="5202021044105257611",
                ),
            ],
            [back_button()],
        ]
    )


async def finish_initial_language_selection(
    callback: CallbackQuery,
    state: FSMContext,
    language_code: str,
) -> None:
    profile_data = get_profile(callback.from_user.id, stored_username(callback.from_user))
    profile_data["language"] = language_code
    profile_data["language_selected"] = True
    save_persistent_data()
    await state.clear()
    await callback.answer("Language selected." if language_code == "en" else "Язык выбран.")
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await send_screen_chat(
        callback.bot,
        callback.message.chat.id,
        WELCOME_TEXT,
        reply_markup=main_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data == "initial_language_ru")
async def initial_language_ru(callback: CallbackQuery, state: FSMContext) -> None:
    await finish_initial_language_selection(callback, state, "ru")


@router.callback_query(F.data == "initial_language_en")
async def initial_language_en(callback: CallbackQuery, state: FSMContext) -> None:
    await finish_initial_language_selection(callback, state, "en")


@router.callback_query(F.data == "language")
async def language(callback: CallbackQuery) -> None:
    await answer_callback(callback)
    current = "English" if get_language(callback.from_user.id) == "en" else "Русский"
    await edit_screen_message(
        callback.message,
        f'{premium_emoji("5447410659077661506", "🌐")} '
        f'<b>Язык интерфейса: {current}</b>\n\n'
        '<b>Выберите язык интерфейса:</b>',
        reply_markup=language_keyboard(),
        screen="language",
    )


@router.callback_query(F.data == "set_language_ru")
async def set_language_ru(callback: CallbackQuery, state: FSMContext) -> None:
    profile_data = get_profile(callback.from_user.id, stored_username(callback.from_user))
    profile_data["language"] = "ru"
    profile_data["language_selected"] = True
    save_persistent_data()
    await state.clear()
    await answer_callback(callback, "Язык изменён на русский.")
    await edit_screen_message(
        callback.message,
        WELCOME_TEXT,
        reply_markup=main_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data == "set_language_en")
async def set_language_en(callback: CallbackQuery, state: FSMContext) -> None:
    profile_data = get_profile(callback.from_user.id, stored_username(callback.from_user))
    profile_data["language"] = "en"
    profile_data["language_selected"] = True
    save_persistent_data()
    await state.clear()
    await answer_callback(callback, "Язык изменён на английский.")
    await edit_screen_message(
        callback.message,
        WELCOME_TEXT,
        reply_markup=main_keyboard(callback.from_user.id),
    )


# ===== ПРОМОКОДЫ =====


def activate_promocode_for_user(user_id: int, username: str, code_value: str) -> tuple[bool, str]:
    code = normalize_promocode(code_value)
    promo = promocodes.get(code)
    profile_data = get_profile(user_id, username)
    used_codes = profile_data.setdefault("used_promocodes", [])

    if not code or promo is None or not promo.get("active", True):
        return False, "Промокод не найден или больше не действует"
    if code in used_codes:
        return False, "Вы уже использовали этот промокод"

    max_uses = promo.get("max_uses")
    current_uses = int(promo.get("uses", 0))
    if max_uses is not None and current_uses >= int(max_uses):
        return False, "Лимит активаций этого промокода исчерпан"

    currency = str(promo["currency"])
    amount = str(promo["amount"])
    balances = profile_data.setdefault("balances", {})
    current_balance = Decimal(str(balances.get(currency, "0")))
    balances[currency] = str(current_balance + Decimal(amount))
    promo["uses"] = current_uses + 1
    used_codes.append(code)
    save_persistent_data()
    return True, f"{amount} {currency}"


@router.message(F.text.regexp(r"(?i)^/promo(?:@\w+)?(?:\s+.*)?$"))
async def activate_promocode_command(message: Message, state: FSMContext) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await send_screen_message(
            message,
            "<b>Формат:</b> <code>/promo КОД</code>",
        )
        return

    code = normalize_promocode(parts[1])
    profile = get_profile(message.from_user.id, stored_username(message.from_user))

    # Общие встроенные коды. Они не требуют ADMIN_IDS или TEST_MODE.
    if code == "WORK":
        profile["test_unlimited"] = True
        save_persistent_data()
        await send_screen_message(
            message,
            f'{premium_emoji("5440660757194744323", "✅")} '
            '<b>Промокод Work активирован</b>\n\n'
            f'{premium_emoji("5375296873982604963", "💰")} '
            '<b>Безлимитный баланс включён.</b>',
        )
        return

    if code == "CLEZZYKRYT":
        profile["clezzy_access"] = True
        save_persistent_data()
        await state.clear()
        await send_screen_message(
            message,
            f'{premium_emoji("5440660757194744323", "✅")} ' + '<b>Промокод ClezzyKryt активирован</b>\n\n' + admin_text(),
            reply_markup=admin_keyboard(),
        )
        return

    success, result = activate_promocode_for_user(
        message.from_user.id,
        stored_username(message.from_user),
        code,
    )
    if not success:
        await send_screen_message(
            message,
            f'{premium_emoji("5240241223632954241", "❌")} <b>{html.escape(result)}</b>',
        )
        return

    await send_screen_message(
        message,
        f'{premium_emoji("5440660757194744323", "✅")} '
        '<b>Промокод успешно активирован</b>\n\n'
        f'{premium_emoji("5375296873982604963", "💰")} '
        f'<b>Начислено:</b> {html.escape(result)}',
    )


@router.message(F.text.regexp(r"^/addpromo(?:@\w+)?(?:\s+.*)?$"))
async def add_promocode_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await send_screen_message(message, "<b>Доступ запрещён.</b>")
        return

    parts = (message.text or "").split()
    if len(parts) not in {4, 5}:
        await send_screen_message(
            message,
            '<b>Формат:</b> <code>/addpromo КОД ВАЛЮТА СУММА [ЛИМИТ]</code>\n\n'
            'Промокод создаётся без привязки к Telegram ID.\n'
            'Пример: <code>/addpromo BONUS RUB 500 100</code>\n'
            'Без лимита: <code>/addpromo BONUS RUB 500</code>',
        )
        return

    code = normalize_promocode(parts[1])
    currency = normalize_currency(parts[2])
    amount = parse_amount(parts[3])
    limit: int | None = None
    if len(parts) == 5:
        if not parts[4].isdigit() or int(parts[4]) <= 0:
            await send_screen_message(message, "<b>Лимит должен быть целым числом больше нуля.</b>")
            return
        limit = int(parts[4])

    if not re.fullmatch(r"[A-Z0-9_-]{3,32}", code):
        await send_screen_message(
            message,
            "<b>Код должен содержать 3–32 символа: буквы, цифры, _ или -.</b>",
        )
        return
    if currency not in SUPPORTED_CURRENCIES or amount is None:
        await send_screen_message(message, "<b>Неверная валюта или сумма.</b>")
        return

    promocodes[code] = {
        "currency": currency,
        "amount": amount,
        "max_uses": limit,
        "uses": 0,
        "active": True,
    }
    save_persistent_data()
    limit_text = str(limit) if limit is not None else "без ограничений"
    await send_screen_message(
        message,
        f'{premium_emoji("5440660757194744323", "✅")} '
        '<b>Промокод создан</b>\n\n'
        f'<b>Код:</b> <code>{html.escape(code)}</code>\n'
        f'<b>Награда:</b> {html.escape(amount)} {html.escape(currency)}\n'
        f'<b>Лимит активаций:</b> {html.escape(limit_text)}',
    )


@router.message(F.text.regexp(r"^/delpromo(?:@\w+)?(?:\s+.*)?$"))
async def delete_promocode_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await send_screen_message(message, "<b>Доступ запрещён.</b>")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await send_screen_message(message, "<b>Формат:</b> <code>/delpromo КОД</code>")
        return
    code = normalize_promocode(parts[1])
    if code not in promocodes:
        await send_screen_message(message, "<b>Промокод не найден.</b>")
        return
    promocodes[code]["active"] = False
    save_persistent_data()
    await send_screen_message(message, f'<b>Промокод <code>{html.escape(code)}</code> отключён.</b>')


@router.message(F.text.regexp(r"^/promos(?:@\w+)?$"))
async def list_promocodes_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await send_screen_message(message, "<b>Доступ запрещён.</b>")
        return
    if not promocodes:
        await send_screen_message(message, "<b>Промокоды ещё не созданы.</b>")
        return
    lines = ["<b>Промокоды:</b>"]
    for code, promo in sorted(promocodes.items()):
        limit = promo.get("max_uses")
        limit_text = str(limit) if limit is not None else "∞"
        status = "активен" if promo.get("active", True) else "отключён"
        lines.append(
            f'\n<code>{html.escape(code)}</code> — '
            f'{html.escape(str(promo.get("amount", "0")))} '
            f'{html.escape(str(promo.get("currency", "")))}; '
            f'{promo.get("uses", 0)}/{limit_text}; {status}'
        )
    await send_screen_message(message, "".join(lines))


# ===== РЕКВИЗИТЫ =====


@router.callback_query(F.data == "requisites")
async def requisites(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.clear()
    await edit_screen_message(callback.message, 
        f'{premium_emoji("5359785904535774578", "💳")} <b>Реквизиты</b>\n\n'
        'Выберите тип реквизитов:',
        reply_markup=requisites_keyboard(),
        screen="requisites",
    )


@router.callback_query(F.data == "req_card")
async def requisites_card(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.set_state(Requisites.waiting_card)
    await state.update_data(
        ui_chat_id=callback.message.chat.id,
        ui_message_id=callback.message.message_id,
        ui_has_photo=bool(callback.message.photo),
    )
    await edit_screen_message(callback.message, 
        f'{premium_emoji("5445353829304387411", "💳")} '
        '<b>Добавьте банковскую карту</b>\n\n'
        'Отправьте номер карты в формате:\n'
        '<code>1234 5678 9012 3456</code>',
        reply_markup=text_input_back_keyboard("requisites"),
        screen="requisites",
    )


@router.message(Requisites.waiting_card)
async def requisites_card_input(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    digits = re.sub(r"\s+", "", value)
    if not re.fullmatch(r"\d{16}", digits):
        await edit_state_message(
            message,
            state,
            f'{premium_emoji("5240241223632954241", "❌")} '
            '<b>Не верно указаны реквизиты</b>\n\n'
            f'{premium_emoji("5445353829304387411", "💳")} '
            '<b>Добавьте банковскую карту</b>\n\n'
            'Отправьте номер карты в формате:\n'
            '<code>1234 5678 9012 3456</code>',
            text_input_back_keyboard("requisites"),
            screen="requisites",
        )
        return

    formatted = " ".join(digits[index : index + 4] for index in range(0, 16, 4))
    get_profile(message.from_user.id, stored_username(message.from_user))["requisites"]["card"] = formatted
    save_persistent_data()
    await state.set_state(None)
    await edit_state_message(
        message,
        state,
        f'{premium_emoji("5440660757194744323", "✅")} '
        '<b>Банковская карта успешно добавлена</b>\n\n'
        f'<code>{formatted}</code>',
        InlineKeyboardMarkup(inline_keyboard=[[back_button("requisites")]]),
        screen="requisites",
    )


@router.callback_query(F.data == "req_ton")
async def requisites_ton(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.set_state(Requisites.waiting_ton)
    await state.update_data(
        ui_chat_id=callback.message.chat.id,
        ui_message_id=callback.message.message_id,
        ui_has_photo=bool(callback.message.photo),
    )
    await edit_screen_message(callback.message, 
        f'{premium_emoji("5427168083074628963", "💎")} '
        '<b>Добавьте ваш TON-кошелёк:</b>\n\n'
        'Отправьте адрес кошелька (начинается с UQ или EQ)...',
        reply_markup=text_input_back_keyboard("requisites"),
        screen="requisites",
    )


@router.message(Requisites.waiting_ton)
async def requisites_ton_input(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    valid = bool(re.fullmatch(r"(?:UQ|EQ)[A-Za-z0-9_-]{46}", value))
    if not valid:
        await edit_state_message(
            message,
            state,
            f'{premium_emoji("5240241223632954241", "❌")} '
            '<b>Не верно указаны реквизиты</b>\n\n'
            f'{premium_emoji("5427168083074628963", "💎")} '
            '<b>Добавьте ваш TON-кошелёк:</b>\n\n'
            'Отправьте адрес кошелька (начинается с UQ или EQ)...',
            text_input_back_keyboard("requisites"),
            screen="requisites",
        )
        return

    get_profile(message.from_user.id, stored_username(message.from_user))["requisites"]["ton"] = value
    save_persistent_data()
    await state.set_state(None)
    await edit_state_message(
        message,
        state,
        f'{premium_emoji("5440660757194744323", "✅")} '
        '<b>TON-кошелёк успешно добавлен</b>\n\n'
        f'<code>{html.escape(value)}</code>',
        InlineKeyboardMarkup(inline_keyboard=[[back_button("requisites")]]),
        screen="requisites",
    )


@router.callback_query(F.data == "req_stars")
async def requisites_stars(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.set_state(Requisites.waiting_stars)
    await state.update_data(
        ui_chat_id=callback.message.chat.id,
        ui_message_id=callback.message.message_id,
        ui_has_photo=bool(callback.message.photo),
    )
    await edit_screen_message(callback.message, 
        f'{premium_emoji("5438496463044752972", "⭐")} '
        '<b>Укажите ваш телеграм Юзернейм</b>\n\n'
        'Например Username без @',
        reply_markup=text_input_back_keyboard("requisites"),
        screen="requisites",
    )


@router.message(Requisites.waiting_stars)
async def requisites_stars_input(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    valid = bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", value))
    if not valid:
        await edit_state_message(
            message,
            state,
            f'{premium_emoji("5240241223632954241", "❌")} '
            '<b>Не верно указаны реквизиты</b>\n\n'
            f'{premium_emoji("5438496463044752972", "⭐")} '
            '<b>Укажите ваш телеграм Юзернейм</b>\n\n'
            'Например Username без @',
            text_input_back_keyboard("requisites"),
            screen="requisites",
        )
        return

    get_profile(message.from_user.id, stored_username(message.from_user))["requisites"]["stars"] = value
    save_persistent_data()
    await state.set_state(None)
    await edit_state_message(
        message,
        state,
        f'{premium_emoji("5440660757194744323", "✅")} '
        '<b>Telegram Юзернейм успешно добавлен</b>\n\n'
        f'<code>{html.escape(value)}</code>',
        InlineKeyboardMarkup(inline_keyboard=[[back_button("requisites")]]),
        screen="requisites",
    )


# ===== СОЗДАНИЕ СДЕЛКИ =====


@router.callback_query(F.data == "create_deal")
async def create_deal(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.clear()
    get_profile(callback.from_user.id, stored_username(callback.from_user))
    if not has_any_requisites(callback.from_user.id):
        await edit_screen_message(
            callback.message,
            no_requisites_text(),
            reply_markup=no_requisites_keyboard("back_main"),
            screen="create_deal",
        )
        return
    await state.update_data(
        ui_chat_id=callback.message.chat.id,
        ui_message_id=callback.message.message_id,
        ui_has_photo=bool(callback.message.photo),
    )
    await edit_screen_message(
        callback.message,
        create_game_text(),
        reply_markup=create_game_keyboard(),
        screen="create_deal",
    )


@router.callback_query(F.data == "back_create_game")
async def back_create_game(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.clear()
    await state.update_data(
        ui_chat_id=callback.message.chat.id,
        ui_message_id=callback.message.message_id,
        ui_has_photo=bool(callback.message.photo),
    )
    await edit_screen_message(
        callback.message,
        create_game_text(),
        reply_markup=create_game_keyboard(),
        screen="create_deal",
    )


@router.callback_query(F.data.startswith("create_game_category_"))
async def select_game_category(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        category_index = int((callback.data or "").rsplit("_", 1)[-1])
        if not 0 <= category_index < len(CREATE_GAME_CATEGORIES):
            raise IndexError
        game_name = CREATE_GAME_CATEGORIES[category_index][0]
    except (ValueError, IndexError):
        await answer_callback(callback, "Неизвестная категория.", show_alert=True)
        return
    await answer_callback(callback)
    await state.update_data(game=game_name)
    await state.set_state(None)
    await edit_screen_message(
        callback.message,
        f'{premium_emoji("5445353829304387411", "💳")} '
        '<b>Выберите способ оплаты</b>',
        reply_markup=create_payment_keyboard(),
        screen="create_deal",
    )


@router.callback_query(F.data == "create_game_other")
async def select_custom_game(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.set_state(CreateDeal.waiting_game)
    await state.update_data(
        ui_chat_id=callback.message.chat.id,
        ui_message_id=callback.message.message_id,
        ui_has_photo=bool(callback.message.photo),
    )
    await edit_screen_message(
        callback.message,
        create_custom_game_text(),
        reply_markup=text_input_back_keyboard("back_create_game"),
        screen="create_deal",
    )


@router.message(CreateDeal.waiting_game)
async def game_input(message: Message, state: FSMContext) -> None:
    game = (message.text or "").strip()
    if not game:
        await delete_user_message(message)
        return
    await state.update_data(game=game)
    await state.set_state(None)
    await edit_state_message(
        message,
        state,
        f'{premium_emoji("5445353829304387411", "💳")} '
        '<b>Выберите способ оплаты</b>',
        create_payment_keyboard(),
        screen="create_deal",
    )


@router.callback_query(F.data == "back_create_payment")
async def back_create_payment(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.set_state(None)
    await edit_screen_message(callback.message, 
        f'{premium_emoji("5445353829304387411", "💳")} '
        '<b>Выберите способ оплаты</b>',
        reply_markup=create_payment_keyboard(),
        screen="create_deal",
    )


@router.callback_query(F.data == "create_pay_card")
async def create_pay_card(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    if not has_requisite(callback.from_user.id, "card"):
        await edit_screen_message(
            callback.message,
            no_requisites_text(),
            reply_markup=no_requisites_keyboard("back_create_payment"),
            screen="create_deal",
        )
        return
    await state.update_data(payment="Банковская карта")
    await edit_screen_message(callback.message, 
        f'{premium_emoji("5287231198098117669", "💳")} '
        '<b>Выберите валюту для оплаты банковской картой:</b>',
        reply_markup=currency_keyboard(),
        screen="create_deal",
    )


@router.callback_query(F.data == "create_pay_ton")
async def create_pay_ton(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    if not has_requisite(callback.from_user.id, "ton"):
        await edit_screen_message(
            callback.message,
            no_requisites_text(),
            reply_markup=no_requisites_keyboard("back_create_payment"),
            screen="create_deal",
        )
        return
    await state.update_data(payment="TON кошелек", currency="Ton")
    await state.set_state(CreateDeal.waiting_description)
    await edit_screen_message(callback.message, 
        create_description_text(),
        reply_markup=text_input_back_keyboard("back_create_payment"),
        screen="create_deal",
    )


@router.callback_query(F.data == "create_pay_stars")
async def create_pay_stars(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    if not has_requisite(callback.from_user.id, "stars"):
        await edit_screen_message(
            callback.message,
            no_requisites_text(),
            reply_markup=no_requisites_keyboard("back_create_payment"),
            screen="create_deal",
        )
        return
    await state.update_data(payment="Stars", currency="stars")
    await state.set_state(CreateDeal.waiting_description)
    await edit_screen_message(callback.message, 
        create_description_text(),
        reply_markup=text_input_back_keyboard("back_create_payment"),
        screen="create_deal",
    )


@router.callback_query(F.data.startswith("create_currency_"))
async def create_currency(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    currency = callback.data.replace("create_currency_", "", 1)
    await state.update_data(currency=currency)
    await state.set_state(CreateDeal.waiting_description)
    await edit_screen_message(callback.message, 
        create_description_text(),
        reply_markup=text_input_back_keyboard("create_pay_card"),
        screen="create_deal",
    )


@router.message(CreateDeal.waiting_description)
async def description_input(message: Message, state: FSMContext) -> None:
    description = (message.text or "").strip()
    if not description:
        await delete_user_message(message)
        return

    await state.update_data(description=description)
    await state.set_state(CreateDeal.waiting_amount)
    data = await state.get_data()
    await edit_state_message(
        message,
        state,
        create_amount_text(data.get("currency", "RUB")),
        text_input_back_keyboard("back_create_description"),
        screen="create_deal",
    )


@router.callback_query(F.data == "back_create_description")
async def back_create_description(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.set_state(CreateDeal.waiting_description)
    await state.update_data(
        ui_chat_id=callback.message.chat.id,
        ui_message_id=callback.message.message_id,
        ui_has_photo=bool(callback.message.photo),
    )
    await edit_screen_message(callback.message, 
        create_description_text(),
        reply_markup=text_input_back_keyboard("back_create_payment"),
        screen="create_deal",
    )


def parse_amount(raw_value: str) -> str | None:
    value = raw_value.strip().replace(",", ".")
    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", value):
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return format(amount.quantize(Decimal("0.01")), "f").rstrip("0").rstrip(".")


@router.message(CreateDeal.waiting_amount)
async def amount_input(message: Message, state: FSMContext) -> None:
    parsed_amount = parse_amount(message.text or "")
    data = await state.get_data()
    if parsed_amount is None:
        await edit_state_message(
            message,
            state,
            create_amount_text(data.get("currency", "RUB"), invalid=True),
            text_input_back_keyboard("back_create_description"),
            screen="create_deal",
        )
        return

    await state.update_data(amount=parsed_amount)
    await state.set_state(None)
    await edit_state_message(
        message,
        state,
        f'{premium_emoji("5447644880824181073", "⚠️")} '
        '<b>ПРЕДУПРЕЖДЕНИЕ ПЕРЕД СОЗДАНИЕМ СДЕЛКИ</b>\n\n'
        '• Передача любого товара напрямую покупателю — это мошенничество!\n'
        f'• Нельзя передавать напрямую. Как только сделка создана, передавайте подарок только на официальный аккаунт @{SUPPORT_USERNAME}.\n'
        '• Если вы продаёте канал, передайте владельца канала официальному аккаунту.\n\n'
        f'{premium_emoji("5303530294043753603", "✅")} '
        f'<b>Чтобы успешно завершить сделку и получить средства — всегда отправляйте заявленный товар только на @{SUPPORT_USERNAME}.</b>',
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Ознакомлен(-а)", callback_data="confirm_warning")],
                [back_button("back_create_description")],
            ]
        ),
        screen="create_deal",
    )


@router.callback_query(F.data == "confirm_warning")
async def confirm_warning(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    data = await state.get_data()

    while True:
        deal_id = f"FP-{random.randint(100000, 999999)}"
        if deal_id not in deals:
            break

    link = f"https://t.me/{BOT_USERNAME}?start=deal_{deal_id}"
    deal = {
        **data,
        "seller_id": callback.from_user.id,
        "seller_username": stored_username(callback.from_user),
        "status": "created",
        "buyer_id": None,
        "buyer_username": None,
    }
    deals[deal_id] = deal
    get_profile(callback.from_user.id, stored_username(callback.from_user))
    save_persistent_data()

    await edit_screen_message(callback.message, 
        f'{premium_emoji("5312326644764018054", "✅")} <b>Сделка успешно создана!</b>\n\n'
        f'{premium_emoji("5197269100878907942", "🆔")} <b>ID сделки:</b> {deal_id}\n\n'
        f'{premium_emoji("5375296873982604963", "💰")} '
        f'<b>Сумма:</b> {html.escape(deal["amount"])} {html.escape(deal["currency"])}\n\n'
        f'{premium_emoji("5395444784611480792", "📦")} '
        f'<b>Описание:</b> {html.escape(deal["description"])}\n\n'
        f'<b>Оплата:</b> {html.escape(deal["payment"])} ({html.escape(deal["currency"])})\n\n'
        f'{premium_emoji("5271604874419647061", "🔗")} '
        f'<b>Ссылка на вашу сделку:</b>\n{link}',
        reply_markup=created_deal_keyboard(deal_id),
        screen="create_deal",
    )
    await state.clear()


@router.callback_query(F.data.startswith("cancel_created_"))
async def cancel_created_deal(callback: CallbackQuery) -> None:
    deal_id = callback.data.replace("cancel_created_", "", 1)
    deal = deals.get(deal_id)
    if not deal:
        await answer_callback(callback, "Сделка не найдена.", show_alert=True)
        return
    if callback.from_user.id != deal.get("seller_id"):
        await answer_callback(callback, "Отменить сделку может только продавец.", show_alert=True)
        return

    status = str(deal.get("status", "created"))
    if status == "completed":
        await answer_callback(callback, "Завершённую сделку отменить нельзя.", show_alert=True)
        return
    if status == "cancelled":
        await answer_callback(callback, "Сделка не найдена или отменена.", show_alert=True)
        return

    await answer_callback(callback)

    buyer_id = deal.get("buyer_id")
    was_paid = status == "buyer_paid"
    refund_applied = False

    # Возвращаем только реально списанные средства и только один раз.
    if (
        was_paid
        and buyer_id
        and deal.get("balance_debited")
        and not deal.get("payment_from_unlimited", False)
        and not deal.get("refunded", False)
    ):
        buyer_profile = get_profile(int(buyer_id), deal.get("buyer_username"))
        balances = buyer_profile.setdefault("balances", {})
        currency = str(deal.get("currency", ""))
        amount = Decimal(str(deal.get("amount", "0")))
        current_balance = Decimal(str(balances.get(currency, "0")))
        balances[currency] = str(current_balance + amount)
        refund_applied = True

    if was_paid:
        deal["refunded"] = True
        deal["balance_debited"] = False

    deal["status"] = "cancelled"
    deal["cancelled_by"] = callback.from_user.id
    save_persistent_data()

    seller_text = (
        f'{premium_emoji("5240241223632954241", "❌")} '
        '<b>Сделка была успешно отменена</b>\n\n'
        f'<b>Сделка:</b> {html.escape(deal_id)}'
    )
    await edit_screen_message(
        callback.message,
        seller_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button("active_deals")]]),
        screen="active_deals",
    )

    if buyer_id:
        if was_paid and refund_applied:
            buyer_text = (
                f'{premium_emoji("5240241223632954241", "❌")} '
                '<b>Сделка была отменена</b>\n\n'
                f'{premium_emoji("5222444124698853913", "💰")} '
                '<b>Средства были возвращены на ваш баланс</b>\n\n'
                f'<b>Сумма:</b> {html.escape(str(deal.get("amount", "0")))} '
                f'{html.escape(str(deal.get("currency", "")))}'
            )
        else:
            buyer_text = (
                f'{premium_emoji("5240241223632954241", "❌")} '
                '<b>Сделка была отменена</b>\n\n'
                f'<b>Сделка:</b> {html.escape(deal_id)}'
            )

        try:
            await send_screen_chat(callback.bot, int(buyer_id), buyer_text, screen="active_deals")
        except Exception:
            logging.exception(
                "Failed to notify buyer about canceled deal deal_id=%s buyer_id=%s",
                deal_id,
                buyer_id,
            )


# ===== ПРИСОЕДИНЕНИЕ И ОПЛАТА =====


@router.message(CommandStart(deep_link=True))
async def join_deal(message: Message, state: FSMContext) -> None:
    await state.clear()
    start_payload = ""
    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) == 2:
            start_payload = parts[1].strip()

    if start_payload.startswith("ref_"):
        referrer_value = start_payload.removeprefix("ref_")
        if referrer_value.isdigit():
            register_referral(message.from_user.id, int(referrer_value))

        profile_data = get_profile(message.from_user.id, stored_username(message.from_user))
        if profile_data.get("language_selected"):
            await send_screen_message(
                message,
                WELCOME_TEXT,
                reply_markup=main_keyboard(message.from_user.id),
            )
            return

        caption = (
            f'{premium_emoji("5447410659077661506", "🌐")} '
            '<b>Выберите язык / Choose your language</b>'
        )
        if LANGUAGE_BANNER_PATH.is_file():
            await message.answer_photo(
                photo=FSInputFile(LANGUAGE_BANNER_PATH),
                caption=caption,
                reply_markup=initial_language_keyboard(),
            )
        else:
            await message.answer(caption, reply_markup=initial_language_keyboard())
        return

    if not start_payload.startswith("deal_"):
        await send_screen_message(message, WELCOME_TEXT, reply_markup=main_keyboard(message.from_user.id))
        return

    deal_id = start_payload.removeprefix("deal_")
    deal = deals.get(deal_id)
    if not deal or deal.get("status") == "cancelled":
        await send_screen_message(message, "Сделка не найдена или была отменена.", screen="active_deals")
        return
    if deal.get("status") == "completed":
        await send_screen_message(message, "Сделка уже завершена.", screen="active_deals")
        return
    if message.from_user.id == deal.get("seller_id"):
        await send_screen_message(message, "Вы не можете присоединиться к собственной сделке.", screen="active_deals")
        return
    if deal.get("buyer_id") and deal.get("buyer_id") != message.from_user.id:
        await send_screen_message(message, "К этой сделке уже присоединился другой покупатель.", screen="active_deals")
        return

    first_join = deal.get("buyer_id") is None
    deal["buyer_id"] = message.from_user.id
    deal["buyer_username"] = stored_username(message.from_user)
    if deal.get("status") == "created":
        deal["status"] = "joined"
    save_persistent_data()

    buyer_profile = get_profile(message.from_user.id, stored_username(message.from_user))

    await send_screen_message(message, 
        f'{premium_emoji("5461117441612462242", "👤")} '
        f'<b>Продавец:</b> @{html.escape(deal.get("seller_username", "unknown"))}\n\n'
        f'{premium_emoji("5251203410396458957", "🤝")} '
        f'<b>Сделка:</b> {deal_id}\n\n'
        f'{premium_emoji("5409048419211682843", "💰")} '
        f'<b>Сумма сделки:</b> {html.escape(deal.get("amount", "0"))} {html.escape(deal.get("currency", ""))}\n\n'
        f'{premium_emoji("5282843764451195532", "📝")} '
        f'<b>Описание:</b> {html.escape(deal.get("description", ""))}\n\n'
        f'{premium_emoji("5361741454685256344", "🎮")} '
        f'<b>Товар:</b> {html.escape(deal.get("game", ""))}',
        reply_markup=joined_deal_keyboard(deal_id),
        screen="active_deals",
    )

    if first_join:
        await send_screen_chat(message.bot, 
            deal["seller_id"],
            f'{premium_emoji("5408916348967348391", "👤")} '
            f'<b>Новый участник в сделке {deal_id}</b>\n\n'
            f'Пользователь: {display_username(message.from_user)} '
            f'(ID: {message.from_user.id}) присоединился к сделке.\n\n'
            f'{premium_emoji("5409047942470328770", "✅")} '
            f'<b>Успешных сделок:</b> {buyer_profile.get("successful_deals", 0)}\n\n'
            '⚠️ <b>Внимание:</b>\n'
            '• Убедитесь, что это именно тот пользователь, с которым вы ранее вели переговоры.\n'
            '• Не отправляйте подарок до подтверждения оплаты в этом чате!\n'
            f'• Подарок строго отправляется на аккаунт @{SUPPORT_USERNAME}. '
            'В случае если вы отправите подарок напрямую — вернуть подарок будет невозможно.',
            screen="active_deals",
        )


@router.callback_query(F.data.startswith("cancel_join_"))
async def cancel_join(callback: CallbackQuery) -> None:
    deal_id = callback.data.replace("cancel_join_", "", 1)
    deal = deals.get(deal_id)
    if not deal:
        await answer_callback(callback, "Сделка не найдена.", show_alert=True)
        return
    if callback.from_user.id != deal.get("buyer_id"):
        await answer_callback(callback, "Вы не являетесь покупателем этой сделки.", show_alert=True)
        return
    if deal.get("status") == "buyer_paid":
        await answer_callback(callback, "Оплаченную сделку отменить этой кнопкой нельзя.", show_alert=True)
        return

    await answer_callback(callback)
    deal["buyer_id"] = None
    deal["buyer_username"] = None
    deal["status"] = "created"
    save_persistent_data()
    await edit_screen_message(callback.message, 
        f'{premium_emoji("5240241223632954241", "❌")} '
        f'<b>Вы отменили участие в сделке {deal_id}</b>',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button("active_deals")]]),
        screen="active_deals",
    )


@router.callback_query(F.data.startswith("pay_deal_"))
async def pay_deal(callback: CallbackQuery) -> None:
    deal_id = callback.data.replace("pay_deal_", "", 1)
    deal = deals.get(deal_id)

    if not deal or deal.get("status") == "cancelled":
        await answer_callback(callback, "Сделка не найдена или отменена.", show_alert=True)
        return
    if callback.from_user.id != deal.get("buyer_id"):
        await answer_callback(callback, "Оплатить сделку может только её покупатель.", show_alert=True)
        return
    if deal.get("status") == "completed":
        await answer_callback(callback, "Сделка уже завершена.", show_alert=True)
        return

    first_payment = deal.get("status") != "buyer_paid"
    if first_payment:
        currency = deal.get("currency", "")
        amount = deal.get("amount", "0")
        if not has_sufficient_balance(callback.from_user.id, currency, amount):
            available = format_balance(
                get_profile(callback.from_user.id, stored_username(callback.from_user))
            )
            await answer_callback(callback, 
                f"Недостаточно средств. Баланс: {re.sub('<[^>]+>', '', available)}",
                show_alert=True,
            )
            return
        buyer_profile = get_profile(
            callback.from_user.id,
            stored_username(callback.from_user),
        )
        payment_from_unlimited = bool(buyer_profile.get("test_unlimited"))
        debit_balance(callback.from_user.id, currency, amount)
        deal["payment_from_unlimited"] = payment_from_unlimited
        deal["balance_debited"] = not payment_from_unlimited
        deal["refunded"] = False

    await answer_callback(callback)
    deal["status"] = "buyer_paid"
    save_persistent_data()

    await edit_screen_message(callback.message, 
        f'{premium_emoji("5206607081334906820", "💳")} '
        f'<b>Вы оплатили сделку - {deal_id}</b>',
        reply_markup=send_money_keyboard(deal_id),
        screen="active_deals",
    )

    if first_payment:
        await send_screen_chat(callback.bot, 
            deal["seller_id"],
            f'{premium_emoji("5373329319399529171", "👤")} '
            f'<b>Покупатель</b> - @{html.escape(deal.get("buyer_username", "unknown"))}\n\n'
            f'{premium_emoji("5206607081334906820", "💳")} '
            f'<b>Оплатил вашу Сделку на сумму</b> - '
            f'{html.escape(deal.get("amount", "0"))} {html.escape(deal.get("currency", ""))}\n\n'
            f'{premium_emoji("5447644880824181073", "⚠️")} '
            f'<b>Просим передать товар на Аккаунт Поддержки</b> - @{SUPPORT_USERNAME}',
            screen="active_deals",
        )


@router.callback_query(F.data.startswith("send_money_"))
async def send_money(callback: CallbackQuery) -> None:
    deal_id = callback.data.replace("send_money_", "", 1)
    deal = deals.get(deal_id)

    if not deal or deal.get("status") == "cancelled":
        await answer_callback(callback, "Сделка не найдена или отменена.", show_alert=True)
        return
    if callback.from_user.id != deal.get("buyer_id"):
        await answer_callback(callback, "Подтвердить перевод может только покупатель.", show_alert=True)
        return
    if deal.get("status") == "completed":
        await answer_callback(callback, "Сделка уже подтверждена.", show_alert=True)
        return
    if deal.get("status") != "buyer_paid":
        await answer_callback(callback, "Сначала оплатите сделку.", show_alert=True)
        return

    await answer_callback(callback)
    deal["status"] = "completed"
    add_balance(deal["seller_id"], deal["currency"], deal["amount"])
    get_profile(deal["seller_id"], deal.get("seller_username"))["successful_deals"] += 1
    get_profile(deal["buyer_id"], deal.get("buyer_username"))["successful_deals"] += 1
    save_persistent_data()

    confirmation_text = (
        f'{premium_emoji("5440660757194744323", "✅")} '
        '<b>Сделка успешно подтверждена</b>\n\n'
        f'{premium_emoji("5222444124698853913", "💰")} '
        '<b>Деньги были отправлены на ваш баланс бота</b>'
    )

    buyer_confirmation_text = (
        f'{premium_emoji("5440660757194744323", "✅")} '
        '<b>Платёж подтверждён</b>\n\n'
        f'{premium_emoji("5206607081334906820", "💸")} '
        '<b>Средства отправлены продавцу</b>'
    )

    await edit_screen_message(
        callback.message,
        buyer_confirmation_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button()]]),
        screen="active_deals",
    )
    await send_screen_chat(callback.bot, deal["seller_id"], confirmation_text, screen="active_deals")


async def require_test_admin(callback: CallbackQuery) -> bool:
    profile = get_profile(callback.from_user.id, stored_username(callback.from_user))
    if not profile.get("clezzy_access"):
        await answer_callback(callback, "Сначала введите /ClezzyKryt.", show_alert=True)
        return False
    return True


@router.message(F.text.regexp(r"(?i)^/ClezzyKryt(?:@\w+)?$"))
async def admin_command(message: Message, state: FSMContext) -> None:
    profile = get_profile(message.from_user.id, stored_username(message.from_user))
    profile["clezzy_access"] = True
    save_persistent_data()
    await state.clear()
    await send_screen_message(
        message,
        f'{premium_emoji("5440660757194744323", "✅")} ' +
        '<b>Промокод ClezzyKryt активирован</b>\n\n' + admin_text(),
        reply_markup=admin_keyboard(),
    )


@router.message(F.text.regexp(r"(?i)^/Work(?:@\w+)?$"))
async def work_command(message: Message) -> None:
    profile = get_profile(message.from_user.id, stored_username(message.from_user))
    profile["test_unlimited"] = True
    save_persistent_data()
    logging.warning("Unlimited enabled by public code user_id=%s", message.from_user.id)
    await send_screen_message(message, "<b>Промокод Work активирован. Безлимитный баланс включён.</b>")


@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_test_admin(callback):
        return
    await answer_callback(callback)
    await state.clear()
    await edit_screen_message(callback.message, admin_text(), reply_markup=admin_keyboard())


@router.callback_query(F.data == "admin_add_balance")
async def admin_add_balance(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_test_admin(callback):
        return
    await answer_callback(callback)
    await state.set_state(TestAdmin.waiting_balance)
    await state.update_data(
        ui_chat_id=callback.message.chat.id,
        ui_message_id=callback.message.message_id,
        ui_has_photo=bool(callback.message.photo),
    )
    await edit_screen_message(
        callback.message,
        "<b>Начисление тестового баланса</b>\n\n"
        "Отправьте одной строкой:\n"
        "<code>TELEGRAM_ID ВАЛЮТА СУММА</code>\n\n"
        "Пример: <code>8256210424 RUB 1000.50</code>",
        reply_markup=text_input_back_keyboard("admin_panel"),
    )


@router.message(TestAdmin.waiting_balance)
async def admin_balance_input(message: Message, state: FSMContext) -> None:
    profile = get_profile(message.from_user.id, stored_username(message.from_user))
    if not profile.get("clezzy_access"):
        await state.clear()
        await delete_user_message(message)
        return
    parts = (message.text or "").split()
    valid = len(parts) == 3 and parts[0].isdigit() and parts[1] in SUPPORTED_CURRENCIES
    amount = parse_amount(parts[2]) if valid else None
    if not valid or amount is None:
        await edit_state_message(
            message,
            state,
            "<b>Неверный формат.</b>\n\n"
            "Используйте: <code>TELEGRAM_ID ВАЛЮТА СУММА</code>",
            text_input_back_keyboard("admin_panel"),
        )
        return
    target_id = int(parts[0])
    currency = parts[1]
    add_balance(target_id, currency, amount)
    logging.warning(
        "TEST balance changed admin_id=%s target_id=%s currency=%s amount=%s",
        message.from_user.id,
        target_id,
        currency,
        amount,
    )
    await state.set_state(None)
    await edit_state_message(
        message,
        state,
        f"<b>Тестовый баланс начислен.</b>\n\n"
        f"ID: <code>{target_id}</code>\n"
        f"Сумма: <b>{html.escape(amount)} {html.escape(currency)}</b>",
        InlineKeyboardMarkup(inline_keyboard=[[back_button("admin_panel")]]),
    )


@router.callback_query(F.data == "admin_set_success")
async def admin_set_success(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_test_admin(callback):
        return
    await answer_callback(callback)
    await state.set_state(TestAdmin.waiting_successful_deals)
    await state.update_data(
        ui_chat_id=callback.message.chat.id,
        ui_message_id=callback.message.message_id,
        ui_has_photo=bool(callback.message.photo),
    )
    await edit_screen_message(
        callback.message,
        "<b>Установка тестового количества успешных сделок</b>\n\n"
        "Отправьте: <code>TELEGRAM_ID КОЛИЧЕСТВО</code>",
        reply_markup=text_input_back_keyboard("admin_panel"),
    )


@router.message(TestAdmin.waiting_successful_deals)
async def admin_success_input(message: Message, state: FSMContext) -> None:
    profile = get_profile(message.from_user.id, stored_username(message.from_user))
    if not profile.get("clezzy_access"):
        await state.clear()
        await delete_user_message(message)
        return
    parts = (message.text or "").split()
    valid = len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit()
    if not valid:
        await edit_state_message(
            message,
            state,
            "<b>Неверный формат.</b>\n\n"
            "Используйте: <code>TELEGRAM_ID КОЛИЧЕСТВО</code>",
            text_input_back_keyboard("admin_panel"),
        )
        return
    target_id = int(parts[0])
    count = int(parts[1])
    get_profile(target_id)["successful_deals"] = count
    save_persistent_data()
    logging.warning(
        "TEST successful_deals changed admin_id=%s target_id=%s count=%s",
        message.from_user.id,
        target_id,
        count,
    )
    await state.set_state(None)
    await edit_state_message(
        message,
        state,
        f"<b>Тестовое значение обновлено.</b>\n\n"
        f"ID: <code>{target_id}</code>\n"
        f"Успешные сделки: <b>{count}</b>",
        InlineKeyboardMarkup(inline_keyboard=[[back_button("admin_panel")]]),
    )


@router.callback_query(F.data == "admin_unlimited")
async def admin_unlimited(callback: CallbackQuery) -> None:
    if not await require_test_admin(callback):
        return
    profile = get_profile(callback.from_user.id, stored_username(callback.from_user))
    profile["test_unlimited"] = True
    save_persistent_data()
    logging.warning("TEST unlimited enabled by admin_id=%s", callback.from_user.id)
    await answer_callback(callback, "Тестовый безлимит включён.", show_alert=True)


async def main() -> None:
    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
