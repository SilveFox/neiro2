# -*- coding: utf-8 -*-
"""Update Flet prototype to use shared parser (workers[])."""
import flet as ft
import time
import asyncio
from pathlib import Path

from core.parser import ParseError, parse_report_text
from core.pricing import calculate_report
from core.excel_writer import append_calc_to_workbook, ensure_working_workbook


class TestApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Проверка ИИ-отчётов (одиночный прогон)"
        self.page.window.width = 1000
        self.page.window.height = 800
        self.page.theme_mode = ft.ThemeMode.LIGHT

        self.current_dir = Path(__file__).parent
        self._processing = False
        self._timer_start = 0.0
        self._last_report = None

        ensure_working_workbook()
        self.init_ui()

    def init_ui(self):
        self.page.padding = 0

        self.txt_report = ft.TextField(
            label="Текст отчёта",
            multiline=True,
            min_lines=6,
            max_lines=8,
            hint_text="Несколько сотрудников — каждый со своими работами...",
        )
        self.txt_date = ft.TextField(
            label="Дата отчёта (YYYY-MM-DD)",
            value=time.strftime("%Y-%m-%d"),
        )
        self.txt_extra_prompt = ft.TextField(
            label="Дополнительная инструкция для ИИ (необязательно)",
            multiline=True,
            min_lines=2,
            max_lines=3,
        )
        self.btn_run_once = ft.Button(
            content=ft.Text("Обработать отчёт"),
            on_click=self.on_run_once_click,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
        )
        self.btn_excel = ft.Button(
            content=ft.Text("Добавить в Excel"),
            on_click=self.on_excel_click,
            disabled=True,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
        )
        self.progress_ring = ft.ProgressRing(width=18, height=18, stroke_width=2)
        self.lbl_status = ft.Text("Обработка... 00:00", size=14, color=ft.Colors.BLUE_700)
        self.status_row = ft.Row(
            [self.progress_ring, self.lbl_status],
            spacing=10,
            visible=False,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.txt_logs = ft.TextField(
            label="Логи системы",
            multiline=True,
            read_only=True,
            expand=True,
            min_lines=1,
            text_size=12,
            text_style=ft.TextStyle(font_family="Courier New"),
        )

        self.page.add(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Одиночная проверка ИИ-отчёта", size=24, weight=ft.FontWeight.BOLD),
                        ft.Text("workers[] ➜ прайс ➜ лист дня в Excel", size=14, color=ft.Colors.GREY_700),
                        ft.Divider(),
                        self.txt_date,
                        self.txt_report,
                        self.txt_extra_prompt,
                        ft.Row(
                            [self.btn_run_once, self.btn_excel, self.status_row],
                            spacing=16,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Divider(),
                        self.txt_logs,
                    ],
                    expand=True,
                    spacing=15,
                ),
                expand=True,
                padding=20,
            )
        )

    def log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        self.txt_logs.value = (self.txt_logs.value or "") + f"[{timestamp}] {message}\n"
        self.txt_logs.update()

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        total = int(seconds)
        mins, secs = divmod(total, 60)
        return f"{mins:02d}:{secs:02d}"

    def _start_status_timer(self):
        self._processing = True
        self._timer_start = time.monotonic()
        self.lbl_status.value = "Обработка... 00:00"
        self.status_row.visible = True
        self.status_row.update()
        self.page.run_task(self._timer_loop)

    async def _timer_loop(self):
        while self._processing:
            elapsed = time.monotonic() - self._timer_start
            self.lbl_status.value = f"Обработка... {self._format_elapsed(elapsed)}"
            self.lbl_status.update()
            await asyncio.sleep(0.25)

    def _stop_status_timer(self) -> str:
        elapsed = time.monotonic() - self._timer_start if self._timer_start else 0.0
        self._processing = False
        elapsed_str = self._format_elapsed(elapsed)
        self.status_row.visible = False
        self.status_row.update()
        return elapsed_str

    def on_run_once_click(self, e):
        if self._processing:
            return
        report_text = (self.txt_report.value or "").strip()
        if not report_text:
            self.log("⚠️ Ошибка: поле отчёта пустое.")
            return

        extra = (self.txt_extra_prompt.value or "").strip()
        report_date = (self.txt_date.value or "").strip() or None
        self.btn_run_once.disabled = True
        self.btn_run_once.update()
        self._start_status_timer()

        def worker():
            try:
                self.log("⚙️ Отправка отчёта в модель...")
                report = parse_report_text(report_text, extra_prompt=extra, report_date=report_date)
                calc = calculate_report(report)
                self._last_report = report
                self.btn_excel.disabled = False
                self.btn_excel.update()
                elapsed = self._stop_status_timer()
                names = ", ".join(w["raw_worker_name"] for w in report["workers"])
                self.log(
                    f"✅ Сотрудники: {names}; сумма {calc.grand_total}; "
                    f"несматчено {calc.unmatched_count}; время {elapsed}"
                )
            except ParseError as ex:
                self._stop_status_timer()
                self.log(f"❌ {ex}")
            except Exception as ex:
                self._stop_status_timer()
                self.log(f"❌ Неожиданная ошибка: {ex}")
            finally:
                self.btn_run_once.disabled = False
                self.btn_run_once.update()

        self.page.run_thread(worker)

    def on_excel_click(self, e):
        if not self._last_report:
            self.log("⚠️ Сначала разберите отчёт.")
            return
        if self._processing:
            return
        self._start_status_timer()
        self.btn_excel.disabled = True
        self.btn_excel.update()

        def worker():
            try:
                report = dict(self._last_report)
                date_now = (self.txt_date.value or "").strip()
                if date_now:
                    report["report_date"] = date_now
                calc = calculate_report(report)
                result = append_calc_to_workbook(calc)
                elapsed = self._stop_status_timer()
                if result.get("duplicate"):
                    self.log(
                        f"⚠️ Дубликат, пропуск ({elapsed}): {result.get('message')} "
                        f"[{report.get('report_date')}]"
                    )
                else:
                    self.log(
                        f"✅ Excel лист {result.get('day_sheet')} "
                        f"({report.get('report_date')}), "
                        f"блоков {len(result.get('blocks') or [])}, время {elapsed}"
                    )
                self._last_report = report
            except Exception as ex:
                self._stop_status_timer()
                self.log(f"❌ Excel: {ex}")
            finally:
                self.btn_excel.disabled = False
                self.btn_excel.update()

        self.page.run_thread(worker)


def main(page: ft.Page):
    TestApp(page)


if __name__ == "__main__":
    ft.run(main)
