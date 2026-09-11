# Архитектура Structura Edit

Текущий контракт реализации. [Пользовательское поведение](workbench.md),
[Python API](api.md), [план](structura-edit-roadmap.md), [проверки](verification.md).
Открывать строку карты по задаче; это не список файлов для обязательного чтения.

## Владельцы и точки входа

Все имена модулей ниже относятся к `src/structura_edit`.

| Область | Владелец и основной путь |
|---|---|
| Состояние редактора | `editor_document.py`: сессия, selection, preview, epoch/input tokens; `edit_workflow.py`: подготовка, Apply, history, Save |
| Данные и история | `session.py`, `document.py`, `changes.py`, `history.py`; unsaved — `saved_changes.py`; resize — `document_resize.py` |
| Мировая область | `source_loading.py`, `world_view.py`, `world_changes.py`; GUI — `source_ui.py`, `world_ui.py` |
| Фоновая задача | `task_protocol.py` → `jobs.py` → `tasks.py`; lifecycle callback — `task_runner.py`; один снимок — `worker_document.py`, delta — `worker_delta.py` |
| Команды и геометрические операции | `commands.py`, `operations.py`, `condition.py`, `mix.py`, `planar.py`, `paint.py` |
| Перенос и повтор | `clipboard.py`, `clipboard_placement.py`, `clipboard_transform.py`; `placement_ui.py`/`placement_review.py`, `repeat_ui.py` |
| NBT и сущности | `entity_data.py`, `object_edits.py`, `nbt_values.py`, `nbt_batch.py`; `object_ui.py`, `region_inspector.py`, `nbt_batch_ui.py` |
| Поиск и инспекция | `object_search.py`, `object_search_ui.py`; `inspection.py`/`inspection_ui.py`; NBT-поиск — `nbt_search.py`/`nbt_search_ui.py` |
| Сцена и preview | `render_source.py`, `sections.py`, `preview.py` → `view_pipeline.py` → `scene.py`; кэш — `section_cache.py` |
| Обзор мира | `overview_model.py`, `overview_ui.py`; сборка/хранение — `overview_build.py`, `overview_store.py`; VTK — `overview_scene.py` |
| Карты и срез | `height_slice.py`, `camera_maps.py`, `map_cache.py`, `map_canvas.py`; мировая карта — `world_map.py`, `overview_maps.py` |
| Ввод и оформление | `navigation.py`, `mouse_look.py`, `cocoa_mouse.py`; общие значения — `appearance.py`, кожа — `theme.py`, `data/editor.qss` |
| Локальные данные | `local_store.py`, `patch_codec.py`, `drafts.py`, `fragments.py`; диагностика — `action_log.py` |
| Сборка GUI | `ui.py` связывает компоненты; меню — `menus.py`, семантика Undo — `action_state.py` |

Core владеет форматами, совместимостью, записью мира и grid/block/entity transforms;
render — моделями, meshing, проекциями и QEM. Engine/model не импортируют GUI.
`ui.py` остаётся явной сборкой; не заменять зависимости event bus или service locator.

## Изменение документа

GUI/API → команда → ChangeSet → preview → Apply. Подготовка не меняет исходную
сессию; Apply записывает историю до изменения данных. Ошибка записи не уничтожает
redo. Save сохраняет историю; Undo после Save создаёт обратные несохранённые правки.
История — временная SQLite с ограниченным RAM-кэшем, не persistent recovery.
Draft восстанавливает конечный patch и контекст без прежней Undo-цепочки.

Document хранит исходную структуру; session — overlay и EntityData. Опубликованный
снимок не мутируется следующим ответом worker. NBT извлекается независимо, исходные
records/palettes сохраняются. `stored_positions(selection)` выбирает меньший обход
базы/overlay или выделения; явный воздух остаётся записью, отсутствие записи — нет.

Координаты операций локальны; `origin` переводит их в мир. WorldChanges использует
`(dimension, x, y, z) → (before, after)`, а WorldView — его текущую проекцию.
Маленькая правка обновляет только delta; Open/Reload/Fork выполняют полную синхронизацию.
F5 сохраняет глобальный patch и history. Новое Open начинает отдельный документ.
Неизвестные чанки/секции не считаются воздухом; запись принадлежит core.

Clipboard сохраняет footprint, исходные позиции и происхождение NBT. Paste/Stack
читают один исходный снимок; последний экземпляр выигрывает пересечение. Take
защищает пропущенные исходные клетки от перекрытия. Без Air бюджет считает блоки,
с Air — footprint/объём; resize и будущая геометрия проверяются отдельно.
Преобразования накапливаются от оригинала буфера, чтобы полный цикл был точным.

