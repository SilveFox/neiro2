# Ветки и Pull Request — МонтажПро

Работа ведётся от ветки **`main`**. Прямые коммиты в `main` не используются: каждая задача — отдельная ветка и Pull Request.

## Имена веток

| Префикс | Когда |
|---------|--------|
| `feature/` | новая функция |
| `fix/` | исправление бага |
| `docs/` | инструкции, README |

Примеры: `feature/price-search`, `fix/svaroк-range-matching`, `docs/user-manual`.

Одна задача — одна ветка — один PR.

## Как начать задачу

```powershell
cd "d:\Work\neiro 2"
git checkout main
git pull origin main
git checkout -b feature/short-task-name
```

Если remote ещё не настроен, `git pull origin main` пропускайте и работайте локально.

## Коммиты

Пишите сообщение по смыслу, на русском или английском, в повелительном наклонении:

- `fix: не резать диапазон 1-7 как объём`
- `feat: фильтр на вкладке Лог Excel`
- `docs: инструкция пользователя`

Не коммитьте `.venv`, `__pycache__`, месячные `.xlsx` из `data/workbooks/`.

## Pull Request

1. Запушить ветку:
   ```powershell
   git add .
   git status
   git commit -m "feat: краткое описание"
   git push -u origin HEAD
   ```
2. На GitHub/GitLab: **Compare & pull request**.
   - **base:** `main`
   - **compare:** ваша ветка
3. Заполнить шаблон PR (Summary, тип, Test plan).
4. Дождаться ревью и зелёных проверок CI (`tests`).
5. Слить в `main` (**Squash and merge** предпочтительно).
6. Удалить ветку на remote и локально:
   ```powershell
   git checkout main
   git pull origin main
   git branch -d feature/short-task-name
   ```

## Чеклист перед PR

- [ ] Тесты: `python -m unittest tests.test_core tests.test_month_workbook -v`
- [ ] Нет лишних файлов (Excel оператора, кэш Python)
- [ ] Описание PR объясняет *зачем*, не только *что*
- [ ] Если менялись прайс/алиасы — это явно указано в Notes

## Защита `main` (на GitHub)

Settings → Branches → Add rule для `main`:

- Require a pull request before merging
- Require approvals (если есть ревьюер)
- Require status checks to pass: workflow **tests**

## Первый remote (если репозиторий ещё только локальный)

Создайте пустой репозиторий на GitHub (без README), затем:

```powershell
git remote add origin https://github.com/ORG/REPO.git
git push -u origin main
```
