# 📝 Flask Task Manager Pro

Менеджер задач на Flask + SQLite с REST API и красивым интерфейсом.

## Возможности
- ✅ Добавление / удаление / выполнение задач
- 🎯 Приоритеты (low / medium / high)
- 🏷 Категории
- 📅 Дедлайны с подсветкой просрочки
- 🔍 Поиск и сортировка
- 📊 Статистика и прогресс-бар
- ⬇ Экспорт в JSON

## Установка и запуск

```bash
git clone https://github.com/ТВОЙ_НИК/flask-task-manager.git
cd flask-task-manager

python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
python app.py
```

Открой http://localhost:5000

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/tasks` | Список задач |
| POST | `/api/tasks` | Создать задачу |
| PUT | `/api/tasks/<id>` | Обновить |
| PATCH | `/api/tasks/<id>/toggle` | Переключить статус |
| DELETE | `/api/tasks/<id>` | Удалить |
| GET | `/api/stats` | Статистика |
| GET | `/api/export` | Экспорт JSON |
