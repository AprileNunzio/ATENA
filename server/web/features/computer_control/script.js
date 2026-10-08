const API_BASE = '/api/v1/computer-control';

const UI = {
    openModal: () => {
        document.getElementById('add-modal').classList.remove('hidden');
        UI.toggleFormFields();
    },
    closeModal: () => {
        document.getElementById('add-modal').classList.add('hidden');
        document.getElementById('add-form').reset();
    },
    toggleFormFields: () => {
        const proto = document.getElementById('f-protocol').value;
        const gIp = document.getElementById('group-ip');
        const gPwd = document.getElementById('group-pwd');
        const gKey = document.getElementById('group-key');
        const gRest = document.getElementById('group-rest');

        gIp.classList.add('hidden');
        gPwd.classList.add('hidden');
        gKey.classList.add('hidden');
        gRest.classList.add('hidden');

        if (proto === 'winrm') {
            gIp.classList.remove('hidden');
            gPwd.classList.remove('hidden');
        } else if (proto.includes('ssh')) {
            gIp.classList.remove('hidden');
            gKey.classList.remove('hidden');
        } else if (proto === 'rest') {
            gRest.classList.remove('hidden');
        }
    },
    showAlert: (title, message, isError = false) => {
        const al = document.getElementById('global-alert');
        const icon = document.getElementById('alert-icon');
        document.getElementById('alert-title').innerText = title;
        document.getElementById('alert-message').innerText = message;
        
        al.className = `fixed bottom-4 right-4 max-w-sm w-full bg-white shadow-lg rounded-lg border-l-4 p-0 transform transition-all duration-300 ${isError ? 'border-red-500' : 'border-green-500'}`;
        icon.innerHTML = isError ? '<i class="fas fa-exclamation-circle text-red-500 text-xl"></i>' : '<i class="fas fa-check-circle text-green-500 text-xl"></i>';
        
        al.classList.remove('hidden');
        setTimeout(() => UI.hideAlert(), 5000);
    },
    hideAlert: () => {
        document.getElementById('global-alert').classList.add('hidden');
    },
    renderGrid: (computers) => {
        const grid = document.getElementById('computers-grid');
        grid.innerHTML = '';
        
        if (Object.keys(computers).length === 0) {
            grid.innerHTML = `<div class="col-span-full text-center py-12 bg-white rounded-xl shadow-sm border border-gray-100"><i class="fas fa-desktop text-4xl text-gray-300 mb-3"></i><p class="text-gray-500">Nessun computer configurato nella rete.</p></div>`;
            return;
        }

        for (const [name, conf] of Object.entries(computers)) {
            let icon = 'fa-desktop';
            let color = 'text-gray-600';
            
            if (conf.protocol.includes('win')) { icon = 'fa-windows'; color = 'text-blue-500'; }
            else if (conf.protocol.includes('mac')) { icon = 'fa-apple'; color = 'text-gray-800'; }
            else if (conf.protocol.includes('linux') || conf.protocol.includes('rhel')) { icon = 'fa-linux'; color = 'text-yellow-600'; }
            else if (conf.protocol === 'rest') { icon = 'fa-satellite-dish'; color = 'text-purple-500'; }

            const card = document.createElement('div');
            card.className = 'bg-white rounded-xl shadow-sm hover:shadow-md transition-shadow border border-gray-200 overflow-hidden flex flex-col';
            card.innerHTML = `
                <div class="p-5 border-b border-gray-100 flex justify-between items-start bg-gray-50">
                    <div class="flex items-center space-x-3">
                        <div class="p-2 bg-white rounded-lg shadow-sm border border-gray-100"><i class="fab ${icon} text-xl ${color}"></i></div>
                        <div>
                            <h3 class="font-bold text-gray-900">${name}</h3>
                            <p class="text-xs text-gray-500 uppercase tracking-wider">${conf.protocol}</p>
                        </div>
                    </div>
                    <button onclick="App.removeComputer('${name}')" class="text-red-400 hover:text-red-600 transition-colors" title="Rimuovi"><i class="fas fa-trash-alt"></i></button>
                </div>
                <div class="p-5 flex-1 space-y-3">
                    ${conf.ip ? `<div class="flex justify-between text-sm"><span class="text-gray-500">IP</span><span class="font-mono text-gray-900">${conf.ip}</span></div>` : ''}
                    ${conf.url ? `<div class="flex justify-between text-sm"><span class="text-gray-500">URL</span><span class="font-mono text-gray-900 truncate ml-2">${conf.url}</span></div>` : ''}
                    ${conf.username ? `<div class="flex justify-between text-sm"><span class="text-gray-500">User</span><span class="font-mono text-gray-900">${conf.username}</span></div>` : ''}
                    
                    <div id="status-${name}" class="mt-4 pt-4 border-t border-gray-100 flex items-center text-sm text-gray-500">
                        <i class="fas fa-circle text-gray-300 text-[10px] mr-2"></i> Stato sconosciuto
                    </div>
                </div>
                <div class="px-5 py-3 bg-gray-50 border-t border-gray-100 flex justify-between">
                    <button onclick="App.syncComputer('${name}')" class="text-sm text-blue-600 hover:text-blue-800 font-medium flex items-center">
                        <i class="fas fa-sync-alt mr-2" id="sync-icon-${name}"></i> PING / SYNC
                    </button>
                </div>
            `;
            grid.appendChild(card);
        }
    }
};

