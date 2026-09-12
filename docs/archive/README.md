# Архив

Исторические планы, объяснения и результаты измерений; не текущие требования.
Для обычной работы нужны [план](../structura-edit-roadmap.md) и
[архитектура](../structura-edit-architecture.md). Архив исключён из стандартного `rg`;
читать конкретный материал или искать внутри него с `rg --no-ignore`.

| Исторический вопрос | Материал |
|---|---|
| CPU карт, F5/атлас, slots/validation, locked-замеры, выпущенные зависимости и локальная упаковка | [проверки и A/B](2026-09/interaction-2026-09-12.json); [маршруты мира A](2026-09/world-a-flight-paths.json) |
| Кэши геометрии/карты, VTK packets, визуальные исправления и границы FPS | [проверки и замеры](2026-09/render-cache-2026-09-12.json) |
| Память recipe, компактный IPC и задержки большого Preview | [проверки и замеры](2026-09/recipe-preview-2026-09-11.json) |
| Приём async-результатов, capabilities, resize и Mix | [проверки и замеры](2026-09/editor-contracts-2026-09-11.json) |
| Сокращение контекста и единый запуск проверок | [результаты](2026-09/context-compaction-2026-09-11.json) |
| Последний data-path этап и цифры IPC/search/sparse | [data-path](2026-09/data-path-delivery-2026-09-11.md) и соседний evidence.json |
| Task ID, Cancel, потеря ответа и подтверждение history | [worker lifecycle](2026-09/worker-lifecycle-2026-09-11.md) |
| Инкрементальный patch и cut/missing chunks | [world patch](2026-09/world-patch-delivery-2026-09-11.md) |
| Большие Preview, Take и хранение | [preview](2026-09/preview-responsiveness-2026-09-11.md), [storage](2026-09/improvement-storage-2026-09-10.md) |
| World overview, QEM и навигация | [implementation](2026-09/world-overview-implementation-2026-09-11.md), [первоначальный план](2026-09/world-overview-plan-2026-09-11.md) |
| Живое тестирование и ошибки UX | [feedback](2026-09/editor-feedback-delivery-2026-09-11.md) |
| Разбор внешних предложений | [сверка с кодом](2026-09/next-priorities-2026-09-11.md) |
| Состояние до сокращения документации | [архитектура](2026-09/architecture-before-compaction.md), [roadmap](2026-09/roadmap-before-compaction.md) |
| Ранние этапы редактора | [7–8 сентября](structura-edit/README.md) |

Остальные файлы сохранены в `2026-09` под прежними именами. Наличие старого числа
тестов, лимита или «следующего шага» в отчёте не меняет текущую реализацию.
