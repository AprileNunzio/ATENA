export class WeatherBackdropManager {
  constructor(containerId = "weather-backdrop", badgeId = "weather-badge") {
    this.container = document.getElementById(containerId);
    this.badge = document.getElementById(badgeId);
    this.canvas = null;
    this.ctx = null;
    this.condition = "clear_day";
    this.isDay = true;
    this.particles = [];
    this.animFrameId = null;
    this.init();
  }

  init() {
    if (!this.container) return;
    this.canvas = document.createElement("canvas");
    this.container.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d");
    this.handleResize = this.resize.bind(this);
    window.addEventListener("resize", this.handleResize);
    this.resize();
    this.fetchWeather();
    setInterval(() => this.fetchWeather(), 600000);
    this.animate();
  }

  resize() {
    if (!this.canvas) return;
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
    this.spawnParticles();
  }

  async fetchWeather() {
    try {
      const res = await fetch("/api/v1/weather/current");
      if (!res.ok) return;
      const data = await res.json();
      this.condition = data.condition || "clear_day";
      this.isDay = Boolean(data.is_day);
      if (this.badge) {
        this.badge.innerHTML = `<span class="weather-indicator-dot"></span><span>${data.city}: ${data.description} (${data.temperature_celsius}°C)</span>`;
      }
      this.applyTheme();
      this.spawnParticles();
    } catch (_) {}
  }

  applyTheme() {
    if (!this.container) return;
    if (this.condition.includes("storm")) {
      this.container.style.background = "radial-gradient(circle at 50% 20%, #1e1b4b 0%, #030712 100%)";
    } else if (this.condition.includes("rain")) {
      this.container.style.background = "radial-gradient(circle at 50% 20%, #0f172a 0%, #020617 100%)";
    } else if (this.condition.includes("cloud") || this.condition.includes("fog")) {
      this.container.style.background = "radial-gradient(circle at 50% 20%, #1e293b 0%, #020617 100%)";
    } else if (!this.isDay) {
      this.container.style.background = "radial-gradient(circle at 50% 20%, #082f49 0%, #020617 100%)";
    } else {
      this.container.style.background = "radial-gradient(circle at 50% 20%, #0369a1 0%, #020617 100%)";
    }
  }

  spawnParticles() {
    if (!this.canvas) return;
    const count = this.condition.includes("rain") ? 90 : (this.condition.includes("storm") ? 120 : 45);
    this.particles = [];
    for (let i = 0; i < count; i++) {
      this.particles.push({
        x: Math.random() * this.canvas.width,
        y: Math.random() * this.canvas.height,
        len: Math.random() * 14 + 6,
        speed: Math.random() * 2 + 1,
        radius: Math.random() * 2 + 0.6,
        alpha: Math.random() * 0.7 + 0.2,
      });
    }
  }

  animate() {
    if (!this.ctx || !this.canvas) return;
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    const w = this.canvas.width;
    const h = this.canvas.height;

    if (this.condition.includes("rain") || this.condition.includes("storm")) {
      this.ctx.strokeStyle = "rgba(56, 189, 248, 0.45)";
      this.ctx.lineWidth = 1.2;
      for (const p of this.particles) {
        this.ctx.beginPath();
        this.ctx.moveTo(p.x, p.y);
        this.ctx.lineTo(p.x - 2, p.y + p.len);
        this.ctx.stroke();
        p.y += p.speed * 4;
        p.x -= 0.8;
        if (p.y > h) {
          p.y = -10;
          p.x = Math.random() * w;
        }
      }
    } else {
      for (const p of this.particles) {
        this.ctx.fillStyle = this.isDay ? `rgba(0, 240, 255, ${p.alpha})` : `rgba(165, 180, 252, ${p.alpha})`;
        this.ctx.beginPath();
        this.ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        this.ctx.fill();
        p.y -= p.speed * 0.25;
        if (p.y < 0) {
          p.y = h;
          p.x = Math.random() * w;
        }
      }
    }

    this.animFrameId = requestAnimationFrame(this.animate.bind(this));
  }

  destroy() {
    if (this.animFrameId) cancelAnimationFrame(this.animFrameId);
    if (this.handleResize) window.removeEventListener("resize", this.handleResize);
  }
}
