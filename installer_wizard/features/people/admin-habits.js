(() => {
  const A = window.AtenaAdmin, { fmt } = A;
  const DAYS = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];

  function habitsSection(p) {
    const h = p.habits || { arrival_hours: [0]*24, weekdays: [0]*7, summary: "Nessuna abitudine registrata." };
    const maxH = Math.max(1, ...(h.arrival_hours || [1]));
    const maxD = Math.max(1, ...(h.weekdays || [1]));
    return `<div style="font-size:14px; margin-bottom:14px">${fmt.esc(h.summary)}</div>
        <div class="grid g2"><div><label>Orari di arrivo</label><div class="chart">${(h.arrival_hours || []).map((v) => `<i style="height:${(v / maxH) * 100}%" title="${v}"></i>`).join("")}</div><div class="chart-lbl"><span>0</span><span>6</span><span>12</span><span>18</span><span>23</span></div></div>
        <div><label>Giorni della settimana</label><div class="chart">${(h.weekdays || []).map((v) => `<i style="height:${(v / maxD) * 100}%" title="${v}"></i>`).join("")}</div><div class="chart-lbl">${DAYS.map((d) => `<span>${d}</span>`).join("")}</div></div></div>
        <div class="muted-note">${p.stats ? p.stats.visits : 0} visite · ${fmt.duration(p.stats ? p.stats.total_seconds : 0)} di presenza · prima volta ${p.stats && p.stats.first_seen ? new Date(p.stats.first_seen * 1000).toLocaleDateString("it-IT") : "—"}</div>`;
  }

  A.PeopleHabits = { section: habitsSection };
})();
