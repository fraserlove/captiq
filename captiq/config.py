import logging
import platformdirs
from dataclasses import dataclass

@dataclass
class Config:
    strict: bool = True
    include_fx_fees: bool = True
    log_level: int = logging.INFO
    cache: str = f'{platformdirs.user_cache_dir()}/captiq/securities.yaml'

config = Config()