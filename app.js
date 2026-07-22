/* Codepet dashboard: polls /api/state and renders pet + charts.
   Chart colors come from the validated dark palette (see style.css roles). */

"use strict";

const REFRESH_MS = 60_000;
const SURFACE = "#1a1a19";
const INK_2 = "#c3c2b7";
const MUTED = "#898781";
const GRID = "#2c2c2a";
const BLUE = "#3987e5";   // sequential context 1: tokens
const GREEN = "#008300";  // sequential context 2: commits
const CATEGORICAL = [     // fixed slot order — validated, never cycled
  "#3987e5", "#008300", "#d55181", "#c98500",
  "#199e70", "#d95926", "#9085e9", "#e66767",
];
const MAX_LANG_SLOTS = CATEGORICAL.length;
const LANG_SLOTS_KEY = "codepet-lang-slots";

const numberFmt = new Intl.NumberFormat("es-MX");
const charts = {};
let habitsBuilt = false;

/* Animation state: what the pet looked like on the previous render. */
const INTERACTION_ANIMS = ["anim-jump", "anim-spin", "anim-wiggle", "anim-dance", "anim-pop"];
const SPARK_COLORS = ["#3987e5", "#c98500", "#199e70", "#d55181"];
let lastXp = null;
let lastStage = null;
let lastAnim = null;
let lastGif = null;
let gifTimer = null;
let currentSprite = null;   // static sprite URL to restore after a GIF plays
let animations = [];        // interaction GIFs offered by the current species
let speciesRendered = null;

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

Chart.defaults.color = MUTED;
Chart.defaults.borderColor = GRID;
Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';

function tooltipOptions() {
  return {
    backgroundColor: "#262624",
    borderColor: "rgba(255,255,255,0.10)",
    borderWidth: 1,
    titleColor: "#ffffff",
    bodyColor: INK_2,
    displayColors: false,
    padding: 10,
  };
}

function shortDate(iso) {
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
}

function compactTokens(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return Math.round(n / 1_000) + "k";
  return String(n);
}

/* ── Charts ─────────────────────────────────────────── */

function makeBarChart(canvasId, color, valueLabel) {
  return new Chart(document.getElementById(canvasId), {
    type: "bar",
    data: {
      labels: [],
      datasets: [{
        data: [],
        backgroundColor: color,
        borderRadius: 4,           // rounded data-end…
        borderSkipped: "bottom",   // …anchored to the baseline
        maxBarThickness: 18,
        categoryPercentage: 0.82,  // ≈2px surface gap between bars
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }, // single series: the title names it
        tooltip: {
          ...tooltipOptions(),
          callbacks: {
            label: (ctx) => `${numberFmt.format(ctx.parsed.y)} ${valueLabel}`,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          border: { color: GRID },
          ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 7 },
        },
        y: {
          beginAtZero: true,
          border: { display: false },
          grid: { color: GRID },
          ticks: { precision: 0, maxTicksLimit: 5 },
        },
      },
    },
  });
}

