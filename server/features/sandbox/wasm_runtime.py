import logging
from server.shared.i18n.provider import global_translator

log = logging.getLogger("atena.sandbox.wasm")

try:
    import wasmtime
    HAS_WASM = True
except ImportError:
    HAS_WASM = False

class WasmSandbox:
    def __init__(self):
        self._module_path = "features/sandbox"
        if HAS_WASM:
            self.engine = wasmtime.Engine()
            self.store = wasmtime.Store(self.engine)
            self.wasi = wasmtime.WasiConfig()
            self.wasi.inherit_stdout() 
            self.store.set_wasi(self.wasi)
        else:
            self.engine = None
            msg = global_translator.translate(self._module_path, "errors.wasm_missing")
            log.warning(msg)

    def execute_plugin(self, wasm_binary: bytes, entrypoint: str = "run", payload: dict = None):
        if not HAS_WASM:
            msg = global_translator.translate(self._module_path, "errors.wasm_unavailable")
            raise RuntimeError(msg)
        
        module = wasmtime.Module(self.engine, wasm_binary)
        linker = wasmtime.Linker(self.engine)
        linker.define_wasi()
        
        instance = linker.instantiate(self.store, module)
        instance.exports(self.store)[entrypoint]
        return True

wasm_runtime = WasmSandbox()
