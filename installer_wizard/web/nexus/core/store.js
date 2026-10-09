export function createStore(initial) {
  let state = { ...initial };
  const listeners = new Set();
  return {
    get: () => state,
    set(patch) {
      const next = { ...state, ...(typeof patch === "function" ? patch(state) : patch) };
      const changed = Object.keys(next).filter((key) => next[key] !== state[key]);
      if (!changed.length) return;
      state = next;
      listeners.forEach((fn) => fn(state, changed));
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}

export const store = createStore({
  user: null,
  level: "pilot",
  favorites: [],
  route: "home",
  link: true,
  snapshot: null,
});
