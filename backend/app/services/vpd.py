import math

def calculate_vpd(temp_c: float | None, humidity_pct: float | None) -> float | None:
    if temp_c is None or humidity_pct is None or not (-40 <= temp_c <= 85) or not (0 <= humidity_pct <= 100):
        return None
    svp = 0.6108 * math.exp((17.27 * temp_c) / (temp_c + 237.3))
    return round(svp * (1 - humidity_pct / 100), 3)

def vpd_band(vpd: float | None) -> str:
    if vpd is None: return 'unavailable'
    if vpd < 0.8: return 'low'
    if vpd < 1.5: return 'moderate'
    return 'high'
