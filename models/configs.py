from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class ServiceConfig(BaseModel):
    """Конфигурация отдельного сервиса Argus"""
    id: str
    name: str
    binary_path: str
    config_path: str
    process_name: str
    exec_start: Optional[str] = None
    working_directory: Optional[str] = None
    unit_type: str = "forking"  # forking|simple|oneshot
    environment: Dict[str, str] = Field(default_factory=dict)
    # Зависимости по ID других сервисов
    depends_on: List[str] = Field(default_factory=list)
    # Команда для проверки (если не стандартная через systemd)
    custom_check_cmd: Optional[str] = None

class NodeConfig(BaseModel):
    """Конфигурация удаленного узла (сервера)"""
    id: str
    name: str
    host: str
    port: int = 22
    username: str
    # Пароль будет храниться в зашифрованном виде (base64)
    encrypted_password: str
    # Путь к файлу с описанием сервисов для этого узла
    services_file: str = "services.yaml"
    base_working_dir: str = "/data/gazpromneft/ADIS"

class AppSettings(BaseModel):
    """Глобальные настройки приложения"""
    last_node_id: Optional[str] = None
    theme: str = "dark"
    monitoring_interval_ms: int = 5000
