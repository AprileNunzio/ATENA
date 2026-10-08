(function (J) {
  "use strict";
  const C = (J.Char = J.Char || {});
  const S = Math.sin, A = Math.abs;
  const mix = (a, b, k) => a.map((v, i) => v + (b[i] - v) * k);
  const ramp = (t, a, b) => Math.max(0, Math.min(1, (t - a) / (b - a)));

  const POSES = {
    saluto: { hands: 1, dur: 2.6, fn: (t) => ({
      main: [[0.62, 0.68, 0.22], [0.22 * S(t * 10), 1, 0.12]], curl: { main: 0.05 },
      turns: [["spine", 0, 0, -0.04]] }) },
    pensa: { hands: 2, loop: true, fn: (t) => ({
      main: [[0.12, -0.78, 0.6], [-0.42, 0.85, 0.36]], other: [[0.12, -0.92, 0.36], [-0.86, 0.06, 0.55]],
      curl: { main: 0.55, other: 0.3 }, turns: [["spine", 0.04, 0, 0.02 * S(t * 0.6)]] }) },
    spiega_a: { hands: 2, dur: 1.9, fn: (t) => ({
      main: [[0.22, -0.88, 0.38], [0.32 + 0.12 * S(t * 4), 0.08, 1]], other: [[0.22, -0.88, 0.38], [0.32 + 0.12 * S(t * 4 + 1), 0.04, 1]],
      curl: { main: 0.15, other: 0.15 } }) },
    spiega_b: { hands: 1, dur: 1.7, fn: (t) => ({
      main: [[0.26, -0.82, 0.48], [0.12 + 0.18 * S(t * 3.5), 0.38, 1]], curl: { main: 0.2 } }) },
    spiega_c: { hands: 2, dur: 1.8, fn: (t) => ({
      main: [[0.3, -0.86, 0.32], [0.78, 0.14 + 0.08 * S(t * 5), 0.62]], other: [[0.3, -0.86, 0.32], [0.78, 0.14 + 0.08 * S(t * 5), 0.62]],
      curl: { main: 0.1, other: 0.1 }, turns: [["spine", -0.03, 0, 0]] }) },
    mani_fianchi: { hands: 2, loop: true, fn: () => ({
      main: [[0.78, -0.55, -0.12], [-0.55, -0.78, 0.18]], other: [[0.78, -0.55, -0.12], [-0.55, -0.78, 0.18]],
      curl: { main: 0.5, other: 0.5 } }) },
    braccia_conserte: { hands: 2, loop: true, fn: (t) => ({
      main: [[0.26, -0.84, 0.5], [-0.92, 0.2, 0.3]], other: [[0.24, -0.86, 0.44], [-0.92, 0.1, 0.36]],
      curl: { main: 0.45, other: 0.45 }, turns: [["spine", 0, 0, 0.015 * S(t * 0.5)]] }) },
    applaude: { hands: 2, dur: 2.6, fn: (t) => {
      const c = A(S(t * 9));
      return { main: [[0.22, -0.55, 0.82], [-0.5 + 0.3 * c, 0.38, 0.85]], other: [[0.22, -0.55, 0.82], [-0.5 + 0.3 * c, 0.38, 0.85]],
               curl: { main: 0.05, other: 0.05 } };
    } },
    pollice_su: { hands: 1, dur: 2.4, fn: () => ({
      main: [[0.22, -0.68, 0.68], [0.05, 0.55, 0.9]], curl: { main: 1 }, keep: { main: ["Thumb"] } }) },
    indica: { hands: 1, dur: 2.8, fn: () => ({
      main: [[0.6, 0.08, 0.8], [0.6, 0.14, 0.8]], curl: { main: 1 }, keep: { main: ["Index"] } }) },
    ombrello: { hands: 1, loop: true, side: "r", fn: () => ({
      main: [[0.24, -0.82, 0.5], [-0.06, 0.62, 0.8]], curl: { main: 0.9 } }) },
    freddo: { hands: 2, dur: 4, fn: (t) => {
      const j = 0.035 * S(t * 38);
      return { main: [[0.3, -0.74, 0.56], [-0.86, 0.36 + j, 0.3]], other: [[0.3, -0.74, 0.56], [-0.86, 0.32 - j, 0.34]],
               curl: { main: 0.6, other: 0.6 }, turns: [["spine", 0.08, 0, 0], ["neck", 0.12, 0, 0]] };
    } },
    stiracchia: { hands: 2, dur: 3.4, fn: (t) => ({
      main: [[0.22, 1, -0.06], [0.06, 1, 0]], other: [[0.22, 1, -0.06], [0.06, 1, 0]],
      curl: { main: 0.2, other: 0.2 }, turns: [["spine", -0.1 * ramp(t, 0.4, 1.4), 0, 0], ["neck", -0.18 * ramp(t, 0.5, 1.5), 0, 0]] }) },
    capelli: { hands: 1, dur: 2.6, fn: (t) => ({
      main: [[0.78, 0.22, 0.2], [-0.25, 0.95, -0.2 + 0.1 * S(t * 3)]], curl: { main: 0.3 },
      turns: [["neck", 0, 0, -0.1]] }) },
    orologio: { hands: 1, dur: 2.8, side: "l", fn: () => ({
      main: [[0.14, -0.68, 0.68], [-0.62, 0.34, 0.7]], curl: { main: 0.4 }, turns: [["neck", 0.32, 0.2, 0]] }) },
    spallucce: { hands: 2, dur: 1.6, fn: (t) => {
      const k = S(Math.min(1, t / 1.6) * Math.PI);
      return { main: [[0.36, -0.84, 0.3], [0.75, 0.05, 0.62]], other: [[0.36, -0.84, 0.3], [0.75, 0.05, 0.62]],
               curl: { main: 0.05, other: 0.05 }, turns: [["lShoulder", 0, 0, 0.22 * k], ["rShoulder", 0, 0, -0.22 * k], ["neck", 0, 0, 0.1 * k]] };
    } },
    inchino: { hands: 2, dur: 2.6, fn: (t) => {
      const k = S(Math.min(1, t / 2.6) * Math.PI);
      return { main: [[0.1, -1, 0.12], [0.05, -1, 0.2]], other: [[0.1, -1, 0.12], [0.05, -1, 0.2]],
               turns: [["spine", 0.25 * k, 0, 0], ["chest", 0.18 * k, 0, 0], ["neck", 0.15 * k, 0, 0]] };
    } },
    cuore: { hands: 2, dur: 2.8, fn: () => ({
      main: [[0.34, -0.42, 0.84], [-0.6, 0.58, 0.55]], other: [[0.34, -0.42, 0.84], [-0.6, 0.58, 0.55]],
      curl: { main: 0.45, other: 0.45 } }) },
    bacio: { hands: 1, dur: 2.4, fn: (t) => {
      const k = ramp(t, 0.9, 1.4);
      return { main: [mix([0.18, -0.62, 0.76], [0.25, -0.2, 0.95], k), mix([-0.3, 0.9, 0.32], [0.15, 0.4, 1], k)],
               curl: { main: 0.25 * (1 - k) } };
    } },
    canta: { hands: 2, loop: true, fn: (t) => ({
      main: [[0.6, -0.3 + 0.08 * S(t * 1.6), 0.55], [0.62, 0.22, 0.78]], other: [[0.12, -0.84, 0.48], [-0.78, 0.48, 0.42]],
      curl: { main: 0.1, other: 0.3 }, turns: [["spine", 0, 0, 0.04 * S(t * 1.6)]] }) },
    sorpresa: { hands: 2, dur: 1.5, fn: (t) => {
      const k = S(Math.min(1, t / 1.5) * Math.PI);
      return { main: [[0.2, -0.7, 0.68], [-0.15, 0.95, 0.3]], other: [[0.2, -0.7, 0.68], [-0.15, 0.95, 0.3]],
               curl: { main: 0.05, other: 0.05 }, turns: [["spine", -0.08 * k, 0, 0]] };
    } },
    ascolto: { hands: 0, loop: true, fn: () => ({ turns: [["spine", 0.05, 0, 0]] }) },
    riposo: { hands: 2, loop: true, fn: () => ({
      main: [[0.14, -1, 0.04], [0.08, -1, 0.22]], other: [[0.14, -1, 0.04], [0.08, -1, 0.22]],
      curl: { main: 0.3, other: 0.3 } }) },
  };

  C.Poses = POSES;
})(window.Atena3D);
