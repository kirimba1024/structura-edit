from PySide6.QtWidgets import QMainWindow, QStackedWidget, QWidget

from structura_edit.task_progress import TaskProgress, TaskProgressPanel


def test_progress_uses_one_status_row_and_does_not_move_the_view(qt_app):
    window = QMainWindow()
    window.setCentralWidget(QWidget())
    content = QStackedWidget()
    idle = QWidget()
    content.addWidget(idle)
    main, overview = TaskProgress(), TaskProgress()
    panel = TaskProgressPanel(content, (main, overview))
    content.addWidget(panel)
    panel.visibility_changed.connect(lambda visible: content.setCurrentWidget(panel if visible else idle))
    window.statusBar().addWidget(content, 1)
    window.resize(400, 200)
    window.show()
    qt_app.processEvents()
    viewport = window.centralWidget().geometry()
    try:
        for task in (main, overview):
            task.set_progress('Preparing scene', 12_345, 62_424)
            task.show()
        qt_app.processEvents()
        assert main.isVisible() and not overview.isVisible()
        assert main.requested and overview.requested
        assert content.currentWidget() is panel
        assert main.rect().contains(main.cancel.geometry())
        assert window.centralWidget().geometry() == viewport
        main.finish()
        assert overview.isVisible() and not main.isVisible()
        assert content.currentWidget() is panel
        overview.finish()
        assert content.currentWidget() is idle
        assert window.centralWidget().geometry() == viewport
    finally:
        window.close()


def test_short_task_cannot_show_after_finishing(qt_app):
    task = TaskProgress()
    task.start('Preparing scene', cancellable=False)
    assert task.delay.isActive() and not task.cancel.isEnabled()
    task.finish()
    assert not task.delay.isActive() and not task.requested and not task.isVisible()
