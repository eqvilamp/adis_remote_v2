from typing import Dict, List, Optional, Tuple
from models.configs import ServiceConfig
from .ssh_client import SSHClientWrapper

class ServiceManager:
    """Логика управления сервисами Argus через SSH"""
    
    def __init__(self, ssh: SSHClientWrapper):
        self.ssh = ssh

    @staticmethod
    def _bash_lc_arg(command: str) -> str:
        # Quote for: bash -lc '<command>'
        return "'" + command.replace("'", "'\"'\"'") + "'"

    @staticmethod
    def _needs_shell(exec_start: str) -> bool:
        tokens = ["&&", "||", ";", "|", ">", "<", "$(", "`", "\n"]
        if exec_start.lstrip().startswith("cd "):
            return True
        return any(t in exec_start for t in tokens)

    @staticmethod
    def _shell_normalize_specifiers(command: str) -> str:
        # When running through bash -lc, use shell-native HOME expansion.
        return command.replace("%h", "$HOME")

    def get_status(self, service: ServiceConfig) -> bool:
        """Проверка запущен ли сервис (через системный менеджер или ps)"""
        # Сначала пробуем через systemctl (если юнит создан)
        unit_name = f"argus_{service.id}.service"
        code, out, _ = self.ssh.execute(f"systemctl --user is-active {unit_name}")
        
        if code == 0 and "active" in out:
            return True
            
        # Резервный вариант: поиск по process_name и конфигу в ps
        process_name = (service.process_name or "").strip()
        config_path = (service.config_path or "").strip()
        if not process_name:
            return False

        cmd = f"ps aux | grep -v grep | grep '{process_name}'"
        if config_path:
            cmd += f" | grep '{config_path}'"
        code, out, _ = self.ssh.execute(cmd)
        return code == 0 and out.strip() != ""
    
    def get_start_order(self, services: Dict[str, ServiceConfig]) -> List[str]:
        """Топологическая сортировка для определения порядка запуска"""
        order = []
        visited = set()
        temp_visited = set()

        def visit(s_id):
            if s_id in temp_visited:
                raise Exception(f"Циклическая зависимость обнаружена в {s_id}")
            if s_id not in visited:
                temp_visited.add(s_id)
                # Сначала посещаем тех, от кого зависим
                for dep in services[s_id].depends_on:
                    if dep in services:
                        visit(dep)
                temp_visited.remove(s_id)
                visited.add(s_id)
                order.append(s_id)

        for s_id in services:
            visit(s_id)
        return order
    
    def get_required_start_chain(self, target_id: str, services: Dict[str, ServiceConfig]) -> List[str]:
        """Вычисляет список ID сервисов, которые нужно запустить для работы target_id"""
        chain = []
        visited = set()

        def collect(s_id):
            if s_id in visited or s_id not in services:
                return
            visited.add(s_id)
            # Сначала собираем зависимости (те, кто ниже в иерархии)
            for dep_id in services[s_id].depends_on:
                collect(dep_id)
            chain.append(s_id)

        collect(target_id)
        return chain

    def get_required_stop_chain(self, target_id: str, services: Dict[str, ServiceConfig]) -> List[str]:
        """Вычисляет список ID сервисов, которые нужно остановить (реверс-зависимости)"""
        chain = []
        visited = set()

        # Строим карту обратных зависимостей: кто зависит от ключа
        reverse_deps = {s_id: [] for s_id in services}
        for s_id, cfg in services.items():
            for dep_id in cfg.depends_on:
                if dep_id in reverse_deps:
                    reverse_deps[dep_id].append(s_id)

        def collect(s_id):
            if s_id in visited:
                return
            visited.add(s_id)
            # Сначала собираем тех, кто зависит от нас (они должны лечь первыми)
            for dependent_id in reverse_deps.get(s_id, []):
                collect(dependent_id)
            chain.append(s_id)

        collect(target_id)
        return chain

    def start_service(self, service: ServiceConfig) -> Tuple[bool, str]:
        """Запуск сервиса через systemd --user"""
        unit_name = f"argus_{service.id}.service"
        # Для Astra Linux и подобных используем базовый путь из конфига узла
        # В реальной задаче base_dir лучше брать из NodeConfig, пока оставим как в примере
        base_dir = "/data/gazpromneft/ADIS"

        unit_type = (getattr(service, "unit_type", None) or "forking").strip()
        if unit_type not in {"forking", "simple", "oneshot"}:
            unit_type = "forking"

        working_dir = getattr(service, "working_directory", None) or base_dir
        exec_start = getattr(service, "exec_start", None)
        if exec_start:
            exec_start_str = str(exec_start).strip()
            if self._needs_shell(exec_start_str):
                exec_start_line = f"/bin/bash -lc {self._bash_lc_arg(self._shell_normalize_specifiers(exec_start_str))}"
            else:
                exec_start_line = exec_start_str
        else:
            exec_start_line = f"{service.binary_path} inifile={service.config_path} daemon=1"
        environment = getattr(service, "environment", None) or {}
        env_lines = ""
        if isinstance(environment, dict) and environment:
            env_lines = "".join(f"Environment={k}={v}\n" for k, v in environment.items())

        restart_block = "Restart=on-failure\nRestartSec=5\n"
        if unit_type == "oneshot":
            restart_block = "RemainAfterExit=yes\n"

        unit_content = f"""[Unit]
Description=Argus {service.name}
After=network.target

[Service]
Type={unit_type}
WorkingDirectory={working_dir}
{env_lines}ExecStart={exec_start_line}
{restart_block}
[Install]
WantedBy=default.target
"""
        unit_path = f"~/.config/systemd/user/{unit_name}"

        # Команда установки и запуска
        heredoc_tag = "ARGUS_UNIT"
        start_action = "restart"
        if unit_type == "oneshot":
            start_action = "start"

        setup_cmd = (
            f"mkdir -p ~/.config/systemd/user/ && "
            f"cat > {unit_path} <<'{heredoc_tag}'\n"
            f"{unit_content}"
            f"{heredoc_tag}\n"
            f"systemctl --user daemon-reload && "
            f"systemctl --user {start_action} {unit_name}"
        )

        code, out, err = self.ssh.execute(setup_cmd)
        if code != 0 and ("canceled" in (err or "").lower() or "canceled" in (out or "").lower()):
            code = 0
        if code == 0:
            return True, f"Сервис {service.name} запущен"
        else:
            return False, f"Ошибка {service.id}: {err or out}"

    def stop_service(self, service: ServiceConfig) -> Tuple[bool, str]:
        """Остановка сервиса"""
        # Пробуем через systemd
        unit_name = f"argus_{service.id}.service"
        unit_type = (getattr(service, "unit_type", None) or "forking").strip()

        if unit_type == "oneshot":
            cmd = (
                "bash -lc "
                + self._bash_lc_arg(
                    f"systemctl --user stop {unit_name} >/dev/null 2>&1 || true; "
                    f"systemctl --user reset-failed {unit_name} >/dev/null 2>&1 || true"
                )
            )
            self.ssh.execute(cmd)
            return True, "Service stopped"

        code, out, err = self.ssh.execute(f"systemctl --user stop {unit_name}")
        if code != 0 and ("canceled" in (err or "").lower() or "canceled" in (out or "").lower()):
            code = 0
        
        # Добиваем через pkill если завис (профессиональный подход - гарантированная очистка)
        config_path = (service.config_path or "").strip()
        if not config_path:
            if code == 0:
                return True, "Service stopped"
            return False, err or out or "Service stop failed"

        cmd = f"pkill -f '{config_path}'"
        code2, out2, err2 = self.ssh.execute(cmd)
        if code == 0 and code2 == 0:
            return True, "Service stopped"
        if code == 0:
            return True, "Service stopped"
        return False, (err or out or err2 or out2 or "Service stop failed")
    
    def diagnose_service(self, service: ServiceConfig) -> Dict[str, any]:
        """Детальная проверка бинарного файла и его окружения"""
        report = {
            "binary_exists": False,
            "executable": False,
            "missing_libs": [],
            "config_exists": False,
            "error": None
        }
        
        try:
            # 1. Проверка наличия бинарника
            code, out, _ = self.ssh.execute(f"test -f {service.binary_path} && echo 'OK'")
            report["binary_exists"] = (out.strip() == "OK")
            
            # 2. Проверка прав на выполнение
            code, out, _ = self.ssh.execute(f"test -x {service.binary_path} && echo 'OK'")
            report["executable"] = (out.strip() == "OK")
            
            # 3. Проверка зависимостей (LDD)
            # Команда ищет строки со стрелкой, где справа написано 'not found'
            ldd_cmd = f"ldd {service.binary_path} | grep 'not found' || true"
            code, out, _ = self.ssh.execute(ldd_cmd)
            if out.strip():
                report["missing_libs"] = [line.split('=>')[0].strip() for line in out.strip().split('\n')]
            
            # 4. Проверка конфига
            code, out, _ = self.ssh.execute(f"test -f {service.config_path} && echo 'OK'")
            report["config_exists"] = (out.strip() == "OK")
            
        except Exception as e:
            report["error"] = str(e)
            
        return report
