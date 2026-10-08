import sys
import threading
import subprocess
import importlib

def _ensure_gui_deps():
    try:
        importlib.import_module("customtkinter")
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "customtkinter", "pillow", "--quiet"])
        importlib.invalidate_caches()

_ensure_gui_deps()

import customtkinter as ctk
from main import start_satellite

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class AtenaAssistant(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("ATENA Assistant")
        self.geometry("320x450")
        self.attributes("-topmost", True)
        self.overrideredirect(True)
        
        self.bind("<ButtonPress-1>", self._start_move)
        self.bind("<B1-Motion>", self._do_move)

        self._build_ui()
        self._start_backend()

    def _start_move(self, event):
        self.x = event.x
        self.y = event.y

    def _do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.winfo_x() + deltax
        y = self.winfo_y() + deltay
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, corner_radius=0, fg_color="#1E1E1E")
        header.grid(row=0, column=0, sticky="ew")
        
        title = ctk.CTkLabel(header, text="ATENA SATELLITE", font=ctk.CTkFont(size=14, weight="bold"))
        title.pack(side="left", padx=10, pady=10)
        
        close_btn = ctk.CTkButton(header, text="X", width=30, height=30, fg_color="transparent", hover_color="#ff4444", command=self.destroy)
        close_btn.pack(side="right", padx=5)

        self.status_lbl = ctk.CTkLabel(self, text="● In ascolto...", text_color="#00FF00", font=ctk.CTkFont(size=12))
        self.status_lbl.grid(row=1, column=0, pady=5)

        self.chat_box = ctk.CTkTextbox(self, state="disabled", fg_color="#2B2B2B", wrap="word")
        self.chat_box.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")

        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.grid(row=3, column=0, padx=10, pady=10, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(input_frame, placeholder_text="Chiedi ad Atena...")
        self.entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.entry.bind("<Return>", lambda e: self._send_msg())

        send_btn = ctk.CTkButton(input_frame, text="Invia", width=60, command=self._send_msg)
        send_btn.grid(row=0, column=1)

        self._log_msg("Sistema", "Satellite Context Bridge avviato. ATENA ora può vedere il tuo schermo in sicurezza.")

    def _log_msg(self, sender: str, msg: str):
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{sender}: {msg}\n\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _send_msg(self):
        txt = self.entry.get().strip()
        if not txt: return
        self.entry.delete(0, "end")
        self._log_msg("Tu", txt)
        self.status_lbl.configure(text="● Elaborazione...", text_color="#FFA500")
        
        threading.Thread(target=self._mock_send, args=(txt,), daemon=True).start()

    def _mock_send(self, txt: str):
        import time
        time.sleep(1)
        self._log_msg("ATENA", "Ricevuto. (Nota: per farmi rispondere realmente devi collegare questo client alle API di chat del backend, attualmente il Satellite invia solo il contesto visivo.)")
        self.status_lbl.configure(text="● In ascolto...", text_color="#00FF00")

    def _start_backend(self):
        t = threading.Thread(target=start_satellite, daemon=True)
        t.start()

if __name__ == "__main__":
    app = AtenaAssistant()
    app.mainloop()
