import yaml
from pathlib import Path
from typing import List, Dict
from models.configs import NodeConfig, ServiceConfig

class ConfigLoader:
    """Утилита для работы с YAML конфигурациями"""

    @staticmethod
    def load_nodes(file_path: Path) -> List[NodeConfig]:
        """Загрузка списка узлов"""
        if not file_path.exists():
            return []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or []
            return [NodeConfig(**item) for item in data]

    @staticmethod
    def load_services(file_path: Path) -> Dict[str, ServiceConfig]:
        """Загрузка сервисов из YAML"""
        if not file_path.exists():
            return {}
            
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            services_data = data.get('services', {})
            return {s_id: ServiceConfig(id=s_id, **s_data) 
                    for s_id, s_data in services_data.items()}

    @staticmethod
    def save_nodes(file_path: Path, nodes: List[NodeConfig]):
        """Сохранение узлов в YAML"""
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump([n.model_dump() for n in nodes], f, allow_unicode=True)