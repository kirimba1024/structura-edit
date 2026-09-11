> Исторический материал. Текущие требования: [план](../../structura-edit-roadmap.md) и [архитектура](../../structura-edit-architecture.md).

# База паритета с WorldEdit / Litematica / Axiom (2026-09)

Срез: этапы 1–8 из плана «база функций не хуже аналогов». Всё ниже проверено тестами
(433 pytest) и native-сценариями (smoke_connected, smoke_backup, smoke_stats, smoke_inspector,
smoke_world_edit). Коммиты этапов — в истории git, там же обоснования.

## Что добавлено

| Функция | Где | Суть |
|---|---|---|
| Произвольное выделение | `cell_set.py` | `CellSet` — битовые маски по 16³ секциям, протокол как у `Selection`; операции принимают оба типа |
| Формы в GUI | `commands.py`, `panels.py` | Walls/Shell/Ellipsoid/Cylinder/Top surface + `Duplicate` в меню |
| Hollow, Overlay surface | `operations.py` | `//hollow` (толщина, BFS-эрозия границы) и `//overlay` (над верхним блоком колонки) |
| Условия | `condition.py`, `condition_ui.py` | air / non-air / список материалов / lenient-свойства + Not; общие для From, масок и DestinationRule «Only where» |
| Смеси | `mix.py`, `mix_ui.py` | веса относительные, выбор по splitmix64(seed,x,y,z); Preview==Apply; работает с сохранением свойств |
| Связное выделение | `connected.py`, `connected_actions.py` | Material / Exact state / Non-air, 6-связность, Add/Subtract, бюджет 2M, worker с прогрессом |
| Иконки предметов | `item_icons.py` | 32px nearest из ресурсов клиента, PNG через worker, LRU кэш |
| Контур изменений | `changes_view.py`, `changes_ui.py` | View → Unsaved changes: акцент/красный контуры по overlay, счётчики, бюджет 100k |
| Revert to opened | `ui.py` | Edit-меню: seek_history(0); отмена пересохранения честно даёт обратный patch |
| Бэкапы миров | core `world_staging.py`, `restore_ui.py` | File → Restore backup: список manifest, верификация хешей, safety-копия перед восстановлением |
| Force при конфликте Save | core `world_patch/world_write`, `restore_ui.py` | диалог «позиция / before / на диске / after», Force пишет показанное |

## Семантика, на которую опираемся

- Замена «From» без значения = non-air (`//replace` по умолчанию). Unknown/unloaded ≠ air.
- Hollow: глубина = L∞-расстояние до дополнения; Walls/Shell на CellSet = «есть 6-сосед вне выделения»,
  для бокса доказано и закреплено тестами (`test_cell_session.py`, `test_shapes.py`).
- Move/Duplicate/Stack с include_air на клеточном выделении стирают только footprint, не весь бокс.
- Связное выделение не зависит от среза высоты; пустые клетки (void) не совпадают ни с одним критерием.
- Revert к открытому после сохранения показывает обратные правки как новые unsaved changes — это
  корректно (диск уже изменён).

## Грабли (проверено тестами, не наступать снова)

- `CellSet` хранит биты MSB-first (`int.to_bytes('big')`); маски/нарезка секций строятся через
  `_span(start, length)` в том же домене. Смешение LSB/MSB даёт мусорные границы.
- Срез секций в `connected._cells`: конец WITHOUT +1 (эксклюзивный), иначе broadcast 17→16.
- Ноль в сетке связанных состояний зарезервирован пустотой; `lookup` палитры без ведущего нуля.
- `item.data(UserRole)` в PySide возвращает копию dict — ключать верификацию по имени, не по `id()`.
- Оверлей выделения: углы A/B могут быть None в режиме cells — фильтруются в `set_selection`.
- Toggle оверлея изменений обязан сбрасывать token при выключении, иначе повторное включение
  не перерисует (закреплено в smoke_backup).

## Ограничения (осознанные)

- Контур изменений не различает resize документа (посчитаны только клетки overlay).
- Диалог Force применяет все показанные строки; выборочное включение строк — потом.
- Кисти, сглаживание рельефа, биомы, именованные выделения — вне этого этапа; CellSet делает
  именованные выделения дешёвыми в будущем.
- Составные условия — без языка выражений: один вид + Negate.

## Метрики

- BFS связности: 510k клеток за 0.32 c (сетка ~0.1 c, память ~12 МБ); union/difference CellSet
  2M ≈ 7/26 мс; from_box 2M ≈ 60 мс.
- Полёт (benchmark_flight) после изменений не просел (та же геометрия и конвейер секций).
