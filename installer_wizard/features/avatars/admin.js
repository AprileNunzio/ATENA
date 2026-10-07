(() => {
  const A = window.AtenaAdmin;

  async function loadAvatars() {
    const res = await A.api("GET", "/api/avatars");
    const list = document.getElementById("avatars-list");
    list.innerHTML = "";
    for (const a of res.avatars) {
      const isActive = a.name === res.active;
      const li = document.createElement("li");
      li.innerHTML = `<strong>${a.name}</strong> ${isActive ? "(ATTIVO)" : ""} - File: ${a.files.join(", ")} 
        <button class="btn sm" data-set="${a.name}" ${isActive ? "disabled" : ""}>Attiva</button>
        <button class="btn sm danger" data-del="${a.name}">Elimina</button>`;
      list.appendChild(li);
    }
  }

  function init() {
    document.getElementById("avatar-btn-upload").onclick = async () => {
      const name = document.getElementById("avatar-new-name").value;
      const fileInput = document.getElementById("avatar-new-file");
      if (!name || fileInput.files.length === 0) return alert("Inserisci nome e seleziona un file");
      
      const formData = new FormData();
      formData.append("name", name);
      formData.append("file", fileInput.files[0]);

      try {
        await fetch("/api/avatars/upload", { method: "POST", body: formData });
        document.getElementById("avatar-new-name").value = "";
        fileInput.value = "";
        loadAvatars();
      } catch (err) {
        alert("Errore durante l'upload");
      }
    };

    document.getElementById("avatars-list").addEventListener("click", async (e) => {
      if (e.target.dataset.del) {
        if (!confirm(`Vuoi davvero eliminare l'avatar ${e.target.dataset.del}?`)) return;
        await A.api("DELETE", `/api/avatars/${e.target.dataset.del}`);
        loadAvatars();
      }
      if (e.target.dataset.set) {
        await A.api("POST", `/api/avatars/active`, {name: e.target.dataset.set});
        loadAvatars();
      }
    });

    document.getElementById("avatar-btn-reset").onclick = async () => {
      await A.api("POST", `/api/avatars/active`, {name: ""});
      loadAvatars();
    };
  }

  A.tab("avatars", { title: "Ologrammi e Avatar 3D", init, load: loadAvatars });
})();
