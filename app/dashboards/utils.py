"""
Utility functions for dashboards
"""
import hashlib
import arabic_reshaper
from bidi.algorithm import get_display
import jdatetime
from datetime import datetime
from typing import Optional, Union

def get_color_for_key(key: str) -> str:
    """Generate consistent color hex code based on a key string."""
    h = hashlib.md5(key.encode()).hexdigest()
    return f"#{h[:6]}"

def reshape_rtl(text: str) -> str:
    """Reshape Persian text for RTL display."""
    if not text:
        return ""
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except Exception:
        return str(text)

def to_jalali(dt: Union[datetime, str]) -> str:
    """Convert datetime to Jalali string."""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return dt
    
    try:
        jalali = jdatetime.datetime.fromgregorian(datetime=dt)
        return jalali.strftime("%Y/%m/%d %H:%M")
    except Exception:
        return str(dt)

def format_number(num: Union[int, float], decimals: int = 0) -> str:
    """Format number with thousand separators."""
    if decimals > 0:
        return f"{num:,.{decimals}f}"
    return f"{num:,}"

def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, return default if denominator is zero."""
    if denominator == 0:
        return default
    return numerator / denominator

def safe_percentage(numerator: float, denominator: float, decimals: int = 1) -> str:
    """Calculate percentage safely."""
    if denominator == 0:
        return f"{0:.{decimals}f}%"
    percentage = (numerator / denominator) * 100
    return f"{percentage:.{decimals}f}%"


