ROLES = ("admin","host","server","bartender","kitchen")
CATEGORIES = ("bar","appetizers","hot","cold")
TRACKS = CATEGORIES
CATEGORY_LABELS = {"bar":"Bar","appetizers":"Appetizers","hot":"Hot","cold":"Cold"}
TABLE_SEATS = [f"{r}{c}" for r in "ABCD" for c in "1234"]
BAR_SEATS = [f"BAR{i}" for i in range(1,11)]
ALL_SEATS = TABLE_SEATS + BAR_SEATS
# Labor is costed at this rate for every employee on the clock ($10.00 per hour)
LABOR_RATE_CENTS_PER_HOUR = 1000
