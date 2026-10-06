(() => {
  AtenaDesk.register("calculator", {
    render(el, d, ctx) {
      let isScientific = false;
      let expr = "";
      let displayExpr = "";
      
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

      function factorial(n) {
        if (n === 0 || n === 1) return 1;
        let res = 1;
        for(let i=2; i<=n; i++) res *= i;
        return res;
      }
      
      el.querySelector('.calc-grid').addEventListener('click', (e) => {
        if(e.target.tagName !== 'BUTTON') return;
        const val = e.target.getAttribute('data-val');
        if (!val) return;
        
        if (val === 'C') {
          expr = "";
          displayExpr = "";
          currEl.textContent = "0";
          historyEl.textContent = "";
        } else if (val === 'DEL') {
          expr = expr.slice(0, -1);
          displayExpr = displayExpr.slice(0, -1);
          currEl.textContent = displayExpr || "0";
        } else if (val === '=') {
          try {
            let toEval = expr.replace(/(\d+)!/g, "factorial($1)");
            let res = new Function("factorial", "return " + toEval)(factorial);
            historyEl.textContent = displayExpr + " =";
            displayExpr = String(Math.round(res * 100000000) / 100000000); 
            expr = displayExpr;
            currEl.textContent = displayExpr;
          } catch (err) {
            currEl.textContent = "Error";
            expr = "";
            displayExpr = "";
          }
        } else {
          if (displayExpr === "" && val === "0") return;
          
          let dispVal = val;
          const map = {
            "Math.sin(": "sin(", "Math.cos(": "cos(", "Math.tan(": "tan(",
            "Math.log(": "ln(", "Math.log10(": "log(", "Math.sqrt(": "√(",
            "Math.PI": "π", "Math.E": "e", "**": "^"
          };
          if (map[val]) dispVal = map[val];
          
          expr += val;
          displayExpr += dispVal;
          currEl.textContent = displayExpr;
        }
      });
    }
  });
})();
