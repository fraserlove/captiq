import logging
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_dir


@dataclass
class Config:
    strict: bool = True
    cache_file: Path = Path(user_cache_dir()) / 'captiq' / 'securities.yaml'
    include_fx_fees: bool = True
    log_level: int = logging.INFO

    @property
    def logging_enabled(self) -> bool:
        return self.log_level != logging.CRITICAL


config = Config()
