from http import HTTPStatus
import logging.config
import os
import sys
import time

import requests
import telegram

from dotenv import load_dotenv

from exception import (ErrorToSend,
                       ErrorNotToSend,
                       SendMessageFailed,
                       UnexpectedHTTPStatusCodeError,
                       UnexpectedTypeError,)

load_dotenv()

BASE_DIR = os.path.dirname(__file__)

logging.config.fileConfig('main_logger.config',
                          defaults={'logfilename': f'{BASE_DIR}/bot_log.log'})

logger = logging.getLogger(__name__)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CURRENT_TIME = int(time.time())

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/1'
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
    except Exception as error:
        message = f'Не удалось отправить сообщение: {error}'
        logger.error(message)
        raise SendMessageFailed(message)


def get_api_answer(set_timestamp: int) -> requests:
    """Получает ответ API и проверяет на корректность."""
    logger.info('Попытка запроса к API')
    timestamp = set_timestamp or CURRENT_TIME
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
        logger.error(message)
        raise ConnectionError(message)


def check_response(response: dict) -> list:
    """Проверяет ответ API на корректность."""
    logger.info('Проверка ответа API на корректность - содержит list')
    if isinstance(response['homeworks'], list):
        logger.info('Проверка пройдена')
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
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    try:
        verdict = VERDICTS[homework_status]
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    except KeyError:
        message = ('Пришел ответ с неизвестным статусом работы '
                   f'или он отсутствует:\nИмя работы: "{homework_name}"\n'
                   f'Статус работы: {homework_status}')
        logger.warning(message)
        raise KeyError(message)


def check_tokens() -> bool:
    """Проверяет доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def main():
    """Основная логика работы бота."""
    error_cache = {}
    if not check_tokens():
        message = 'Переменные-токены недоступны в окружении'
        logger.critical(message)
        sys.exit(message)
    else:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        prev_report = {}
        try:
            # Получается что в get_api_answer для получения результата,
            # а не только проверки, мы должны задавать не настоящее время,
            # ведь придёд пустой список, а задать дату
            # от которой прислать обновление и так как у нас запрос идет через
            # промежуток RETRY_TIME, то его я и выбрал
            response = get_api_answer(CURRENT_TIME - RETRY_TIME)
            homeworks = check_response(response)
            if homeworks:
                homework = homeworks[0]
                current_report = {}
                current_report.update(
                    {homework.get('date_updated'):
                     [homework.get('homework_name'), homework.get('status')]}
                )
                # Имя и статус могут повторяться, а дата обновления нет,
                # потому её добавил, ведь это самый уникальный показатель
                # Особенно, если дату задать как 0 или давнюю дату
                if current_report != prev_report:
                    logger.debug('Получен новый статус')
                    prev_report.clear()
                    prev_report = current_report.copy()
                    message = parse_status(homework)
                    send_message(bot, message)
                else:
                    logger.debug('Обновлений нет')
            else:
                logger.debug('Обновлений нет')
        except ErrorToSend as error:
            message = f'{type(error).__name__}: {error}'
            current_error = {}
            current_error.update(
                {'message': message}
            )
            logger.error(message)
            if current_error != error_cache:
                error_cache = error_cache.copy()
                send_message(bot, message)
        except (Exception, ErrorNotToSend) as error:
            message = f'{type(error).__name__}: {error}'
            logger.error(message)
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
