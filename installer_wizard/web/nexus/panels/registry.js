const PANELS = Object.freeze({
  overview: () => import("./system/overview.js"),
  updates: () => import("./system/updates.js"),
  config: () => import("./system/config.js"),
  logs: () => import("./system/logs.js"),
  events: () => import("./system/events.js"),
  steps: () => import("./system/steps.js"),
  packages: () => import("./system/packages.js"),
});

export const hasPanel = (id) => Object.hasOwn(PANELS, id);
export const loadPanel = (id) => PANELS[id]();
export const panelIds = () => Object.keys(PANELS);
