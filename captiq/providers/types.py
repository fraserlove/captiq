from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from yaml import YAMLObject
from dateutil.parser import parse as parse_timestamp


@dataclass
class Split(YAMLObject):
    date: datetime
    ratio: Decimal
    yaml_tag = '!split'

    @classmethod
    def from_yaml(cls, loader, node) -> 'Split':
        value = loader.construct_scalar(node)
        timestamp, ratio = value.split(',')
        return Split(parse_timestamp(timestamp), Decimal(ratio))

    @classmethod
    def to_yaml(cls, dumper, data) -> str:
        return dumper.represent_scalar(cls.yaml_tag, f'{data.date}, {data.ratio}')

    def __eq__(self, other) -> bool:
        return self.date == other.date and self.ratio == other.ratio


@dataclass
class SecurityInfo(YAMLObject):
    name: str = ''
    splits: Sequence[Split] = field(default_factory=list)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    yaml_tag = '!security'
