from datetime import date, datetime, timezone

from captiq.types import Year

'''
Minimum timestamp for an order. Different rules apply on orders made before 6 April 2008.
See: https://www.gov.uk/hmrc-internal-manuals/capital-gains-manual/cg51570
'''
MIN_TIMESTAMP = datetime(2008, 4, 6, tzinfo=timezone.utc)

class TaxYear:
    START_MONTH = MIN_TIMESTAMP.month
    START_DAY = MIN_TIMESTAMP.day
    
    @classmethod
    def current(cls) -> Year:
        ''' Return the current tax year. '''
        now = datetime.now()
        if now.month < cls.START_MONTH or (now.month == cls.START_MONTH and now.day < cls.START_DAY):
            return Year(now.year - 1)
        return Year(now.year)
    
    @classmethod
    def period(cls, tax_year: Year) -> tuple[date, date]:
        ''' Return the start and end dates for a given tax year. '''
        start = date(tax_year, cls.START_MONTH, cls.START_DAY)
        end = date(tax_year + 1, cls.START_MONTH, cls.START_DAY - 1)
        return start, end
    
    @classmethod
    def from_date(cls, d: date) -> Year:
        ''' Return the tax year for a given date. '''
        return Year(d.year if d >= date(d.year, cls.START_MONTH, cls.START_DAY) else d.year - 1)
    
    @classmethod
    def short_date(cls, tax_year: Year) -> str:
        ''' Return the tax year in the format YY/YY. '''
        return f'{tax_year}/{(tax_year + 1) % 100}'
    
    @classmethod
    def full_date(cls, tax_year: Year) -> str:
        ''' Return the tax year in the format DD/MM/YYYY - DD/MM/YYYY. '''
        start, end = cls.period(tax_year)
        return f'{start.strftime("%d/%m/%Y")} - {end.strftime("%d/%m/%Y")}'