function makeDoughnutChart(canvasId) {
  return new Chart(document.getElementById(canvasId), {
    type: "doughnut",
    data: {
      labels: [],
      datasets: [{
        data: [],
        backgroundColor: [],
        borderColor: SURFACE,  // 2px surface gap between segments
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "62%",
      plugins: {
        legend: {
          position: "right",
          labels: { color: INK_2, usePointStyle: true, boxWidth: 8, boxHeight: 8 },
        },
        tooltip: {
          ...tooltipOptions(),
          callbacks: {
            label: (ctx) => `${ctx.label}: ${numberFmt.format(ctx.parsed)} archivo(s)`,
          },
        },
      },
    },
  });
}

/* Color follows the entity: each language keeps its slot across days. */
function languageSlots(extensions) {
  let slots;
  try {
    slots = JSON.parse(localStorage.getItem(LANG_SLOTS_KEY)) || {};
  } catch {
    slots = {};
  }
  const used = new Set(Object.values(slots));
  for (const ext of extensions) {
    if (slots[ext] === undefined) {
      let free = 0;
      while (used.has(free) && free < MAX_LANG_SLOTS) free++;
      if (free < MAX_LANG_SLOTS) {
        slots[ext] = free;
        used.add(free);
      }
    }
  }
  localStorage.setItem(LANG_SLOTS_KEY, JSON.stringify(slots));
  return slots;
}

function updateLanguagesChart(byLanguage) {
  const entries = Object.entries(byLanguage).sort((a, b) => b[1] - a[1]);
  const empty = entries.length === 0;
  document.getElementById("languages-empty").classList.toggle("hidden", !empty);
  document.getElementById("languages-chart").classList.toggle("hidden", empty);

  const slots = languageSlots(entries.map(([ext]) => ext));
  const labels = [];
  const data = [];
  const colors = [];
  let other = 0;
  for (const [ext, count] of entries) {
    const slot = slots[ext];
    if (slot === undefined) {
      other += count;
      continue;
    }
    labels.push(ext.replace(/^\./, ""));
    data.push(count);
    colors.push(CATEGORICAL[slot]);
  }
  if (other > 0) {
    labels.push("otros");
    data.push(other);
    colors.push(MUTED);
  }
  const chart = charts.languages;
  chart.data.labels = labels;
  chart.data.datasets[0].data = data;
  chart.data.datasets[0].backgroundColor = colors;
  chart.update();
}

function updateBarChart(chart, series, valueKey) {
  chart.data.labels = series.map((p) => shortDate(p.date));
  chart.data.datasets[0].data = series.map((p) => p[valueKey]);
  chart.update();
}

/* ── Animation ──────────────────────────────────────── */

const GIF_DURATION_MS = 1600;

/* Frame-by-frame GIFs when the species ships them; CSS motion otherwise. */
function playInteractionAnim(kind = "lively") {
  if (reducedMotion) return;
  if (animations.length) {
    playGif(kind);
    return;
  }
  playCssAnim();
}

/* Actions a species may ship. Interaction picks among the lively ones; "sleep"
   belongs to a pet nobody has fed lately, so it plays on its own. */
const LIVELY_ACTIONS = ["jump", "smile", "dance"];
const RESTING_ACTION = "sleep";

function actionOf(url) {
  const match = url.match(/_([a-z]+)\.gif$/);
  return match ? match[1] : "";
}

function pickAnimations(kind) {
  if (kind === "resting") {
    const resting = animations.filter((a) => actionOf(a) === RESTING_ACTION);
    if (resting.length) return resting;
  }
  const lively = animations.filter((a) => LIVELY_ACTIONS.includes(actionOf(a)));
  // species whose files predate the action names fall back to whatever exists
  return lively.length ? lively : animations;
}

/* Swap the sprite for an animation GIF, then restore the still frame.
   The cache-busting query restarts the GIF from frame 0 on every play. */
function playGif(kind = "lively") {
  const sprite = document.getElementById("pet-sprite");
  if (!currentSprite || sprite.classList.contains("hidden")) {
    playCssAnim();
    return;
  }
  const choices = pickAnimations(kind);
  let gif = lastGif;
  while (choices.length > 1 && gif === lastGif) {
    gif = choices[Math.floor(Math.random() * choices.length)];
  }
  if (choices.length === 1) gif = choices[0];
  lastGif = gif;

  clearTimeout(gifTimer);
  // the GIF canvas carries padding the still frame lacks; "animating" grows the
  // box by the same factor so the pet keeps its size across the swap
  sprite.classList.add("animating");
  sprite.src = `${gif}?t=${Date.now()}`;
  gifTimer = setTimeout(() => {
    sprite.src = currentSprite;
    sprite.classList.remove("animating");
    gifTimer = null;
  }, GIF_DURATION_MS);
}

function playCssAnim() {
  const body = document.getElementById("pet-body");
  let anim = lastAnim;
  while (anim === lastAnim) {
    anim = INTERACTION_ANIMS[Math.floor(Math.random() * INTERACTION_ANIMS.length)];
  }
  lastAnim = anim;
  body.classList.remove(...INTERACTION_ANIMS);
  void body.offsetWidth; // restart the animation even if the class repeats
  body.classList.add(anim);
  body.addEventListener("animationend", () => body.classList.remove(anim), { once: true });
}

function spawnSparks(count = 14) {
  if (reducedMotion) return;
  const layer = document.getElementById("fx-layer");
  for (let i = 0; i < count; i++) {
    const spark = document.createElement("span");
    spark.className = "spark";
    const angle = (Math.PI * 2 * i) / count + Math.random() * 0.4;
    const distance = 45 + Math.random() * 55;
    spark.style.setProperty("--dx", `${Math.cos(angle) * distance}px`);
    spark.style.setProperty("--dy", `${Math.sin(angle) * distance}px`);
    spark.style.background = SPARK_COLORS[i % SPARK_COLORS.length];
    spark.style.animationDelay = `${Math.random() * 0.15}s`;
    layer.appendChild(spark);
    spark.addEventListener("animationend", () => spark.remove(), { once: true });
  }
}

function floatXp(amount) {
  if (reducedMotion || !amount) return;
  const layer = document.getElementById("fx-layer");
  const label = document.createElement("span");
  label.className = "xp-float";
  label.textContent = `+${amount} XP`;
  layer.appendChild(label);
  label.addEventListener("animationend", () => label.remove(), { once: true });
}

function floatXpAtButton(button, amount) {
  if (reducedMotion) return;
  const rect = button.getBoundingClientRect();
  const label = document.createElement("span");
  label.className = "btn-float";
  label.textContent = `+${amount}`;
  label.style.left = `${rect.left + rect.width / 2}px`;
  label.style.top = `${rect.top - 6}px`;
  document.body.appendChild(label);
  label.addEventListener("animationend", () => label.remove(), { once: true });
}

/* Evolution is the one moment that gets its own sequence. */
function playLevelUp(stageName) {
  if (reducedMotion) return;
  const card = document.querySelector(".pet-card");
  const body = document.getElementById("pet-body");
  card.classList.add("levelup");
  body.classList.add("evolving");
  spawnSparks(26);
  setTimeout(() => spawnSparks(20), 400);

  const banner = document.createElement("div");
  banner.className = "levelup-banner";
  banner.textContent = `¡Evolucionó a ${stageName}!`;
  card.appendChild(banner);

  card.addEventListener("animationend", () => card.classList.remove("levelup"), { once: true });
  body.addEventListener("animationend", () => body.classList.remove("evolving"), { once: true });
  banner.addEventListener("animationend", () => banner.remove(), { once: true });
}

/* ── Rendering ──────────────────────────────────────── */

const KIND_LABELS = {
  "git-commit": "commit",
  "claude-tokens": "tokens Claude",
  "files": "archivos",
  "github": "GitHub",
};

function render(s, options = {}) {
  const art = document.getElementById("pet-art");
  const gained = lastXp !== null && s.xp > lastXp ? s.xp - lastXp : 0;
  const evolved = lastStage !== null && s.stage !== lastStage;

  const body = document.getElementById("pet-body");
  const sprite = document.getElementById("pet-sprite");
  art.textContent = s.art.join("\n");

  animations = s.animations || [];

  // a sprite for this stage replaces the ASCII art; otherwise fall back to it
  if (s.sprite) {
    const playingGif = gifTimer && currentSprite !== s.sprite;
    currentSprite = s.sprite;
    if (!playingGif && !sprite.src.includes(s.sprite)) sprite.src = s.sprite;
    sprite.classList.remove("hidden");
    art.classList.add("hidden");
  } else {
    currentSprite = null;
    sprite.classList.add("hidden");
    art.classList.remove("hidden");
  }

  if (s.species !== speciesRendered) {
    buildSpeciesPicker(s.species_options, s.species);
    speciesRendered = s.species;
  }

  // keep any running interaction animation; only swap the mood loop
  const running = INTERACTION_ANIMS.filter((a) => body.classList.contains(a));
  body.className = ["pet-body", `mood-${s.mood.key}`, ...running].join(" ");

  document.getElementById("pet-name").textContent = s.name;
  document.getElementById("pet-stage").textContent = `etapa: ${s.stage} · ${s.xp} XP`;
  document.getElementById("pet-mood").textContent = s.mood.text;

  const fill = document.getElementById("xp-fill");
  const bar = document.querySelector(".xp-bar");
  const label = document.getElementById("xp-label");
  if (s.next_stage) {
    const pct = Math.round(s.next_stage.progress * 100);
    fill.style.width = `${pct}%`;
    label.textContent = `faltan ${s.next_stage.xp_needed} XP para "${s.next_stage.name}"`;
    bar.classList.toggle("almost", pct >= 85);  // pulses when evolution is close
  } else {
    fill.style.width = "100%";
    label.textContent = "etapa máxima alcanzada";
    bar.classList.remove("almost");
  }
  if (gained) {
    bar.classList.remove("gain");
    void bar.offsetWidth;
    bar.classList.add("gain");
  }

  document.getElementById("streak").textContent =
    s.streak > 0 ? `🔥 racha de ${s.streak} día(s)` : "sin racha todavía";

  const decay = document.getElementById("decay-note");
  decay.classList.toggle("hidden", !s.decay_lost);
  if (s.decay_lost) decay.textContent = `⚠ Perdió ${s.decay_lost} XP por inactividad`;

  document.getElementById("tile-tokens").textContent = compactTokens(s.today.tokens);
  document.getElementById("tile-commits").textContent = numberFmt.format(s.today.commits);
  document.getElementById("tile-files").textContent = numberFmt.format(s.today.files);

  const gh = document.getElementById("tile-github");
  if (s.today.github.status !== "ok") {
    gh.textContent = "⚠ sin conexión";
    gh.className = "tile-value tile-github offline";
  } else if (s.today.github.contributed) {
    gh.textContent = "✓ contribuiste";
    gh.className = "tile-value tile-github ok";
  } else {
    gh.textContent = "· aún nada";
    gh.className = "tile-value tile-github pending";
  }

  const tunnel = document.getElementById("tunnel-link");
  tunnel.classList.toggle("hidden", !s.tunnel);
  if (s.tunnel) {
    tunnel.href = s.tunnel;
    tunnel.textContent = `🌐 ${s.tunnel.replace("https://", "")}`;
  }

  document.getElementById("repos-watched").textContent =
    s.repos_watched ? `${s.repos_watched} repo(s) vigilados` : "";

  updateBarChart(charts.tokens, s.series.tokens, "tokens");
  updateBarChart(charts.commits, s.series.commits, "commits");
  updateLanguagesChart(s.series.languages);

  if (!habitsBuilt) buildHabitButtons(s.habits);

  const feed = document.getElementById("feed");
  feed.innerHTML = "";
  for (const [date, kind, xp, detail] of s.log) {
    const li = document.createElement("li");
    const label = KIND_LABELS[kind] || kind;
    li.innerHTML =
      `<span class="date">${shortDate(date)}</span>` +
      `<span>${label}${detail ? " — " + escapeHtml(detail) : ""}</span>` +
      `<span class="xp">+${xp}</span>`;
    feed.appendChild(li);
  }

  // Evolution outranks the interaction animation; both outrank a silent update.
  if (evolved) {
    playLevelUp(s.stage);
  } else if (options.interaction || gained) {
    playInteractionAnim();
    if (gained) {
      spawnSparks(gained >= 20 ? 18 : 10);
      if (!options.silentXp) floatXp(gained);
    }
  } else if (["bored", "sad", "hungry"].includes(s.mood.key) && Math.random() < 0.35) {
    // idle poll on a neglected pet: let it nap instead of standing still
    playInteractionAnim("resting");
  }
  lastXp = s.xp;
  lastStage = s.stage;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function buildSpeciesPicker(options, active) {
  const box = document.getElementById("species-picker");
  box.innerHTML = "";
  for (const option of options || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `species-btn${option.key === active ? " active" : ""}`;
    btn.disabled = !option.available;
    btn.textContent = option.label;
    btn.title = option.available ? "" : "Sin sprites todavía";
    btn.addEventListener("click", async () => {
      if (option.key === active) return;
      const res = await fetch("/api/species", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ species: option.key }),
      });
      if (res.ok) {
        speciesRendered = null;  // force the picker to redraw with the new active
        render(await res.json(), { interaction: true });
      }
    });
    box.appendChild(btn);
  }
}

