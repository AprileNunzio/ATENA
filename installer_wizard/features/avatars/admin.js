(() => {
  async function loadAvatars() {
    const res = await Atena.api.get("/api/avatars");
    const list = document.getElementById("avatars-list");
    list.innerHTML = "";
    for (const a of res.avatars) {
      const li = document.createElement("li");
      li.innerHTML = `<strong>${a.name}</strong> - File: ${a.files.join(", ")} <button class="wk-btn wk-btn-danger" data-del="${a.name}">Elimina</button>`;
      list.appendChild(li);
    }
  }

  Atena.on("panel:avatars", () => {
    loadAvatars();

    document.getElementById("avatar-btn-upload").onclick = async () => {
      const name = document.getElementById("avatar-new-name").value;
      const fileInput = document.getElementById("avatar-new-file");
      if (!name || fileInput.files.length === 0) return alert("Inserisci nome e seleziona un file");
      
      const formData = new FormData();
      formData.append("name", name);
      formData.append("file", fileInput.files[0]);

      try {
        await fetch("/api/avatars/upload", { method: "POST", body: formData, headers: { Authorization: `Bearer ${Atena.token}` } });
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
        await Atena.api.delete(`/api/avatars/${e.target.dataset.del}`);
        loadAvatars();
      }
    });
  });
})();
