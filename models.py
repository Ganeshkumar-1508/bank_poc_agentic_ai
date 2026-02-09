from dataclasses import dataclass
from typing import Optional

@dataclass
class UserQuery:
    raw: str
    product_type: str
    amount: Optional[float]
    tenure_months: Optional[int]
    tenure_days: Optional[int]
    age: Optional[int]

@dataclass
class RateRow:
    provider: str
    tenure: str
    interest_rate: str
    amount: str
    senior_citizen: str
    source_url: str
    source_name: str = ""
    rate_min: Optional[float] = None
    rate_max: Optional[float] = None