function buildHabitButtons(habits) {
  const box = document.getElementById("habit-buttons");
  box.innerHTML = "";
  for (const habit of habits) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "habit-btn";
    btn.innerHTML = `${escapeHtml(habit.desc)}<span class="xp">+${habit.xp}</span>`;
    btn.addEventListener("click", async () => {
      btn.classList.remove("clicked");
      void btn.offsetWidth;
      btn.classList.add("clicked");
      floatXpAtButton(btn, habit.xp);
      const res = await fetch(`/api/habit/${habit.key}`, { method: "POST" });
      if (res.ok) render(await res.json(), { interaction: true, silentXp: true });
    });
    box.appendChild(btn);
  }
  habitsBuilt = true;
}

/* ── Wiring ─────────────────────────────────────────── */

async function fetchState(force = false) {
  const url = force ? "/api/scan" : "/api/state";
  const res = await fetch(url, force ? { method: "POST" } : undefined);
  if (res.ok) render(await res.json(), { interaction: force });
}

document.getElementById("scan-btn").addEventListener("click", async (ev) => {
  ev.target.disabled = true;
  try {
    await fetchState(true);
  } finally {
    ev.target.disabled = false;
  }
});

// clicking the pet is an interaction too — it just says hello
document.getElementById("pet-body").addEventListener("click", playInteractionAnim);

document.getElementById("pet-name").addEventListener("dblclick", async () => {
  const name = prompt("Nuevo nombre para tu mascota:");
  if (!name || !name.trim()) return;
  const res = await fetch("/api/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name.trim() }),
  });
  if (res.ok) render(await res.json(), { interaction: true });
});

charts.tokens = makeBarChart("tokens-chart", BLUE, "tokens");
charts.commits = makeBarChart("commits-chart", GREEN, "commit(s)");
charts.languages = makeDoughnutChart("languages-chart");

fetchState();
setInterval(fetchState, REFRESH_MS);