## Принятие фонового результата

- EditorDocument владеет epoch; открытие и принятая замена меняют его. Session token
  относится к документу, input token дополнительно к selection и параметрам. Изменение
  формы не должно отменять уже запущенный Save/Apply.
- EditWorkflow и PlacementReview проверяют захваченный token до `replace`. Первый
  ответ инвалидирует второй ответ от того же исходного состояния даже без serial worker.
  Сам replace пока проверяет ID и monotonic revision; не обходить проверку исходного token.
- Worker-протокол несёт task ID во всех progress/result/failure. DocumentToken различает
  snapshot ID, document ID, revision и state ID: одинаковая revision после Reload
  недостаточна. Клиент также проверяет идентичность сессии и базового Document.
- Один worker удерживает один документ. Ошибка, смена источника и смерть процесса
  сбрасывают подтверждение. Следующий явный запрос передаёт снимок заново; завершённая
  или неопределённая запись автоматически не повторяется.
- Apply блоков и одиночный Undo/Redo без resize/сущностей возвращают итоговые значения
  ключей и History. Поток обмена копирует словари и собирает EditSession, не исполняя
  операцию и не записывая SQLite повторно. Save/resize/entities/multi-step history,
  подклассы сессии и render сохраняют полный ответ. Копирование остаётся O(P).
- SQLite-путь создаёт родитель. Worker откладывает удаление redo-строк до следующего
  запроса с принятым снимком. Потеря ответа/ошибка сборки оставляют GUI прежнюю историю;
  новая orphan-строка может остаться до удаления временного журнала.
- TaskRunner: IDLE → STARTING → RUNNING; отмена может ждать CANCELLING. SubmitResult
  различает STARTED/BUSY/FAILED_TO_START. Callback освобождается до вызова результата,
  чтобы тот мог начать следующую задачу; старый callback не должен сбросить новую.
- Cancel закрывает процесс и отбрасывает его ответы. Если prepare/restore ещё выполняет
  поток, новый обмен ждёт его завершения. Очередь прогресса хранит одно значение.
  Зависший Python-поток нельзя безопасно убить; это ограничение сохраняется явно.

## Сцена, поиск и ввод

ViewPipeline принимает только текущий request. Новые акторы создаются скрыто порциями,
прежние остаются до принятия; отмена закрывает генератор и освобождает временные VTK-объекты.
VTK работает в GUI-потоке; render-запросы объединяются одним Qt timer. Preview включает
halo для соседних форм; Apply переиспользует принятую геометрию. Одновременная старая
и новая сцена увеличивают peak памяти; один VTK-вызов может превысить целевую порцию.

HeightSlice принадлежит запросу вида. Scene принимает срез вместе с геометрией;
picking использует показанный срез до замены. Карты проверяют известность внутри
фактического slab, разделяют dimension/resources/depth; preview не загрязняет атлас.
Обзор мира — отдельный неизменяемый снимок и исполнитель, не второй владелец edits.
[Выбор покрытия, публикация и телепорт](world-view.md).

ObjectSearch хранит один индекс и маску последнего запроса, счётчики по 4096 строк.
Страница извлекается порциями; новый snapshot сбрасывает индекс даже при той же revision.
Бюджет 64 MiB включает индексы блоков/сущностей, маску и запас временных/result-данных;
это не RSS процесса. Collect проверяет размер выдачи до материализации. ObjectFinder
использует тот же worker-document slot; NBT batch фиксирует полный набор targets и revision.

Selection card ограничивает preview до 32³ и 32 сущностей; точные counts не приближены.
NBT tree/поиск/таблицы загружают страницы, не создают виджет на каждое поле.

На macOS Cocoa даёт относительные дробные deltas; события до capture отбрасываются,
CoreGraphics отвязывает движение курсора. Остальные платформы используют Qt recenter
с исключением синтетических движений. Focus/menu/dialog освобождают capture и held keys.
VTK-overlay используется вместо прозрачного QWidget поверх native render: тот оставлял
следы старого фона. Поведение клавиш определено в workbench, физический ввод проверяется вручную.

## Изменения и проверки

Меню и handler истории читают один history_action; общая матрица остальных capabilities
ещё не сведена. Расширять существующие правила по конкретному сценарию, а не создавать
ещё одно изменяемое состояние. Новые абстракции требуют существующего владельца и задачи.

Структурные решения хранить здесь, текущую очередь — в плане, измерения — в архиве.
Не дублировать текущие лимиты/CLI во всех отчётах. Проверки engine сравнивают данные,
Undo и stale-ответы; геометрию — по покрытию/материалам, а не порядку вершин.
Команда и обязательные native-сценарии определены в verification.
