from pathlib import Path
from core.workbook_factory import set_active_workbook

# путь к тестовой книге
test_path = Path("data/workbooks/SE_test_2026-07.xlsx")
set_active_workbook(test_path, year_month="2026-07")