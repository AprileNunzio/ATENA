import { store } from "../../core/store.js";
import { Series } from "../../components/charts.js";

export const SERIES = { cpu: new Series(), mem: new Series(), disk: new Series(), temp: new Series() };
let lastTime = 0, tracking = false;

export function trackSystem() {
  if (tracking) return;
  tracking = true;
  store.subscribe((state, changed) => {
    const sys = state.snapshot?.system;
    if (!changed.includes("snapshot") || !sys || sys.time === lastTime) return;
    lastTime = sys.time;
    SERIES.cpu.push(sys.cpu_percent);
    SERIES.mem.push(sys.mem_percent);
    SERIES.disk.push(sys.disk_percent);
    if (sys.temperature != null) SERIES.temp.push(sys.temperature);
  });
}
