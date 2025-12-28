import os
import stat
import paramiko
import logging
from typing import Optional, Tuple, List

class SSHClientWrapper:
    """Профессиональная обертка над Paramiko для работы с удаленным сервером"""
    
    def __init__(self):
        self._client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None
        self.logger = logging.getLogger("SSHClient")

    def connect(self, host: str, port: int, user: str, password: str) -> Tuple[bool, str]:
        """Установка соединения"""
        try:
            self.disconnect()

            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self._client.connect(
                hostname=host,
                port=port,
                username=user,
                password=password,
                timeout=15,             # Таймаут на TCP соединение
                banner_timeout=30,      # Таймаут на чтение баннера (Критично для вашей ошибки!)
                auth_timeout=15,        # Таймаут на аутентификацию
                allow_agent=False,      # Отключаем агент, чтобы избежать лишних запросов
                look_for_keys=False     # Отключаем поиск ключей, если используем пароль
            )

            self._sftp = self._client.open_sftp()

            # Включаем KeepAlive, чтобы соединение не рвалось
            transport = self._client.get_transport()
            transport.set_keepalive(30)
            
            return True, "Connected successfully"
        except Exception as e:
            self.logger.error(f"Connection failed to {host}: {e}")
            return False, str(e)

    def disconnect(self):
        """Безопасное закрытие всех ресурсов"""
        try:
            if self._sftp:
                self._sftp.close()
                self._sftp = None
            if self._client:
                self._client.close()
                self._client = None
        except Exception:
            pass

    def execute(self, command: str) -> Tuple[int, str, str]:
        """Выполнение команды. Возвращает (exit_code, stdout, stderr)"""
        if not self._client:
            return -1, "", "Not connected"
            
        try:
            stdin, stdout, stderr = self._client.exec_command(command, timeout=30)
            exit_status = stdout.channel.recv_exit_status()
            return (
                exit_status,
                stdout.read().decode('utf-8', errors='ignore'),
                stderr.read().decode('utf-8', errors='ignore')
            )
        except Exception as e:
            self.logger.error(f"Exec error: {e}")
            return -1, "", str(e)
        
    def list_dir(self, remote_path: str) -> List[dict]:
        """Список файлов с деталями"""
        if not self._sftp:
            raise Exception("SFTP session is not open")
            
        files = []
        try:
            # Получаем список атрибутов файлов
            for attr in self._sftp.listdir_attr(remote_path):
                files.append({
                    'name': attr.filename,
                    'size': attr.st_size,
                    'is_dir': stat.S_ISDIR(attr.st_mode), # ИЗМЕНЕНО: надежный способ
                    'permissions': str(attr),
                    'mtime': attr.st_mtime
                })
        except Exception as e:
            self.logger.error(f"SFTP listdir error: {e}")
            raise e # Пробрасываем ошибку выше для воркера
            
        return files

    def download_file(self, remote_path: str, local_path: str):
        self._sftp.get(remote_path, local_path)

    def smart_upload(self, local_paths: List[str], remote_base_dir: str, progress_callback=None): # НОВОЕ
        """Универсальная загрузка: определяет файлы и папки и загружает их"""
        import os
        for path in local_paths:
            name = os.path.basename(path)
            remote_path = os.path.join(remote_base_dir, name).replace('\\', '/')
            
            if os.path.isdir(path):
                if progress_callback:
                    progress_callback(f"📂 Обработка папки: {name}")
                self.upload_folder(path, remote_path, progress_callback)
            else:
                if progress_callback:
                    progress_callback(f"📄 Загрузка файла: {name}")
                self.upload_file(path, remote_path)
        return True

    def upload_file(self, local_path: str, remote_path: str):
        self._sftp.put(local_path, remote_path)

    def upload_folder(self, local_dir: str, remote_dir: str, progress_callback=None):
        """Рекурсивная загрузка папки"""
        import os
        
        # Создаем целевую папку на сервере
        try:
            self._sftp.mkdir(remote_dir)
        except IOError:
            pass # Папка уже может существовать

        for root, dirs, files in os.walk(local_dir):
            # Вычисляем относительный путь для воссоздания структуры
            rel_path = os.path.relpath(root, local_dir)
            if rel_path == ".":
                target_dir = remote_dir
            else:
                target_dir = os.path.join(remote_dir, rel_path).replace('\\', '/')
                try:
                    self._sftp.mkdir(target_dir)
                except IOError:
                    pass

            for f in files:
                local_file = os.path.join(root, f)
                remote_file = os.path.join(target_dir, f).replace('\\', '/')
                if progress_callback:
                    progress_callback(f"📤 Загрузка: {f}")
                self._sftp.put(local_file, remote_file)

    def read_text_file(self, remote_path: str) -> str:
        """Чтение содержимого текстового файла в строку"""
        with self._sftp.open(remote_path, 'r') as f:
            return f.read().decode('utf-8', errors='ignore')

    def write_text_file(self, remote_path: str, content: str):
        """Запись строки в удаленный файл"""
        with self._sftp.open(remote_path, 'w') as f:
            f.write(content.encode('utf-8'))

    def remove_file(self, remote_path: str) -> Tuple[bool, str]:
        """Удаление файла или пустой директории"""
        try:
            self._sftp.remove(remote_path)
            return True, "File deleted"
        except Exception as e:
            try:
                self._sftp.rmdir(remote_path)
                return True, "Directory deleted"
            except:
                return False, str(e)

    @property
    def is_connected(self) -> bool:
        """Безопасная проверка активного соединения"""
        try:
            if self._client is None:
                return False
            
            transport = self._client.get_transport()
            # Проверяем, что транспорт существует и он активен
            return transport is not None and transport.is_active()
        except Exception:
            return False