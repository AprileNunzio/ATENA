import ast
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
FOREIGN = {"sandbox_broker", "installer_wizard", "client_satellite", "scripts", "native"}
HOST_SHELL = {"pty", "pexpect"}


def _sources():
    for path in SERVER.rglob("*.py"):
        if "tests" not in path.relative_to(SERVER).parts and "__pycache__" not in path.parts:
            yield path


GUARDS = {"ImportError", "ModuleNotFoundError", "Exception"}


def _guarded(handlers) -> bool:
    for handler in handlers:
        names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
        if any(isinstance(n, ast.Name) and n.id in GUARDS for n in names):
            return True
    return False


def _walk(node, guarded=False):
    if isinstance(node, ast.Try):
        inner = guarded or _guarded(node.handlers)
        for child in node.body:
            yield from _walk(child, inner)
        for child in node.handlers + node.orelse + node.finalbody:
            yield from _walk(child, guarded)
        return
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield node.lineno, alias.name.split(".")[0], guarded
    elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        yield node.lineno, node.module.split(".")[0], guarded
    for child in ast.iter_child_nodes(node):
        yield from _walk(child, guarded)


def _imports(path: Path):
    yield from _walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))


class BoundaryTest(unittest.TestCase):
    def test_core_never_imports_packages_missing_from_its_image(self):
        offenders = [f"{p.relative_to(ROOT)}:{line} → {name}" for p in _sources()
                     for line, name, guarded in _imports(p) if name in FOREIGN and not guarded]
        self.assertEqual(offenders, [], "the core image ships only server/: optional integrations must degrade on ImportError")

    def test_core_never_opens_a_shell_on_the_host(self):
        offenders = [f"{p.relative_to(ROOT)}:{line} → {name}" for p in _sources()
                     for line, name, _ in _imports(p) if name in HOST_SHELL]
        self.assertEqual(offenders, [], "untrusted commands must run inside the sandbox, never in a host terminal")


class ImageParityTest(unittest.TestCase):
    def test_kernel_composition_imports_from_a_server_only_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(SERVER, Path(tmp) / "server", ignore=shutil.ignore_patterns("tests", "__pycache__"))
            env = {**os.environ, "PYTHONPATH": tmp}
            result = subprocess.run([sys.executable, "-c", "import server.core.kernel.composition"],
                                    cwd=tmp, env=env, capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
