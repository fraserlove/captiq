import logging
import logging.config

from captiq.config import config

logger = logging.getLogger('default')

CSI = '\033['
RESET = f'{CSI}0m'
BOLD = f'{CSI}1m'
WHITE = f'{CSI}37m'
RED = f'{CSI}91m'
YELLOW = f'{CSI}93m'
BLUE = f'{CSI}94m'

class Formatter(logging.Formatter):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        fmt = kwargs.get('fmt', '{message}')

        self.formats = {
            logging.DEBUG: f'{BLUE}{fmt}{RESET}',
            logging.INFO: f'{BOLD}{WHITE}{fmt}{RESET}',
            logging.WARNING: f'{YELLOW}{fmt}{RESET}',
            logging.ERROR: f'{RED}{fmt}{RESET}',
            logging.CRITICAL: f'{BOLD}{RED}{fmt}{RESET}',
        }

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self.formats.get(record.levelno)
        formatter = logging.Formatter(log_fmt, style='{')
        return formatter.format(record)


def raise_or_warn(e: Exception) -> None:
    if config.strict:
        raise e
    logger.warning(e)

def configure_logger() -> None:
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                '()': Formatter,
                'format': '{levelname} | {message}',
                'style': '{',
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
            },
        },
        'root': {
            'handlers': ['console'],
            'level': config.log_level,
        }
    })
