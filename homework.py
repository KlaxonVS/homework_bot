from http import HTTPStatus
import logging
import os
import sys
import time

import requests
import telegram
from telegram.ext import CommandHandler, Updater

from dotenv import load_dotenv

from exception import (UnexpectedHTTPStatusCodeError,
                       UnexpectedTypeError,
                       UnexpectedStatus,)

load_dotenv()


logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%d-%m-%y %H:%M:%S',
)
handler.setFormatter(formatter)


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CURRENT_TIME = int(time.time())

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

CUSTOM_EXCEPTIONS = (
    UnexpectedHTTPStatusCodeError,
    UnexpectedTypeError,
    UnexpectedStatus,
)

ERROR_CACHE = []

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot: telegram.Bot,
                 message: str,) -> None:
    """Отправляет сообщение в Telegram чат."""
    bot.send_message(TELEGRAM_CHAT_ID, text=message)
    logger.info(f'Новое сообщение в чате: {message}')


def i_am_working(update, context) -> None:
    """Реакция на команду /start и вывод команд."""
    buttons = [['/start', '/clear_error_cache']]
    keyboard = telegram.ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    chat = update.effective_chat
    context.bot.send_message(chat.id, 'Я не сплю.', reply_markup=keyboard)
    logger.info('Проверил, что в сети')


def get_api_answer(current_timestamp: int) -> requests:
    """Получает ответ API и проверяет на корректность."""
    timestamp = current_timestamp
    params = {'from_date': timestamp}
    response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    if response.status_code == HTTPStatus.OK:
        return response.json()
    else:
        logger.exception(f'Ошибка при запросе к эндпоинту {ENDPOINT}.')
        message = (
            f'Ожидаемый ответ сервера: {HTTPStatus.OK}. '
            f'Полученный ответ: {response.status_code}'
        )
        raise UnexpectedHTTPStatusCodeError(message)


def check_response(response: dict) -> list:
    """Проверяет ответ API на корректность."""
    if type(response['homeworks']) is list:
        return response['homeworks']
    else:
        message = (
            'От сервера не пришли необходимые данные в формате list.'
            f'Пришел {type(response["homeworks"])}'
        )
        logger.error(message)
        raise UnexpectedTypeError(message)


def parse_status(homework: dict) -> str:
    """Подготавливает сообщение со статусом работы."""
    homework_name = homework['homework_name']
    homework_status = homework['status']
    if homework_status in HOMEWORK_STATUSES:
        verdict = HOMEWORK_STATUSES[homework_status]
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    elif homework_status not in HOMEWORK_STATUSES:
        message = f'Пришел неизвестный статус работы: {homework_status}'
        logger.error(message)
        raise UnexpectedStatus(message)
    elif homework_status is None:
        message = 'Статус работы отсутствует'
        logger.error(message)
        raise UnexpectedStatus(message)


def check_tokens() -> bool:
    """Проверяет доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def exception_check(error: str) -> bool:
    """Проверяет, что ошибка не повторяется и заносит ее в список."""
    if error not in ERROR_CACHE:
        ERROR_CACHE.append(error)
        return True
    else:
        return False


def clear_error_cache(update, context) -> None:
    """Очищает список ошибок."""
    ERROR_CACHE.clear()
    chat = update.effective_chat
    context.bot.send_message(chat.id, 'Кэш очищен')
    logger.info('Кэш очищен')


def main():
    """Основная логика работы бота."""
    updater = Updater(token=TELEGRAM_TOKEN)
    updater.dispatcher.add_handler(CommandHandler('start', i_am_working))
    updater.dispatcher.add_handler(CommandHandler('clear_error_cache',
                                                  clear_error_cache))
    updater.start_polling()
    updater.idle()
    if check_tokens():
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        current_timestamp = int(time.time())
        while True:
            try:
                update_time = current_timestamp - RETRY_TIME
                response = get_api_answer(update_time)
                homeworks = check_response(response)
                if homeworks:
                    homework = homeworks[0]
                    message = parse_status(homework)
                    send_message(bot, message)
                else:
                    logger.debug('Обновлений нет')
            except Exception as error:
                message = f'Сбой в работе программы: {error}'
                logger.error(message)
                if exception_check(str(error)):
                    send_message(bot, message)
            finally:
                time.sleep(RETRY_TIME)
    else:
        logger.critical('Переменные-токены недоступны в окружении')
        time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
