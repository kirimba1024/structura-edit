# Приложение macOS

Локальная сборка для Apple Silicon из текущих исходников workspace. Приложение
содержит Python, Qt, VTK, библиотеки Structura, шрифт, пример и таблицы форматов.
Ресурсы Minecraft пользователь выбирает отдельно; без них работает цветной рендер.

## Сборка

Из корня workspace на Apple Silicon Mac с Python 3.9 и Xcode Command Line Tools:

```bash
.venv-edit/bin/python libs/structura-edit/packaging/build_macos.py
```

Скрипт создаёт изолированное `build/package-env`, устанавливает зависимости из
`macos-requirements.txt`, собирает свежие wheels core/render/edit и проверяет их
зависимости. PyInstaller собирает приложение из установленных wheels; editable
пакеты и внешняя `.venv-edit` в приложение не включаются. `--skip-install`
повторно использует установленные зависимости, но заново собирает библиотеки
из исходников. `--output /absolute/path` меняет каталог результата.

Затем проверяются подпись и рабочий маршрут в настоящем окне приложения:
bundled demo → открытие временной структуры → пакетная правка 70 объектов →
Preview → Apply → Save и повторное чтение → Undo → обзор временного Java-мира.
Последний этап выполняет общий `tests/smoke_overview.py`: построение шести чанков
с нативным QEM, телепорт A→B→C, отмена движением, F5, смена среза, отмена без
автоповтора и зум карты. В пакет входят этот сценарий и его fixture, а не весь
набор тестов. Проверка использует собственные временные данные и пустой каталог
ресурсов. Только после успеха создаются:

- `dist/Structura Edit.app`;
- `dist/Structura-Edit-macOS-arm64.zip`;
- `dist/build.json` с SHA-256 архива и wheels, версиями и результатом проверки;
- `dist/installation-check/` с JSON и снимками окон.

Для worker используется `multiprocessing.freeze_support()` до загрузки GUI,
как требует [PyInstaller для frozen multiprocessing](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#multi-processing).
Архив создаётся системным `ditto`, сохраняющим структуру `.app` и символические
ссылки, необходимые [пакетам PyInstaller на macOS](https://pyinstaller.org/en/stable/feature-notes.html#macos).

## Запуск и проверка переноса

Открыть `.app` двойным кликом или распаковать ZIP и переместить приложение в
выбранный каталог. Отдельно устанавливать Python не нужно. Для повторной
диагностики запустить бинарный файл внутри уже перемещённого пакета:

```bash
"/path/to/Structura Edit.app/Contents/MacOS/Structura Edit" --check-installation /private/tmp/structura-install-check
```

Команда возвращает ненулевой код при ошибке и пишет `result.json` с причиной.
В обычном запуске приложение использует стандартное локальное хранилище
редактора; временная изоляция применяется только к проверке установки.

## Граница поставки

Alpha-архив публикуется в GitHub Releases с ad hoc подписью. Developer ID и
notarization не настроены: Gatekeeper может блокировать скачанное приложение.
Проверка `codesign --verify` не заменяет notarization. Версия внутри `.app`
берётся из установленного wheel редактора, включая alpha-номер сборки.
Нативная проверка выполнена на macOS 26.6.2 / arm64; macOS 13 (минимум Qt 6.10.2) объявлена
минимальной платформой пакета, но отдельно не проверена. Intel Mac, Windows и
Linux требуют собственных сборок и проверок. Автопроверка установки охватывает
NBT, bundled demo и обзор Java-мира; полный набор конвертеров и запись мира
проверяются отдельно в тестах workspace. Версии Qt, VTK и meshoptimizer, результат
обзора и его контрольные кадры сохраняются в `installation-check/`.
