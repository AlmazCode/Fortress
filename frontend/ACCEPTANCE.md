# U — предварительная проверка запуска, Windows

18 октября 2026. Состояние **blocked**, автор №2; независимая приёмка не заявляется. Человек разрешил предварительные проверки A/F до I и уточнил целевую платформу: Windows для сервиса и будущего обучения. Linux-хост не является новым требованием пользователя.

Проверенный код: `d0d3ca5bda0b7e92feb0cd4945962508b4e7d6c2`, собственная ветка `codex/dev2-frontend`; принятую integration `469b2eb841de187d8e3429dc17514254777d3bdc` объединил без правок входящих файлов. Frontend и contracts по сравнению с предыдущим опубликованным head не изменены. После свежего fetch I всё ещё blocked по O runtime/external HTTPS, принятого SHA I нет.

На настоящем Windows Python 3.11.17 команда `python -c "from backend.app.main import create_app"` завершилась **exit 1**: `main.py:18 → deadlines.py:13 → tasks.py:9 → import fcntl → ModuleNotFoundError`. Запуск API не состоялся. Дополнительно статически выявлены POSIX `flock`, `SIGALRM`/`setitimer` и конфигурация `prefork`; это предмет проверки переносимости, а не результаты исполненных worker tests. Удаление импорта или подмена worker без проверки гарантий не исправляют runtime.

Передача №1/№4 через этот отчёт: обеспечить штатный native Windows запуск API/worker/БД/очереди с сохранением межпроцессного GPU lock, дедлайнов, durable jobs и восстановления после сбоя. Нужны настоящий production без release и отдельно явный synthetic API test profile. После этого №2 проверяет реальный браузерный путь; итоговая U требует принятого I. Backend/infra в этой ветке №2 не исправлял.

Все семь групп браузерных критериев пока **not_run**: upload→202→polling→done/failed, production503, явная synthetic provenance, auth/network/resume, source PTS/video/JPEG, lifecycle/key checks и 360/768/1440 с клавиатурой и новыми screenshot observations. Версия браузера не заявляется: браузер для этой попытки не запускался. Старые fixture screenshots и 110 component tests относятся к F и не заменяют U. Подробности и реальные exit codes — [report.json](../tests/e2e/report.json).

Перед изменениями сохранён локальный checkpoint. Временно добавленную для подготовки Playwright зависимость убрал из tracked manifest/lock: невыполненная подготовка тестов не включается в кандидат. Прежний чужой `frontend/.gitignore` сохранён без добавления в Git. Полное обучение не запускалось; его Windows/GPU совместимость №2 здесь не проверял.
