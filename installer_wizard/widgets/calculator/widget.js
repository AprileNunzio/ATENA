(() => {
  AtenaDesk.register("calculator", {
    render(el, d, ctx) {
      let isScientific = false;
      let parts = [];
      const SHOW = {
        "Math.sin(": "sin(", "Math.cos(": "cos(", "Math.tan(": "tan(",
        "Math.log(": "ln(", "Math.log10(": "log(", "Math.sqrt(": "√(",
        "Math.PI": "π", "Math.E": "e", "**": "^", "*": "×", "/": "÷", "-": "−"
      };
      const source = () => parts.join("");
      const shown = () => parts.map((p) => SHOW[p] || p).join("");
      
      el.innerHTML = `
        <div class="calc-wrapper">
          <div class="calc-head">
            ${ctx.head({ icon: "calc", label: "Calcolatrice" })}
            <button class="calc-mode-btn wk-btn" type="button">Sci</button>
          </div>
          <div class="calc-screen">
            <div class="calc-history"></div>
            <div class="calc-curr">0</div>
          </div>
          <div class="calc-grid">
            <div class="calc-sci-keys" style="display: none;">
              <button data-val="Math.sin(">sin</button>
              <button data-val="Math.cos(">cos</button>
              <button data-val="Math.tan(">tan</button>
              <button data-val="Math.log(">ln</button>
              <button data-val="Math.log10(">log</button>
              <button data-val="Math.sqrt(">√</button>
              <button data-val="Math.PI">π</button>
              <button data-val="Math.E">e</button>
              <button data-val="**">^</button>
              <button data-val="(">(</button>
              <button data-val=")">)</button>
              <button data-val="!">n!</button>
            </div>
            <div class="calc-basic-keys">
              <button class="calc-op" data-val="C">C</button>
              <button class="calc-op" data-val="DEL">⌫</button>
              <button class="calc-op" data-val="%">%</button>
              <button class="calc-op" data-val="/">÷</button>
              
              <button data-val="7">7</button>
              <button data-val="8">8</button>
              <button data-val="9">9</button>
              <button class="calc-op" data-val="*">×</button>
              
              <button data-val="4">4</button>
              <button data-val="5">5</button>
              <button data-val="6">6</button>
              <button class="calc-op" data-val="-">−</button>
              
              <button data-val="1">1</button>
              <button data-val="2">2</button>
              <button data-val="3">3</button>
              <button class="calc-op" data-val="+">+</button>
              
              <button data-val="0" style="grid-column: span 2;">0</button>
              <button data-val=".">.</button>
              <button class="calc-eq" data-val="=">=</button>
            </div>
          </div>
        </div>
      `;

      const modeBtn = el.querySelector('.calc-mode-btn');
      const sciKeys = el.querySelector('.calc-sci-keys');
      const historyEl = el.querySelector('.calc-history');
      const currEl = el.querySelector('.calc-curr');
      
      modeBtn.addEventListener('click', () => {
        isScientific = !isScientific;
        modeBtn.textContent = isScientific ? "Norm" : "Sci";
        sciKeys.style.display = isScientific ? "grid" : "none";
      });

      const FUNCS = { "Math.sin(": Math.sin, "Math.cos(": Math.cos, "Math.tan(": Math.tan, "Math.log(": Math.log, "Math.log10(": Math.log10, "Math.sqrt(": Math.sqrt };
      const TOKEN = /\s*(Math\.(?:sin|cos|tan|log10|log|sqrt)\(|Math\.PI|Math\.E|\*\*|\d+(?:\.\d*)?|\.\d+|[-+*/%()!])/y;
      function factorial(n) {
        if (!Number.isInteger(n) || n < 0 || n > 170) throw new RangeError("factorial");
        let res = 1;
        for (let i = 2; i <= n; i++) res *= i;
        return res;
      }
      function evaluate(src) {
        const tokens = [];
        TOKEN.lastIndex = 0;
        while (TOKEN.lastIndex < src.length) {
          const m = TOKEN.exec(src);
          if (!m) throw new SyntaxError("token");
          tokens.push(m[1]);
        }
        let i = 0;
        const peek = () => tokens[i];
        const next = () => tokens[i++];
        const expect = (t) => { if (next() !== t) throw new SyntaxError(t); };
        const primary = () => {
          const t = next();
          if (t === undefined) throw new SyntaxError("end");
          if (FUNCS[t]) { const v = expression(); expect(")"); return FUNCS[t](v); }
          if (t === "Math.PI") return Math.PI;
          if (t === "Math.E") return Math.E;
          if (t === "(") { const v = expression(); expect(")"); return v; }
          if (t === "-") return -unary();
          if (t === "+") return unary();
          const n = Number(t);
          if (!Number.isFinite(n)) throw new SyntaxError(t);
          return n;
        };
        const postfix = () => { let v = primary(); while (peek() === "!") { next(); v = factorial(v); } return v; };
        const unary = () => postfix();
        const power = () => { const b = unary(); if (peek() === "**") { next(); return b ** power(); } return b; };
        const term = () => {
          let v = power();
          while (["*", "/", "%"].includes(peek())) {
            const op = next(), r = power();
            v = op === "*" ? v * r : op === "/" ? v / r : v % r;
          }
          return v;
        };
        const expression = () => {
          let v = term();
          while (peek() === "+" || peek() === "-") { const op = next(), r = term(); v = op === "+" ? v + r : v - r; }
          return v;
        };
        const out = expression();
        if (i !== tokens.length || !Number.isFinite(out)) throw new SyntaxError("trailing");
        return out;
      }

      el.querySelector('.calc-grid').addEventListener('click', (e) => {
        if(e.target.tagName !== 'BUTTON') return;
        const val = e.target.getAttribute('data-val');
        if (!val) return;
        
        if (val === 'C') {
          parts = [];
          currEl.textContent = "0";
          historyEl.textContent = "";
        } else if (val === 'DEL') {
          parts.pop();
          currEl.textContent = shown() || "0";
        } else if (val === '=') {
          if (!parts.length) return;
          try {
            const res = evaluate(source());
            historyEl.textContent = shown() + " =";
            const out = String(Math.round(res * 100000000) / 100000000);
            parts = [...out];
            currEl.textContent = out;
          } catch (err) {
            currEl.textContent = "Errore";
            parts = [];
          }
        } else {
          if (!parts.length && val === "0") return;
          parts.push(val);
          currEl.textContent = shown();
        }
      });
    }
  });
})();
