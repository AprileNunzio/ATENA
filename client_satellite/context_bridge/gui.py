import sys
import threading
import subprocess
import importlib
import socket
import urllib.request
import urllib.error
import json

def _ensure_gui_deps():
    try:
        importlib.import_module("customtkinter")
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "customtkinter", "pillow", "--quiet"])
        importlib.invalidate_caches()

_ensure_gui_deps()

import customtkinter as ctk
from main import start_satellite
from cryptography.fernet import Fernet
import os

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class AtenaAssistant(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("ATENA Satellite Client")
        self.geometry("380x520")
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
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, corner_radius=0, fg_color="#1E1E1E")
        header.grid(row=0, column=0, sticky="ew")
        
        title = ctk.CTkLabel(header, text="ATENA SATELLITE", font=ctk.CTkFont(size=14, weight="bold"))
        title.pack(side="left", padx=10, pady=10)
        
        close_btn = ctk.CTkButton(header, text="X", width=30, height=30, fg_color="transparent", hover_color="#ff4444", command=self.destroy)
        close_btn.pack(side="right", padx=5)

        # Sezione Auto-Associazione
        setup_frame = ctk.CTkFrame(self, fg_color="#2B2B2B")
        setup_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        
        ctk.CTkLabel(setup_frame, text="IP Server ATENA:", font=ctk.CTkFont(size=11)).grid(row=0, column=0, padx=5, pady=(5,0), sticky="w")
        self.f_server_ip = ctk.CTkEntry(setup_frame, placeholder_text="es. 192.168.1.100:8000", height=28)
        self.f_server_ip.grid(row=1, column=0, padx=5, pady=(0,5), sticky="ew")

        ctk.CTkLabel(setup_frame, text="Nome di questo PC:", font=ctk.CTkFont(size=11)).grid(row=0, column=1, padx=5, pady=(5,0), sticky="w")
        self.f_pc_name = ctk.CTkEntry(setup_frame, placeholder_text="es. UFFICIO-1", height=28)
        self.f_pc_name.grid(row=1, column=1, padx=5, pady=(0,5), sticky="ew")
        
        setup_frame.grid_columnconfigure(0, weight=1)
        setup_frame.grid_columnconfigure(1, weight=1)

        self.btn_connect = ctk.CTkButton(setup_frame, text="Associa", command=self._auto_register, fg_color="#0066cc", hover_color="#0052a3", height=28)
        self.btn_connect.grid(row=2, column=0, columnspan=2, padx=5, pady=10, sticky="ew")

        self.status_lbl = ctk.CTkLabel(self, text="● In attesa di associazione...", text_color="#FFA500", font=ctk.CTkFont(size=12, weight="bold"))
        self.status_lbl.grid(row=2, column=0, pady=5)

        self.chat_box = ctk.CTkTextbox(self, state="disabled", fg_color="#2B2B2B", wrap="word")
        self.chat_box.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")

        self._log_msg("Sistema", "Satellite Context Bridge avviato in background. Inserisci l'IP di ATENA e associa questo PC.")

    def _log_msg(self, sender: str, msg: str):
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{sender}: {msg}\n\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _auto_register(self):
        server_ip = self.f_server_ip.get().strip()
        pc_name = self.f_pc_name.get().strip()
        
        if not server_ip or not pc_name:
            self._log_msg("Errore", "Inserisci l'IP del Server e il Nome del PC.")
            return

        if not server_ip.startswith("http"):
            server_ip = f"http://{server_ip}"
            
        self.btn_connect.configure(state="disabled", text="Associazione...")
        
        # Genera PSK
        psk = Fernet.generate_key().decode()
        os.environ["ATENA_CONTEXT_PSK"] = psk
        
        # IP Locale
        local_ip = socket.gethostbyname(socket.gethostname())
        local_url = f"http://{local_ip}:19999"

        payload = {
            "name": pc_name,
            "protocol": "rest",
            "url": local_url,
            "api_key": psk
        }
        
        threading.Thread(target=self._send_register_request, args=(server_ip, payload), daemon=True).start()

    def _send_register_request(self, server_ip, payload):
        req = urllib.request.Request(
            f"{server_ip}/api/v1/computer-control/add",
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status in [200, 201]:
                    self.status_lbl.configure(text="● Associato ad ATENA", text_color="#00FF00")
                    self._log_msg("Sistema", f"Auto-Associazione completata! ATENA ora vede il PC a {payload['url']}.")
                    self.btn_connect.configure(text="Connesso", fg_color="#00aa00")
                else:
                    self._log_msg("Errore", f"Server ha risposto con codice {response.status}.")
                    self.btn_connect.configure(state="normal", text="Riprova")
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode('utf-8')
            self._log_msg("Errore", f"Impossibile associare: {err_msg}")
            self.btn_connect.configure(state="normal", text="Riprova")
        except Exception as e:
            self._log_msg("Errore", f"Connessione fallita: {str(e)}")
            self.btn_connect.configure(state="normal", text="Riprova")

    def _start_backend(self):
        # In ascolto sulla LAN: ATENA contatta il satellite su <ip-locale>:19999 (traffico cifrato con la PSK)
        t = threading.Thread(target=start_satellite, kwargs={"host": "0.0.0.0"}, daemon=True)
        t.start()

if __name__ == "__main__":
    app = AtenaAssistant()
    app.mainloop()
