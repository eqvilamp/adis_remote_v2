from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QPlainTextEdit, QLabel)
from PyQt6.QtGui import QFont

class TextEditorDialog(QDialog):
    def __init__(self, filename: str, content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Редактор: {filename}")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        self.label = QLabel(f"Правка файла на сервере: {filename}")
        layout.addWidget(self.label)
        
        self.editor = QPlainTextEdit()
        # Используем моноширинный шрифт для конфигов
        self.editor.setFont(QFont("Consolas", 11) if self.is_windows() else QFont("Monospace", 11))
        self.editor.setPlainText(content)
        layout.addWidget(self.editor)
        
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("💾 Сохранить")
        self.btn_cancel = QPushButton("Отмена")
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)
        
        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def get_text(self) -> str:
        return self.editor.toPlainText()

    def is_windows(self):
        import platform
        return platform.system() == "Windows"