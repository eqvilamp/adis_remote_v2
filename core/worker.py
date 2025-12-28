from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, pyqtSlot

class WorkerSignals(QObject):
    """Сигналы для передачи результатов из потока в GUI"""
    finished = pyqtSignal(str, object)  # task_name, result
    error = pyqtSignal(str, str)        # task_name, error_msg
    log = pyqtSignal(str)               # сообщение для лога

class SSHTask(QRunnable):
    """Общая задача для выполнения действий по SSH в фоне"""
    
    def __init__(self, task_name: str, func, *args, **kwargs):
        super().__init__()
        self.task_name = task_name
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            self.signals.log.emit(f"Starting task: {self.task_name}...")
            result = self.func(*self.args, **self.kwargs)
            self.signals.finished.emit(self.task_name, result)
        except Exception as e:
            self.signals.error.emit(self.task_name, str(e))