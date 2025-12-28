import os
from typing import List
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QComboBox, QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QTextEdit, QLabel, QStatusBar, QMessageBox,
                             QTabWidget, QTreeWidget, QTreeWidgetItem, QFileDialog,
                             QMenu)
from PyQt6.QtCore import Qt, QTimer, QThreadPool
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent, QColor

from gui.editor_dialog import TextEditorDialog
from models.configs import NodeConfig, ServiceConfig
from core.ssh_client import SSHClientWrapper
from core.service_manager import ServiceManager
from core.worker import SSHTask
from utils.config_loader import ConfigLoader
from pathlib import Path

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Argus Remote Manager v2 (Pro)")
        self.resize(1100, 700)
        self.current_remote_path = ""
        
        # Backend компоненты
        self.ssh = SSHClientWrapper()
        self.service_manager = ServiceManager(self.ssh)
        self.threadpool = QThreadPool.globalInstance()
        
        # Данные
        self.nodes = []
        self.services = {}
        self.current_node: NodeConfig = None
        
        self.init_ui()
        self.load_initial_data()
        
        # Таймер для автообновления статусов
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.refresh_all_statuses)

    def init_ui(self):
        """Интерфейс с вкладками"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Верхняя панель (общая)
        top_layout = QHBoxLayout()
        self.node_selector = QComboBox()
        self.node_selector.currentIndexChanged.connect(self.on_node_changed)
        self.btn_connect = QPushButton("Подключиться")
        self.btn_connect.clicked.connect(self.toggle_connection)
        top_layout.addWidget(QLabel("Узел:"))
        top_layout.addWidget(self.node_selector)
        top_layout.addWidget(self.btn_connect)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # Вкладки
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Вкладка 1: Сервисы
        self.tab_services = QWidget()
        self.setup_services_tab()
        self.tabs.addTab(self.tab_services, "⚙️ Управление сервисами")

        # Вкладка 2: Файлы (SFTP)
        self.tab_files = QWidget()
        self.setup_files_tab()
        self.tabs.addTab(self.tab_files, "📁 Файловый менеджер")

        # Панель логов (внизу)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(120)
        self.log_output.setStyleSheet("background-color: #1e1e1e; color: #00ff00;")
        main_layout.addWidget(self.log_output)

    def setup_services_tab(self):
        layout = QVBoxLayout(self.tab_services)
        
        btn_bar = QHBoxLayout()
        self.btn_start_all = QPushButton("▶️ Запустить цепочку")
        self.btn_start_all.clicked.connect(self.start_all_chain)
        self.btn_stop_all = QPushButton("⏹️ Остановить всё")
        self.btn_stop_all.clicked.connect(self.stop_all_chain)
        btn_bar.addWidget(self.btn_start_all)
        btn_bar.addWidget(self.btn_stop_all)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Сервис", "Статус", "Зависимости", "Действия"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    def setup_files_tab(self): # ИЗМЕНЕНО
        layout = QVBoxLayout(self.tab_files)
        
        file_bar = QHBoxLayout()
        self.btn_file_up = QPushButton("⬅️ Назад")
        self.btn_file_up.clicked.connect(self.navigate_up)
        
        self.path_label = QLabel("/")
        self.path_label.setStyleSheet("font-weight: bold; color: #555;")

        file_bar.addWidget(self.btn_file_up)
        file_bar.addWidget(self.path_label)
        file_bar.addStretch()
        
        # ИЗМЕНЕНО: Кнопка загрузки теперь имеет меню
        self.btn_upload = QPushButton("📤 Загрузить...")
        upload_menu = QMenu(self)
        upload_menu.addAction("📄 Файл", self.upload_file_dialog)
        upload_menu.addAction("📁 Папку", self.upload_folder_dialog)
        self.btn_upload.setMenu(upload_menu)
        
        file_bar.addWidget(self.btn_upload)
        layout.addLayout(file_bar)

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["Имя", "Размер", "Права"])

        # Включаем поддержку Drag & Drop
        self.file_tree.setAcceptDrops(True)
        # Переопределяем методы прямо у объекта для лаконичности
        self.file_tree.dragEnterEvent = self.file_tree_dragEnterEvent
        self.file_tree.dropEvent = self.file_tree_dropEvent
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self.show_file_context_menu)
        self.file_tree.itemDoubleClicked.connect(self.on_file_double_clicked)
        layout.addWidget(self.file_tree)

    def create_action_buttons(self, s_id: str):
        """Создание виджета с кнопками управления для строки"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(5)

        btn_start = QPushButton("▶️")
        btn_start.setToolTip("Запустить")
        btn_start.setFixedWidth(40)
        btn_start.clicked.connect(lambda: self.run_service_task(s_id, "start"))

        btn_diag = QPushButton("🔍")
        btn_diag.setToolTip("Диагностика")
        btn_diag.clicked.connect(lambda: self.run_diagnosis_task(s_id))

        btn_stop = QPushButton("⏹️")
        btn_stop.setToolTip("Остановить")
        btn_stop.setFixedWidth(40)
        btn_stop.clicked.connect(lambda: self.run_service_task(s_id, "stop"))

        layout.addWidget(btn_start)
        layout.addWidget(btn_diag)
        layout.addWidget(btn_stop)
        layout.addStretch()
        return container

    def log(self, message: str):
        """Добавление записи в лог в интерфейсе"""
        self.log_output.append(message)

    def load_initial_data(self):
        """Загрузка списка узлов из YAML"""
        try:
            nodes_path = Path("app_config/nodes.yaml")
            self.nodes = ConfigLoader.load_nodes(nodes_path)
            for node in self.nodes:
                self.node_selector.addItem(node.name, node)
            self.log(f"Загружено узлов: {len(self.nodes)}")
        except Exception as e:
            self.log(f"Ошибка загрузки узлов: {e}")

    def on_node_changed(self, index):
        if index < 0: return
        self.current_node = self.node_selector.itemData(index)
        self.current_remote_path = self.current_node.base_working_dir
        self.path_label.setText(self.current_remote_path)
        self.log(f"📍 Выбран узел: {self.current_node.name}")
        
        services_path = Path(f"app_config/{self.current_node.services_file}")
        self.services = ConfigLoader.load_services(services_path)
        self.update_table_view()
        
        if self.ssh.is_connected:
            self.refresh_file_list()

    def update_table_view(self):
        """Отрисовка списка сервисов"""
        self.table.setRowCount(0)
        for s_id, service in self.services.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            name_item = QTableWidgetItem(service.name)
            name_item.setData(Qt.ItemDataRole.UserRole, s_id)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem("🔘 Ожидание..."))
            self.table.setItem(row, 2, QTableWidgetItem(", ".join(service.depends_on)))
            
            # Вставляем кнопки управления
            self.table.setCellWidget(row, 3, self.create_action_buttons(s_id))

    def toggle_connection(self):
        """Управление подключением"""
        if not self.ssh.is_connected:
            self.log(f"Подключение к {self.current_node.host}...")
            # Запускаем задачу подключения асинхронно
            # В данном примере для простоты пароль берем напрямую (потом из Crypto)
            task = SSHTask("Connect", self.ssh.connect, 
                           self.current_node.host, self.current_node.port, 
                           self.current_node.username, self.current_node.encrypted_password)
            task.signals.finished.connect(self.on_connect_finished)
            task.signals.error.connect(lambda n, e: self.log(f"Ошибка: {e}"))
            self.threadpool.start(task)
        else:
            self.ssh.disconnect()
            self.on_disconnect_ui()

    def on_connect_finished(self, name, result):
        success, message = result
        if success:
            self.log("✅ Успешно подключено")
            self.btn_connect.setText("Отключиться")
            self.btn_start_all.setEnabled(True)
            self.btn_stop_all.setEnabled(True)
            
            # Автоматически загружаем список файлов при входе
            self.refresh_file_list()
            
            self.monitor_timer.start(5000)
            self.refresh_all_statuses()
        else:
            QMessageBox.critical(self, "Ошибка SSH", message)

    def on_disconnect_ui(self):
        """Очистка UI при отключении"""
        self.log("🔌 Отключено")
        self.btn_connect.setText("Подключиться")
        
        # Управление кнопками без обращения к удаленному btn_refresh
        self.btn_start_all.setEnabled(False)
        self.btn_stop_all.setEnabled(False)
        
        self.monitor_timer.stop()
        self.table.setRowCount(0)
        self.file_tree.clear()
        self.update_table_view()

    def refresh_all_statuses(self):
        """Асинхронный опрос всех сервисов с защитой от потери связи"""
        if not self.ssh or not self.ssh.is_connected:
            # Если связь внезапно пропала, останавливаем мониторинг
            if self.monitor_timer.isActive():
                self.monitor_timer.stop()
                self.log("⚠️ Соединение потеряно. Мониторинг приостановлен.")
                self.on_disconnect_ui()
            return
        
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if not item: continue
            
            s_id = item.data(Qt.ItemDataRole.UserRole)
            if s_id in self.services:
                service = self.services[s_id]
                task = SSHTask(f"Status_{s_id}", self.service_manager.get_status, service)
                task.signals.finished.connect(self.on_status_received)
                # Важно: игнорируем ошибки статуса, чтобы не спамить в лог при лагах сети
                self.threadpool.start(task)

    def on_status_received(self, task_name, is_running):
        """Обновление ячейки статуса в таблице"""
        s_id = task_name.replace("Status_", "")
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == s_id:
                item = self.table.item(row, 1)
                if is_running:
                    item.setText("🟢 Работает")
                    item.setForeground(QColor("green"))
                else:
                    item.setText("🔴 Остановлен")
                    item.setForeground(QColor("red"))
                break

    # --- Логика группового управления ---

    def start_all_chain(self):
        """Запуск всех сервисов в правильном порядке"""
        try:
            order = self.service_manager.get_start_order(self.services)
            self.log(f"🔗 Запуск цепочки: {' -> '.join(order)}")
            
            def run_chain():
                for s_id in order:
                    self.service_manager.start_service(self.services[s_id])
                    import time
                    time.sleep(1.5) # Пауза для стабильности systemd
                return True

            task = SSHTask("Chain_Start", run_chain)
            task.signals.finished.connect(lambda: QTimer.singleShot(500, self.refresh_all_statuses))
            task.signals.finished.connect(lambda: self.log("🎯 Все сервисы в цепочке запущены"))
            self.threadpool.start(task)
        except Exception as e:
            self.log(f"❌ Ошибка: {e}")

    def stop_all_chain(self):
        """Остановка всех сервисов в обратном порядке"""
        order = self.service_manager.get_start_order(self.services)
        order.reverse()
        
        def run_stop_chain():
            for s_id in order:
                self.service_manager.stop_service(self.services[s_id])
            return True

        task = SSHTask("Chain_Stop", run_stop_chain)
        task.signals.finished.connect(lambda: self.log("🎯 Все сервисы остановлены"))
        self.threadpool.start(task)

    def run_service_task(self, s_id: str, action: str):
        """Интеллектуальный запуск/остановка одиночного сервиса с учетом цепочек"""
        if not self.ssh.is_connected:
            self.log("❌ Ошибка: Нет соединения с сервером")
            return

        # 1. Определяем последовательность действий
        if action == "start":
            chain = self.service_manager.get_required_start_chain(s_id, self.services)
            message_prefix = "Запуск цепочки"
        else:
            chain = self.service_manager.get_required_stop_chain(s_id, self.services)
            message_prefix = "Остановка цепочки"

        # 2. Логируем зависимости в основной лог (этот поток - GUI, тут можно)
        if len(chain) > 1:
            names_chain = [self.services[idx].name for idx in chain]
            self.log(f"🔗 {message_prefix}: {' -> '.join(names_chain)}")
            if action == "start":
                target_name = self.services[s_id].name
                deps = [self.services[d].name for d in self.services[s_id].depends_on]
                if deps:
                    self.log(f"ℹ️ Для запуска {target_name} необходимо запустить: {', '.join(deps)}")

        # 3. Определяем функцию, которая будет работать в фоне
        def execute_chain(progress_callback): # Добавлен аргумент для логирования
            for task_id in chain:
                svc = self.services[task_id]
                
                if action == "start":
                    # Проверяем статус перед запуском
                    if self.service_manager.get_status(svc):
                        progress_callback(f"⏭️ {svc.name} уже запущен, пропускаю...")
                        continue
                    
                    progress_callback(f"🚀 Запуск: {svc.name}...")
                    success, msg = self.service_manager.start_service(svc)
                    if not success:
                        # Возвращаем ошибку, чтобы прервать цепочку
                        return False, f"Критическая ошибка: {msg}. Цепочка прервана."
                    
                    import time
                    time.sleep(1.2) # Техническая пауза для стабилизации процесса
                
                else:
                    progress_callback(f"🛑 Остановка: {svc.name}...")
                    self.service_manager.stop_service(svc)
            
            return True, f"{'Запуск' if action == 'start' else 'Остановка'} завершена успешно"

        # 4. Создаем задачу. Передаем execute_chain как функцию.
        # В kwargs передаем callback, который SSHTask прокинет в функцию.
        task = SSHTask(f"Chain_{action}_{s_id}", execute_chain)
        
        # Настраиваем мост для логов: фоновая задача -> сигнал -> метод self.log
        task.signals.log.connect(self.log)

        # Подменяем аргументы запуска так, чтобы в progress_callback попал эмиттер сигнала
        task.args = (task.signals.log.emit,) 

        def on_finished(name, result):
            success, msg = result
            if success:
                self.log(f"🎯 {msg}")
            else:
                self.log(f"❌ {msg}")
                QMessageBox.warning(self, "Ошибка цепочки", msg)
            
            # Обновляем все статусы через секунду после завершения всех операций
            QTimer.singleShot(1000, self.refresh_all_statuses)

        task.signals.finished.connect(on_finished)
        task.signals.error.connect(lambda n, e: self.log(f"❌ Системная ошибка выполнения: {e}"))
        
        self.threadpool.start(task)

    # --- Логика диагностики ---

    def run_diagnosis_task(self, s_id: str):
        service = self.services[s_id]
        task = SSHTask(f"Diag_{s_id}", self.service_manager.diagnose_service, service)
        task.signals.finished.connect(self.show_diagnosis_result)
        self.threadpool.start(task)

    def show_diagnosis_result(self, name, report: dict):
        s_id = name.replace("Diag_", "")
        msg = f"📝 Результат диагностики [{self.services[s_id].name}]:\n\n"
        
        msg += f"• Файл бинарника: {'✅ Ок' if report['binary_exists'] else '❌ НЕ НАЙДЕН'}\n"
        msg += f"• Файл конфига: {'✅ Ок' if report['config_exists'] else '❌ НЕ НАЙДЕН'}\n"
        msg += f"• Права доступа: {'✅ Ок' if report['executable'] else '❌ Нет прав на выполнение'}\n"
        
        if report['missing_libs']:
            msg += f"\n‼️ КРИТИЧЕСКАЯ ОШИБКА: Отсутствуют библиотеки:\n"
            for lib in report['missing_libs']:
                msg += f"  - {lib}\n"
            msg += "\nРекомендация: Проверьте LD_LIBRARY_PATH или установите пакеты."
        elif report['binary_exists'] and report['executable']:
            msg += "\n✅ Все системные зависимости найдены."

        QMessageBox.information(self, "Диагностика", msg)

    # --- Логика файлового менеджера ---

    def refresh_file_list(self):
        """Запрос списка файлов с детальным логом"""
        if not self.ssh.is_connected:
            self.log("⚠️ Ошибка: Нет соединения для обновления файлов")
            return
            
        if not self.current_remote_path:
            self.current_remote_path = self.current_node.base_working_dir
            
        self.path_label.setText(self.current_remote_path)
        self.log(f"🔍 Запрос списка файлов в: {self.current_remote_path}...")
        
        task = SSHTask("ListDir", self.ssh.list_dir, self.current_remote_path)
        
        # Связываем сигналы
        task.signals.finished.connect(self.populate_file_tree)
        task.signals.error.connect(lambda name, err: self.log(f"❌ Ошибка SFTP ({name}): {err}"))
        task.signals.log.connect(self.log) # Напрямую выводим логи из задачи
        
        self.threadpool.start(task)

    def populate_file_tree(self, name, files: list):
        """Заполнение дерева файлов"""
        self.file_tree.clear()
        self.log(f"✅ Получено объектов: {len(files)}") 
        
        if not files:
            self.log("ℹ️ Папка пуста")
            return

        # Сортировка: сначала папки, потом файлы
        files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

        for f in files:
            from datetime import datetime
            dt = datetime.fromtimestamp(f['mtime']).strftime('%Y-%m-%d %H:%M')
            
            icon = "📁" if f['is_dir'] else "📄"
            size_str = f"{f['size'] / 1024:.1f} KB" if not f['is_dir'] else "[DIR]"
            
            item = QTreeWidgetItem([
                f"{icon} {f['name']}", 
                size_str, 
                f"{f['permissions']}"
            ])
            # Добавляем дату в подсказку или в четвертую колонку, если расширим
            item.setToolTip(0, f"Изменен: {dt}")
            self.file_tree.addTopLevelItem(item)

    def upload_file_dialog(self): # ИЗМЕНЕНО: поддержка мультивыбора
        """Загрузка файлов через диалог с поддержкой выбора нескольких элементов"""
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите файлы для загрузки")
        if files:
            self.run_smart_upload(files)

    def upload_folder_dialog(self):
        """Загрузка папки рекурсивно"""
        local_dir = QFileDialog.getExistingDirectory(self, "Выберите папку для загрузки")
        if local_dir:
            folder_name = os.path.basename(local_dir)
            remote_dir = os.path.join(self.current_remote_path, folder_name).replace('\\', '/')
            
            self.log(f"📂 Начало загрузки папки {folder_name}...")
            
            task = SSHTask("UploadFolder", self.ssh.upload_folder, local_dir, remote_dir)
            task.signals.log.connect(self.log)
            task.signals.finished.connect(lambda n, r: self.log(f"✅ Папка {folder_name} полностью загружена"))
            task.signals.finished.connect(lambda: self.refresh_file_list())
            task.signals.error.connect(lambda n, e: self.log(f"❌ Ошибка загрузки папки: {e}"))
            
            self.threadpool.start(task)

    def run_smart_upload(self, local_paths: List[str]):
        """Запуск асинхронной загрузки списка объектов"""
        count = len(local_paths)
        self.log(f"⏳ Начинаю загрузку объектов ({count})...")
        
        task = SSHTask("SmartUpload", self.ssh.smart_upload, local_paths, self.current_remote_path)
        task.signals.log.connect(self.log)
        
        def on_done(name, res):
            self.log(f"✅ Загрузка {count} объектов завершена")
            self.refresh_file_list()
            
        task.signals.finished.connect(on_done)
        task.signals.error.connect(lambda n, e: self.log(f"❌ Ошибка загрузки: {e}"))
        self.threadpool.start(task)

    # --- Логика навигации и редактора ---

    def refresh_file_list(self):
        if not self.ssh.is_connected: return
        self.path_label.setText(self.current_remote_path)
        task = SSHTask("ListDir", self.ssh.list_dir, self.current_remote_path)
        task.signals.finished.connect(self.populate_file_tree)
        self.threadpool.start(task)

    def navigate_up(self):
        """Переход на уровень выше"""
        self.current_remote_path = os.path.dirname(self.current_remote_path.rstrip('/'))
        if not self.current_remote_path: self.current_remote_path = "/"
        self.refresh_file_list()

    def on_file_double_clicked(self, item, column):
        """Двойной клик: вход в папку или редактирование файла"""
        name_with_icon = item.text(0)
        filename = name_with_icon.split(" ", 1)[1] # убираем иконку
        full_path = os.path.join(self.current_remote_path, filename).replace('\\', '/')

        if name_with_icon.startswith("📁"):
            self.current_remote_path = full_path
            self.refresh_file_list()
        else:
            # Если это файл - открываем редактор
            self.open_editor_task(full_path)

    def open_editor_task(self, remote_path: str):
        """Асинхронная загрузка контента для редактора"""
        self.log(f"Загрузка файла для правки: {remote_path}")
        task = SSHTask("ReadFile", self.ssh.read_text_file, remote_path)
        
        def launch_editor(name, content):
            dialog = TextEditorDialog(os.path.basename(remote_path), content, self)
            if dialog.exec():
                new_content = dialog.get_text()
                self.save_file_task(remote_path, new_content)
        
        task.signals.finished.connect(launch_editor)
        self.threadpool.start(task)

    def save_file_task(self, remote_path: str, content: str):
        """Асинхронное сохранение файла"""
        self.log(f"Сохранение изменений: {remote_path}...")
        task = SSHTask("WriteFile", self.ssh.write_text_file, remote_path, content)
        task.signals.finished.connect(lambda n, r: self.log(f"✅ Файл {remote_path} сохранен"))
        self.threadpool.start(task)

    # --- Контекстное меню файлов ---

    def show_file_context_menu(self, position):
        item = self.file_tree.itemAt(position)
        if not item: return

        menu = QMenu()
        edit_action = QAction("✏️ Редактировать", self)
        delete_action = QAction("🗑 Удалить", self)
        
        # Определяем путь
        name_with_icon = item.text(0)
        filename = name_with_icon.split(" ", 1)[1]
        full_path = os.path.join(self.current_remote_path, filename).replace('\\', '/')

        edit_action.triggered.connect(lambda: self.open_editor_task(full_path))
        delete_action.triggered.connect(lambda: self.confirm_delete_file(full_path))

        if not name_with_icon.startswith("📁"):
            menu.addAction(edit_action)
        menu.addAction(delete_action)
        menu.exec(self.file_tree.viewport().mapToGlobal(position))

    def confirm_delete_file(self, remote_path):
        reply = QMessageBox.question(self, "Удаление", f"Вы уверены, что хотите удалить {os.path.basename(remote_path)}?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            task = SSHTask("DeleteFile", self.ssh.remove_file, remote_path)
            task.signals.finished.connect(lambda n, r: self.refresh_file_list())
            self.threadpool.start(task)

    # --- Обработчики Drag & Drop ---

    def file_tree_dragEnterEvent(self, event: QDragEnterEvent):
        """Проверка: тащат ли нам файлы"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def file_tree_dropEvent(self, event: QDropEvent):
        """Обработка брошенных файлов/папок"""
        if not self.ssh.is_connected:
            self.log("⚠️ Сначала подключитесь к серверу!")
            return

        urls = event.mimeData().urls()
        local_paths = [url.toLocalFile() for url in urls]
        
        if local_paths:
            self.run_smart_upload(local_paths)