const App = {
    loadComputers: async () => {
        try {
            const res = await fetch(`${API_BASE}/list`);
            const json = await res.json();
            if (json.status === 'success') {
                UI.renderGrid(json.data);
            }
        } catch (e) {
            UI.showAlert('Errore di Rete', 'Impossibile caricare i dispositivi.', true);
        }
    },
    handleAdd: async (e) => {
        e.preventDefault();
        const payload = {
            name: document.getElementById('f-name').value,
            protocol: document.getElementById('f-protocol').value,
            ip: document.getElementById('f-ip').value,
            url: document.getElementById('f-url').value,
            username: document.getElementById('f-user').value,
            password: document.getElementById('f-pwd').value,
            key_path: document.getElementById('f-key').value,
            api_key: document.getElementById('f-apikey').value
        };

        try {
            const res = await fetch(`${API_BASE}/add`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const json = await res.json();
            if (res.ok && json.status === 'success') {
                UI.closeModal();
                UI.showAlert('Successo', json.message);
                App.loadComputers();
            } else {
                UI.showAlert('Errore', json.detail || json.message, true);
            }
        } catch (e) {
            UI.showAlert('Errore', 'Impossibile salvare il dispositivo.', true);
        }
    },
    removeComputer: async (name) => {
        if (!confirm(`Vuoi davvero rimuovere ${name}?`)) return;
        try {
            const res = await fetch(`${API_BASE}/remove/${name}`, { method: 'DELETE' });
            if (res.ok) {
                UI.showAlert('Rimosso', `Dispositivo ${name} rimosso.`);
                App.loadComputers();
            }
        } catch (e) {
            UI.showAlert('Errore', 'Impossibile rimuovere.', true);
        }
    },
    syncComputer: async (name) => {
        const icon = document.getElementById(`sync-icon-${name}`);
        const statusDiv = document.getElementById(`status-${name}`);
        icon.classList.add('fa-spin');
        statusDiv.innerHTML = `<i class="fas fa-circle text-blue-400 text-[10px] mr-2 animate-pulse"></i> Sincronizzazione in corso...`;

        try {
            const res = await fetch(`${API_BASE}/sync/${name}`, { method: 'POST' });
            const json = await res.json();
            icon.classList.remove('fa-spin');
            
            if (json.status === 'success') {
                statusDiv.innerHTML = `<i class="fas fa-circle text-green-500 text-[10px] mr-2"></i> Online & Sincronizzato`;
                UI.showAlert('Sync OK', `Connessione a ${name} stabilita.`);
            } else {
                statusDiv.innerHTML = `<i class="fas fa-circle text-red-500 text-[10px] mr-2"></i> Offline / Errore`;
                UI.showAlert('Errore Sync', json.message || 'Host irraggiungibile.', true);
            }
        } catch (e) {
            icon.classList.remove('fa-spin');
            statusDiv.innerHTML = `<i class="fas fa-circle text-red-500 text-[10px] mr-2"></i> Errore di rete`;
        }
    }
};

document.addEventListener('DOMContentLoaded', App.loadComputers);
