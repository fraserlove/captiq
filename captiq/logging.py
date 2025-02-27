import logging
import logging.config

from captiq.config import config

logger = logging.getLogger('default')

class CustomFormatter(logging.Formatter):
    CSI = '\033['
    BRIGHT_CYAN = f'{CSI}96m'
    BOLD_WHITE = f'{CSI}1;37m'
    BRIGHT_YELLOW = f'{CSI}93m'
    RED = f'{CSI}31m'
    BOLD_RED = f'{CSI}1;31m'
    RESET = f'{CSI}0m'

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        fmt = kwargs.get('fmt', '{message}')

        self.formats = {
            logging.DEBUG: f'{self.BRIGHT_CYAN}{fmt}{self.RESET}',
            logging.INFO: f'{self.BOLD_WHITE}{fmt}{self.RESET}',
            logging.WARNING: f'{self.BRIGHT_YELLOW}{fmt}{self.RESET}',
            logging.ERROR: f'{self.RED}{fmt}{self.RESET}',
            logging.CRITICAL: f'{self.BOLD_RED}{fmt}{self.RESET}',
        }

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self.formats.get(record.levelno)
        formatter = logging.Formatter(log_fmt, style='{')
        return formatter.format(record)


def configure_logger() -> None:
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                '()': CustomFormatter,
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
