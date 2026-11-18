ROLES = ("admin","host","server","bartender","kitchen")
# Access levels. A role (position) is the station someone works a shift in; access is what they are allowed to manage.
#   owner   - everything, including the employee database, recipes and devices
#   manager - runs the restaurant (command center, reports, end of day, every station) but no database management
#   team    - works the stations listed in their positions
ACCESS_LEVELS = ("owner", "manager", "team")
ACCESS_LABELS = {"owner": "Owner", "manager": "Manager", "team": "Team Member"}
STATION_ROLES = tuple(role for role in ROLES if role != "admin")
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 5
CATEGORIES = ("bar","appetizers","hot","cold")
TRACKS = CATEGORIES
CATEGORY_LABELS = {"bar":"Bar","appetizers":"Appetizers","hot":"Hot","cold":"Cold"}
TABLE_SEATS = [f"{r}{c}" for r in "ABCD" for c in "1234"]
BAR_SEATS = [f"BAR{i}" for i in range(1,11)]
ALL_SEATS = TABLE_SEATS + BAR_SEATS
# Labor is costed at this rate for every employee on the clock ($10.00 per hour)
LABOR_RATE_CENTS_PER_HOUR = 1000

# Devices: a monitor shows ticket tracks; a printer prints ticket tracks and/or guest receipts
DEVICE_KINDS = ("printer", "monitor")
RECEIPT_JOB = "receipt"
PRINTER_JOBS = TRACKS + (RECEIPT_JOB,)
