import secrets
import time
import logging
from typing import List
from server.core.agent_registry.interfaces import BaseAgent, AgentTaskRequest, AgentTaskResponse
from server.features.sysops_automation.ssh_executor import shell_executor, CommandExecutionRequest
from server.features.sysops_automation.smb_manager import smb_manager, SmbShareRequest
from server.features.sysops_automation.mysql_provisioner import mysql_provisioner, MySQLProvisionRequest
from server.features.sysops_automation.app_scaffolder import app_scaffolder, AppScaffoldRequest
from server.features.sysops_automation.proxmox_manager import proxmox_manager
from server.core.reasoning.react_loop import ReActLoop
from server.core.reasoning.self_critique import self_critique_engine
from server.shared.i18n.provider import global_translator

logger = logging.getLogger("atena.sysops_agent")

class SysOpsAutomationAgent(BaseAgent):
    def __init__(self) -> None:
        self._module_path = "features/sysops_automation"
        self._react = self._build_react_loop()

    @property
    def agent_id(self) -> str:
        return "agent_sysops_automation"

    @property
    def capabilities(self) -> List[str]:
        return [
            "debian_bash",
            "powershell_cmd",
            "ssh_remote",
            "smb_share_create",
            "mysql_db_provision",
            "app_scaffold",
            "proxmox_management",
            "react_reasoning",
            "self_critique"
        ]

    async def can_handle(self, request: AgentTaskRequest) -> float:
        if request.intent == "SYSOPS_AUTOMATION":
            return 0.95
        keywords = [
            "ssh", "powershell", "pwsh", "debian", "bash", "comando", "terminale",
            "smb", "samba", "cartella condivisa", "condividi",
            "mysql", "mariadb", "database", "crea app", "crea applicazione", "scaffold",
            "proxmox", "macchina virtuale", "vm", "lxc", "container proxmox", "hypervisor"
        ]
        lowered = request.raw_query.lower()
        match_count = sum(1 for k in keywords if k in lowered)
        if match_count > 0:
            return min(0.4 + (match_count * 0.2), 0.98)
        return 0.05

    async def execute(self, request: AgentTaskRequest) -> AgentTaskResponse:
        start_time = time.time()
        
        agent_context = global_translator.translate(self._module_path, "agent_context")
        
        # We inject a shared list to store widgets generated during this run
        self._current_widgets = []
        
        react_result = await self._react.run(
            task=request.raw_query,
            agent_context=agent_context,
        )

        default_answer = global_translator.translate(self._module_path, "default_answer")
        raw_answer = react_result.get("answer", default_answer)
        refined_answer = await self._refine_with_critique(request.raw_query, raw_answer)

        # Combine all widgets into one HTML payload if any were generated
        combined_widget_html = "".join(self._current_widgets) if self._current_widgets else None

        elapsed = (time.time() - start_time) * 1000
        return AgentTaskResponse(
            task_id=request.task_id,
            agent_id=self.agent_id,
            status="SUCCESS" if react_result.get("success") else "PARTIAL",
            result_data={
                "react_iterations": react_result.get("iterations", 0),
                "trajectory": react_result.get("trajectory", []),
                "widget_html": combined_widget_html
            },
            speech_output=refined_answer,
            execution_time_ms=elapsed
        )

    def _build_react_loop(self) -> ReActLoop:
        loop = ReActLoop(max_iterations=6, model_name="qwen2.5-coder:7b", component="sysops_agent")

        async def run_shell_command(shell_type: str, command: str) -> str:
            res = await shell_executor.execute_command(
                CommandExecutionRequest(shell_type=shell_type, command=command)
            )
            return f"EXIT_CODE: {res.exit_code}\nSTDOUT: {res.stdout[:1000]}\nSTDERR: {res.stderr[:1000]}"

        async def create_smb_share(share_name: str, directory_path: str) -> str:
            success = await smb_manager.create_or_update_share(
                SmbShareRequest(share_name=share_name, directory_path=directory_path)
            )
            return "SUCCESS" if success else "FAILED"

        async def provision_mysql(database_name: str, username: str) -> str:
            password = secrets.token_urlsafe(18)
            success = await mysql_provisioner.provision_database(
                MySQLProvisionRequest(database_name=database_name, username=username, password=password)
            )
            return f"SUCCESS password={password}" if success else "FAILED"

        async def scaffold_app(app_name: str, target_directory: str) -> str:
            success = await app_scaffolder.scaffold_application(
                AppScaffoldRequest(app_name=app_name, template_type="fastapi", target_directory=target_directory)
            )
            return "SUCCESS" if success else "FAILED"
            
        async def query_proxmox(method: str, path: str, data: str = "") -> str:
            import json
            payload = None
            if data:
                try:
                    payload = json.loads(data)
                except Exception:
                    pass
            res = await proxmox_manager.execute_api_call(method, path, payload)
            return json.dumps(res, indent=2)
            
        async def render_html_widget(title: str, html_body: str) -> str:
            if not hasattr(self, '_current_widgets'):
                self._current_widgets = []
            
            # Using Tailwind CSS as per UI capabilities
            widget = f'''
            <div class="bg-[var(--card)] text-[var(--foreground)] border border-[var(--border)] rounded-xl p-5 shadow-sm my-2">
                <h2 class="text-[var(--foreground)] font-semibold text-lg border-b border-[var(--border)] pb-2 mb-3">{title}</h2>
                <div>{html_body}</div>
            </div>
            '''
            self._current_widgets.append(widget)
            return "Widget mostrato con successo."

        tool_shell = global_translator.translate(self._module_path, "tools.run_shell_command")
        loop.register_tool("run_shell_command", tool_shell, run_shell_command)
        
        tool_smb = global_translator.translate(self._module_path, "tools.create_smb_share")
        loop.register_tool("create_smb_share", tool_smb, create_smb_share)
        
        tool_mysql = global_translator.translate(self._module_path, "tools.provision_mysql")
        loop.register_tool("provision_mysql", tool_mysql, provision_mysql)
        
        tool_scaffold = global_translator.translate(self._module_path, "tools.scaffold_app")
        loop.register_tool("scaffold_app", tool_scaffold, scaffold_app)
        
        loop.register_tool(
            "query_proxmox", 
            "Esegue una chiamata API REST a Proxmox. Usa metodo (GET/POST/ecc), path (es. nodes/pve/qemu) e opzionalmente dati JSON.", 
            query_proxmox
        )
        
        loop.register_tool(
            "render_html_widget",
            "Crea e mostra un widget HTML (tabelle, metriche, grafici) all'utente. Utile per mostrare stato di salute, dati strutturati o dashboard di Proxmox. Fornisci un titolo e codice HTML (usa Tailwind CSS per stile).",
            render_html_widget
        )

        return loop

    async def _refine_with_critique(self, task: str, answer: str) -> str:
        try:
            critique_task = global_translator.translate(self._module_path, "critique_task", task=task)
            return await self_critique_engine.critique_and_refine(
                task=critique_task,
                draft_output=answer,
                max_refinements=1,
                quality_threshold=8,
            )
        except Exception as exc:
            msg = global_translator.translate(self._module_path, "errors.critique_failed", exc=exc)
            logger.warning(msg)
            return answer
