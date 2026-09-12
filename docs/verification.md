# Проверки редактора

Запускать из workspace; установку см. в [README](../README.md#install-and-launch).
`.venv-edit` содержит GUI/test/typing. Ruff доступен в `.venv` либо PATH;
при необходимости установить `ruff==0.13.3` в рабочее окружение. Состав проверок
задан в [tools/check_edit.py](../../../tools/check_edit.py), а не дублируется списком команд.

```bash
.venv-edit/bin/python tools/check_edit.py fast
.venv-edit/bin/python tools/check_edit.py native
.venv-edit/bin/python tools/check_edit.py full
```

- **fast:** локальные ссылки активной документации, Ruff, strict mypy выбранной границы,
  core/edit pytest и native QEM unit test. Часть pytest использует Qt: это не headless-профиль.
- **native:** обязательные smoke сохранения/восстановления, отклонения старого recipe, clipboard, поиска/NBT,
  карт/срезов, точных texels и entity icons, повторного GPU preview, world overview/телепорта
  и навигации. Окна запускаются последовательно.
- **full:** fast и native. Сборка приложения — отдельный [packaging check](../packaging/README.md).
- **docs:** только структура и локальные ссылки текущей документации.

Скрипт создаёт отдельный каталог результата: лог на шаг и result.json. Итог passed
появляется только после всех шагов профиля. Ошибка, timeout, прерывание или отсутствующий
инструмент дают ненулевой код; автоматического повтора нет. `--output` задаёт новый
каталог, `--timeout` — предел одного шага. Настройки draft/recent/Amulet временные.
Запись мира проверяется на fixtures; путь к личному миру не нужен.

На этом Mac запуск Qt из sandbox может падать до теста: использовать разрешённый
native запуск в разблокированном сеансе. Offscreen не заменяет проверку фокуса/capture; автосценарии не доказывают
работу физического тачпада. Для navigation оставить тестовое окно активным; полёт,
переключение приложений/меню и возврат фокуса дополнительно проверить руками.

Mypy 1.18.2 проверяет task_protocol/worker_document/worker_delta/action_state, импортируемая
реализация пропускается. Это не доказательство type completeness всего py.typed API.
Ruff пока E4/E7/E9/F; расширение format/import rules выполняется отдельно от логики.

В [CI](../../../.github/workflows/check-edit.yml) тот же `fast` настроен для Linux
(Python 3.9/3.11, Xvfb), macOS и Windows (Python 3.11). Логи сохраняются артефактом.
Конфигурация требует публикации текущих изменений библиотек и submodule refs;
её наличие не означает успешный прогон на этих системах. Native navigation,
минимальная macOS и упаковка остаются отдельными проверками.

Совместимость зависимостей проверяется отдельно от workspace: импорт должен идти
из wheels, а не editable checkout. Edit 0.1.0a2 требует core 0.6.2/render 0.8.2:
прежние опубликованные версии не содержали обязательных API. Собственный
[CI редактора](../.github/workflows/verify.yml) собирает wheel, устанавливает его
с опубликованными зависимостями на Linux/macOS/Windows и проверяет версии,
расположение модулей, нужные импорты, Ruff, mypy и pytest. `pip check` сам по себе
не подтверждает наличие API. Сборка macOS устанавливает свежие wheels из исходников
каждой библиотеки и записывает их версии и SHA-256 в `build.json`.

## Проверка конкретной правки

Сначала воспроизведение и целевые tests, затем профиль по затронутой границе.
Документация без кода требует docs; data/model — fast; GUI/state/worker — full.
Не запускать заново весь набор после каждого изменения Markdown. Новая упаковка
проходит bundled demo → worker/NBT Apply/Save/Undo → обзор временного Java-мира.

Ошибки worker доступны в Issues → Copy details и stdout recipe. Для падений Python
использовать `-X faulthandler`. После правки исходников перезапустить GUI/worker;
CodeVersion — development guard по mtime/size, не хеш содержимого.

## Замеры по задаче

Из `libs/structura-edit/tests`; запускать готовым `.venv-edit/bin/python` из workspace.

| Скрипт | Что измеряет |
|---|---|
| `benchmark_edit_workflow.py --visible` | 24 этажа, Take/resize/Save/Undo/Redo; время GUI и RSS; `--full-session` даёт контроль IPC |
| `benchmark_changes.py` | Повторные validation/encode/decode ChangeSet для Take 24-этажного здания; `--profile` отдельным проходом |
| `benchmark_map_canvas.py --output PATH` | 512 сущностей, движение камеры, малая/большая карта в QImage Retina; frame/CPU distributions, PNG и хеш пикселей |
| `benchmark_worker_document.py` | Pipe/SQLite при 0–500k patch; байты ответа до восстановления; GUI/render не входят |
| `benchmark_search_pages.py` | Широкий запрос и страницы готового индекса до 3 млн строк; tracemalloc отдельно |
| `benchmark_object_search.py --synthetic-blocks 100000` | Построение индекса и реальные worker-запросы страниц |
| `benchmark_sparse_iteration.py` | Маленький Replace и Copy редких блоков в больших bounds |
| `benchmark_paint.py` | Работа кисти вдоль пути и контроль полного прямоугольника |
| `benchmark_world.py PATH --radius 6 --visible` | Полный маршрут на временной копии мира |
| `benchmark_flight.py PATH --visible --close` | Полёт, кадры и отзывчивость без постоянного FPS-счётчика в продукте |
| `benchmark_overview.py WORLD --reuse` | Изолированная копия готового кэша, дальний вид, полёт и latest-wins teleport; мир только читается |

Измерять последовательно, без параллельных tests. Сохранять размер сцены/viewport,
версии, параметры, p50/p95/p99/p99.9/max, GUI gap и RSS; сумма RSS повторно учитывает общие
страницы, bytes геометрии не равны VRAM. Профилировать отдельным прогоном (`--profile`,
`--trace` у workflow), а timings сравнивать без профиля. Результат — в архиве с указанием
ограничений; текущие контракты и план не копируются в каждый новый отчёт.
`flight_metrics.py` считает FPS только по завершённым кадрам с новым положением или
направлением камеры, включая up; первоначальный неподвижный кадр и повторные RenderEvent
не завышают FPS. Сохраняются длительность всего интервала, completed-motion FPS, первый
и последний промежутки без движения, сырые отметки кадров/render/heartbeat. Render
durations и 5-мс heartbeat измеряются отдельно; фиксируются кадры дольше одного/двух бюджетов.
Сравнивать холодную подготовку, повторное открытие и полёт отдельно, при одинаковом
viewport и представлении геометрии. Colored-only замер не заменяет textured acceptance.

`benchmark_overview.py` по умолчанию требует native окно и активный сеанс; потеря
активности, смена экрана или viewport завершает прогон ошибкой. `--diagnostic` допускает
заблокированный сеанс, но результат имеет статус diagnostic; `--profile` тоже не даёт
эталонного FPS. QImage-замер карты проверяет CPU и пиксели независимо от WindowServer,
а не полную задержку интерактивного окна.

Эталонный запуск после разблокировки:

```bash
.venv-edit/bin/python libs/structura-edit/tests/benchmark_overview.py WORLD --reuse --radius 6 --viewport 2760 1600 --flight-seconds 30 --target-hz 60 --paths libs/structura-edit/docs/archive/2026-09/world-a-flight-paths.json --output /private/tmp/structura-overview-reference.json
```

`--reuse` требует подходящий HLOD-снимок и копирует его вместе с geometry cache во
временные данные; drafts/recent и личный кэш не меняются. `--cache-source` задаёт корень
исходного кэша. JSON маршрутов содержит мировые position/target, travel и yaw_degrees;
данный набор относится к миру A, положения леса/пещеры ещё требуют визуального подтверждения.
`--tick-ms` меняет только таймер сценария, не таймер навигации продукта; обе величины
и частота экрана записываются в результат. 120 Hz не подтверждается прогоном с 16-мс таймером.
