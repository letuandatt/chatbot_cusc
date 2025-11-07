import pytz
from datetime import timezone

# --- ĐỊNH NGHĨA MÚI GIỜ VIỆT NAM ---
try:
    VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
    print("VN_TZ initialized successfully.")
except pytz.UnknownTimeZoneError:
    print("VN_TZ not found, using UTC as default timezone.")
    VN_TZ = timezone.utc