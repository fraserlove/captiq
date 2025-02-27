from typing import Optional

class ISIN(str):
    def __new__(cls, value: str) -> 'ISIN':
        return super().__new__(cls, value)

class Ticker(str):
    def __new__(cls, value: Optional[str] = None) -> Optional['Ticker']:
        if not value:
            return None
        return super().__new__(cls, value)

class Year(int):
    def __new__(cls, value: Optional[int] = None) -> Optional['Year']:
        if not value:
            return None
        return super().__new__(cls, value)