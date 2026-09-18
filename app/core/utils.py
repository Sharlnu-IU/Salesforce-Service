import math
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional
import uuid

def deep_serialize(obj: Any) -> Any:
    """
    Recursively converts Decimals, UUIDs, Enums, and datetimes into JSON-safe structures.
    """
    if isinstance(obj, dict):
        return {k: deep_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [deep_serialize(item) for item in obj]
    elif isinstance(obj, (datetime,)):
        return obj.isoformat()
    elif isinstance(obj, (uuid.UUID,)):
        return str(obj)
    elif isinstance(obj, (Decimal,)):
        return float(obj)
    elif isinstance(obj, (Enum,)):
        return obj.value
    return obj

def calculate_duration(start: Optional[datetime], end: Optional[datetime] = None) -> Optional[float]:
    """
    Calculates duration in seconds between two datetimes. If end is None, uses current UTC time.
    """
    if not start:
        return None
    end_time = end or datetime.now(timezone.utc)
    # Ensure timezone awareness compatibility
    if start.tzinfo is None and end_time.tzinfo is not None:
        start = start.replace(tzinfo=timezone.utc)
    elif start.tzinfo is not None and end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    return round((end_time - start).total_seconds(), 2)

def build_pagination_info(page: int, page_size: int, total: int) -> Dict[str, Any]:
    """
    Constructs a standard pagination envelope.
    """
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
