import sys
import logging
from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow

DARK_STYLE = """
QMainWindow { background-color: #2b2b2b; }
QTableWidget { 
    background-color: #333333; 
    color: #efefef; 
    gridline-color: #444; 
    border: none;
}
QHeaderView::section {
    background-color: #444;
    color: white;
    padding: 4px;
    border: 1px solid #555;
}
QTextEdit { 
    background-color: #1e1e1e; 
    color: #00ff00; 
    border: 1px solid #444; 
}
QPushButton { 
    background-color: #444; 
    color: white; 
    border: 1px solid #555; 
    padding: 5px 15px;
    border-radius: 3px;
}
QPushButton:hover { background-color: #555; }
QPushButton:pressed { background-color: #2e7d32; }
QTabWidget::pane { border: 1px solid #444; }
QTabBar::tab {
    background: #333;
    color: #bbb;
    padding: 10px 20px;
}
QTabBar::tab:selected {
    background: #444;
    color: white;
    border-bottom: 2px solid #2e7d32;
}
"""

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("app.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )

if __name__ == "__main__":
    setup_logging()
    app = QApplication(sys.argv)
    
    # Применяем темную тему (базовая настройка)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())