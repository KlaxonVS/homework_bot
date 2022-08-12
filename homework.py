from http import HTTPStatus
import logging.config
import os
import sys
import time

import requests
import telegram

from dotenv import load_dotenv

from exception import (EmptyResponse,
                       ErrorNotToSend,
                       SendMessageFailed,
                       UnexpectedHTTPStatusCodeError,)

load_dotenv()

BASE_DIR = os.path.dirname(__file__)

logging.config.fileConfig('main_logger.config',
                          defaults={'logfilename': f'{BASE_DIR}/bot_log.log'})

logger = logging.getLogger(__name__)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
ERROR_TOKEN = '9Rr0я'

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot: telegram.Bot,
                 message: str,) -> None:
    """Отправляет сообщение в Telegram чат."""
    logger.info('Попытка отправить сообщение в чат')
    try:
        bot.send_message(TELEGRAM_CHAT_ID, text=message)
        logger.info(f'Новое сообщение в чате: {message}')
    except telegram.TelegramError as error:
        logger.error(
            'Попытка отправить сообщение об ошибке не удалась'
            f'{type(error).__name__}: {error}'
        )
    except Exception as error:
        message = f'Не удалось отправить сообщение: {error}'
        raise SendMessageFailed(message)


def get_api_answer(current_time: int) -> requests:
    """Получает ответ API и проверяет на корректность."""
    logger.info('Попытка запроса к API')
    timestamp = current_time or time.time()
    params = {'from_date': timestamp}
    api_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': params,
    }
    try:
        logger.info('Запрос к API')
        response = requests.get(**api_params)
        if response.status_code == HTTPStatus.OK:
            logger.info(f'Запрос к API прошел успешно: {response.status_code}')
            return response.json()
        else:
            logger.exception(f'Ошибка при запросе к эндпоинту {ENDPOINT}.')
            message = (
                f'Ожидаемый ответ: {HTTPStatus.OK}. '
                f'Полученный: {response.status_code} {response.reason}\n'
            )
            raise UnexpectedHTTPStatusCodeError(message)
    except ConnectionError as error:
        message = (f'{error}'', переданные переменные:\n'
                   '{url}\nAuthorization: {headers[Authorization]:.5}\n'
                   '{params}')
        raise ConnectionError(message)


def check_response(response: dict) -> list:
    """Проверяет ответ API на корректность."""
    logger.info('Проверка ответа API на корректность - содержит list')
    if not isinstance(response, dict):
        message = (
            'От сервера не пришли необходимые данные в формате dict.'
            f'Пришел {type(response)}'
        )
        raise TypeError(message)
    if not isinstance(response.get('homeworks'), list):
        received_data = response.get('homeworks')
        message = (
            'От сервера не пришли необходимые данные в формате list.'
            f'Пришел {type(received_data)}'
        )
        raise TypeError(message)
    if 'homeworks' not in response:
        message = ('Ответ не содержит домашних работ.'
                   f'Пришло: {response}')
        raise EmptyResponse(message)
    logger.info('Проверка пройдена')
    return response.get('homeworks')


def parse_status(homework: dict) -> str:
    """Подготавливает сообщение со статусом работы."""
    homework_name = homework.get('homework_name')
    status = homework.get('status')
    if not homework_name:
        message = (
            'Пришел ответ с отсутствующем именем.\n'
            f'Имя работы: "{homework_name}"'
        )
        raise KeyError(message)
    if status not in VERDICTS:
        message = (
            'Пришел ответ с неизвестным, отсутствующем статусом работы\n'
            f'Статус работы: {status}'
        )
        raise NameError(message)
    return (
        'Изменился статус проверки работы "{homework_name}". {verdict}'
        .format(homework_name=homework_name, verdict=VERDICTS[status])
    )


def check_tokens() -> bool:
    """Проверяет доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def main():
    """Основная логика работы бота."""
    current_time = int(time.time())
    prev_report = {}
    current_report = {}
    if not check_tokens():
        message = 'Переменные-токены недоступны в окружении'
        logger.critical(message)
        sys.exit(message)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    while True:
        try:
            response = get_api_answer(current_time)
            homeworks = check_response(response)
            if homeworks:
                homework = homeworks[0]
                message = parse_status(homework)
                current_report['message'] = message
            else:
                logger.debug('Обновлений нет')
            if current_report != prev_report:
                logger.debug('Получен новый статус')
                prev_report = current_report.copy()
                current_time = int(time.time())
                send_message(bot, message)
            else:
                logger.debug('Обновлений нет')
        except ErrorNotToSend as error:
            message = f'{type(error).__name__}: {error}'
            logger.error(message)
        except Exception as error:
            message = f'{type(error).__name__}: {error}. {ERROR_TOKEN}'
            current_report['message'] = message
            logger.error(message)
            if current_report != prev_report:
                prev_report = current_report.copy()
                send_message(bot, message)
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
