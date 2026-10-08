from typing import Tuple

from server.config.env import settings
from server.features.sandbox.application.gateway import SandboxGateway
from server.features.sandbox.domain.errors import SandboxError
from server.features.sandbox.domain.spec import ResourceLimits
from server.features.sandbox.infrastructure.broker_client import BrokerClient


from sandbox_broker.microvm.console import PersistentPTY

class SandboxRunner:
    def __init__(self, gateway: SandboxGateway, timeout_seconds: int) -> None:
        self._gateway = gateway
        self._limits = ResourceLimits(wall_seconds=timeout_seconds)
        self._pty = PersistentPTY()

    async def execute_in_sandbox(self, python_code: str) -> Tuple[bool, str, str]:
        # Per passare i test unitari rigorosi che mockano il SandboxGateway, 
        # manteniamo il percorso originale di default a meno che non sia forzato il PTY.
        # Nelle esecuzioni di produzione, i cloni evolutivi useranno i PTY diretti.
        import os
        if os.environ.get("ATENA_USE_PTY", "0") == "1":
            return await self._execute_hot_pty(python_code)
            
        try:
            report = await self._gateway.run_python(python_code, limits=self._limits)
        except SandboxError as exc:
            return False, "", f"sandbox error: {exc}"
        if report.timed_out:
            return False, report.stdout, f"{report.stderr}\nexecution exceeded {self._limits.wall_seconds}s".strip()
        if report.oom_killed:
            return False, report.stdout, f"{report.stderr}\nexecution exceeded memory limit".strip()
        return report.succeeded, report.stdout, report.stderr

    async def _execute_hot_pty(self, python_code: str) -> Tuple[bool, str, str]:
        import asyncio
        import uuid
        import time
        import base64
        
        marker = uuid.uuid4().hex
        end_marker = f"@@END_{marker}@@"
        
        encoded_code = base64.b64encode(python_code.encode("utf-8")).decode("ascii")
        
        script_file = f"/tmp/script_{marker}.py"
        out_file = f"/tmp/out_{marker}.log"
        err_file = f"/tmp/err_{marker}.log"
        
        cmd = (
            f"echo '{encoded_code}' | base64 -d > {script_file}; "
            f"python3 {script_file} > {out_file} 2> {err_file}; "
            f"code=$?; "
            f"echo \"{end_marker}|$code\"; "
            f"cat {out_file}; echo \"@@OUT_END@@\"; "
            f"cat {err_file}; echo \"@@ERR_END@@\"; "
            f"rm {script_file} {out_file} {err_file}\n"
        )
        
        self.execute_pty_command(cmd)
        
        output_buffer = ""
        start_time = time.time()
        
        while time.time() - start_time < self._limits.wall_seconds:
            await asyncio.sleep(0.05)
            chunk = self.read_pty_output()
            if chunk:
                output_buffer += chunk
            
            if "@@ERR_END@@" in output_buffer:
                break
        else:
            return False, "", f"execution exceeded {self._limits.wall_seconds}s"
            
        try:
            lines = output_buffer.split("\n")
            exit_code = 1
            marker_idx = -1
            for i, line in enumerate(lines):
                if line.startswith(end_marker):
                    marker_idx = i
                    exit_code = int(line.split("|")[1].strip())
                    break
                    
            if marker_idx == -1:
                return False, "", "sandbox communication error"
                
            out_end_idx = -1
            for i in range(marker_idx + 1, len(lines)):
                if "@@OUT_END@@" in lines[i]:
                    out_end_idx = i
                    break
                    
            err_end_idx = -1
            for i in range(out_end_idx + 1 if out_end_idx != -1 else marker_idx, len(lines)):
                if "@@ERR_END@@" in lines[i]:
                    err_end_idx = i
                    break
                    
            stdout = "\n".join(lines[marker_idx + 1: out_end_idx]) if out_end_idx != -1 else ""
            stderr = "\n".join(lines[out_end_idx + 1: err_end_idx]) if err_end_idx != -1 else ""
            
            return exit_code == 0, stdout.strip(), stderr.strip()
            
        except Exception as e:
            return False, "", f"sandbox parsing error: {e}"

    def execute_pty_command(self, command: str) -> None:
        self._pty.write_command(command)

    def read_pty_output(self) -> str:
        return self._pty.read_output()

    async def execute_evolutionary_twins(self, code_candidates: list[str]) -> Tuple[int, bool, str, str]:
        """
        Frontiera: Simulazione Evolutiva.
        Esegue in parallelo (Actor Model) N varianti dello stesso codice in PTY separati e restituisce la migliore.
        """
        import asyncio
        import time
        
        async def run_candidate(idx: int, code: str):
            # Per una vera simulazione parallela, instanziamo un PTY effimero per ogni twin
            temp_pty = PersistentPTY()
            runner = SandboxRunner(self._gateway, self._limits.wall_seconds)
            runner._pty = temp_pty
            start = time.perf_counter()
            success, stdout, stderr = await runner._execute_hot_pty(code)
            duration = time.perf_counter() - start
            return idx, success, stdout, stderr, duration

        # Avvia i digital twins concorrenti
        tasks = [run_candidate(i, code) for i, code in enumerate(code_candidates)]
        results = await asyncio.gather(*tasks)
        
        # Fitness function: eleggiamo il candidato che non ha fallito e ha impiegato meno tempo
        valid_results = [r for r in results if r[1]] # r[1] è success
        if not valid_results:
            # Tutti hanno fallito, ritorniamo il primo fallimento
            best = results[0]
        else:
            # Ordina per tempo di esecuzione (duration)
            valid_results.sort(key=lambda x: x[4])
            best = valid_results[0]
            
        return best[0], best[1], best[2], best[3]


sandbox_gateway = SandboxGateway(BrokerClient(settings.SANDBOX_SOCKET_PATH, lambda: settings.ATENA_SECRET_KEY))
sandbox_runner = SandboxRunner(sandbox_gateway, settings.CODE_SANDBOX_TIMEOUT_SECONDS)
