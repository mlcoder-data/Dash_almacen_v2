# patterns.py
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class Result:
    ok: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    msg: Optional[str] = None

def OK(value: Any = None, msg: str | None = None) -> Result:
    return Result(ok=True, value=value, msg=msg)

def ERR(error: str) -> Result:
    return Result(ok=False, error=error)