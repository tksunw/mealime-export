// Vanilla JS, hash routing. #/ index, #/recipe/<id>, #/cook/<id>/<n>, #/plan, #/plan/<id>.
const view = document.getElementById("view");
const filter = document.getElementById("filter");
const MAX_PLAN = 5;
let index = null;
let state = { plan: [], history: [], checked: {}, overrides: {} }; // plan: recipe ids; history: [{ids, created}]; checked/overrides keyed by ingredient key
const cache = {};

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function getIndex() {
  if (!index) index = await (await fetch("/api/recipes")).json();
  return index;
}
async function getRecipe(id) {
  if (!cache[id]) cache[id] = await (await fetch(`/api/recipes/${id}`)).json();
  return cache[id];
}
async function loadState() {
  try { state = { ...state, ...(await (await fetch("/api/state")).json()) }; } catch (e) { /* offline: keep defaults */ }
}
function saveState() {
  return fetch("/api/state", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state) });
}

// --- plan mutations ---
const inPlan = (id) => state.plan.includes(+id);
function togglePlan(id) {
  id = +id;
  if (inPlan(id)) state.plan = state.plan.filter((x) => x !== id);
  else if (state.plan.length < MAX_PLAN) state.plan.push(id);
  saveState();
  route();
}
function clearPlan() {
  if (state.plan.length) {
    state.history = [{ ids: state.plan, created: new Date().toISOString() }, ...state.history].slice(0, 10);
    state.plan = [];
    state.checked = {};
    saveState();
  }
  location.hash = "#/";
}
function restorePlan(i) {
  state.plan = state.history[i].ids.slice(0, MAX_PLAN);
  saveState();
  location.hash = "#/plan";
}
function toggleChecked(key) {
  state.checked[key] = !state.checked[key];
  saveState();
  view.querySelector(`[data-key="${CSS.escape(key)}"]`)?.classList.toggle("done", state.checked[key]);
}
async function setCategory(key, cat) {
  state.overrides[key] = cat;
  await saveState(); // grocery is computed server-side from the saved overrides
  const y = scrollY;
  await route();
  scrollTo(0, y);
}
async function copyGrocery() {
  const g = await (await fetch(`/api/grocery?ids=${state.plan.join(",")}`)).json();
  const text = g.order.map((c) => {
    const items = g.items.filter((i) => i.category === c && !state.checked[i.key]);
    return items.length ? `${c}\n${items.map((i) => `  ${i.lines.length ? i.lines.join(" + ") + " " : ""}${i.name}${i.approx?.length ? ` (about ${i.approx.join(" + ")})` : ""}`).join("\n")}` : "";
  }).filter(Boolean).join("\n\n");
  try { await navigator.clipboard.writeText(text); flash("Copied"); } catch (e) { flash("Copy failed"); }
}
function flash(msg) {
  const b = view.querySelector(".copy"); if (!b) return;
  const t = b.textContent; b.textContent = msg; setTimeout(() => { b.textContent = t; }, 1500);
}
window.togglePlan = togglePlan; window.clearPlan = clearPlan; window.restorePlan = restorePlan;
window.toggleChecked = toggleChecked; window.setCategory = setCategory; window.copyGrocery = copyGrocery;

// --- views ---
function renderIndex(list) {
  const q = filter.value.trim().toLowerCase();
  const shown = q ? list.filter((r) => r.name.toLowerCase().includes(q)) : list;
  const full = state.plan.length >= MAX_PLAN;
  view.innerHTML = `<section class="grid">${shown.map((r) => `
    <div class="card ${inPlan(r.id) ? "picked" : ""}">
      <a href="#/recipe/${r.id}"><img src="${esc(r.image)}" alt="" loading="lazy"></a>
      <button class="pick" onclick="togglePlan(${r.id})" ${!inPlan(r.id) && full ? "disabled" : ""}
        aria-label="${inPlan(r.id) ? "Remove from plan" : "Add to plan"}">${inPlan(r.id) ? "✓" : "+"}</button>
      <a class="card-body" href="#/recipe/${r.id}">
        <h2>${esc(r.name)}</h2>
        <p class="meta">${r.minutes} min · ${r.servings} servings</p>
      </a>
    </div>`).join("")}</section>`;
}

function recipeHTML(r) {
  const buy = r.line_items.filter((li) => !li.pantry);
  const pantry = r.line_items.filter((li) => li.pantry);
  const li = (x) => `<li>${x.quantity ? `<b>${esc(x.quantity)}</b> ` : ""}${esc(x.ingredient_name)}</li>`;
  return `
  <article class="recipe">
    <img class="hero" src="${esc(r.image)}" alt="">
    <h1>${esc(r.name)}</h1>
    <p class="meta">${r.cooking_minutes} min · ${r.serving_count} servings
      <a class="btn" href="#/cook/${r.id}/1">Cook</a>
      <button class="btn ghost" onclick="togglePlan(${r.id})" ${!inPlan(r.id) && state.plan.length >= MAX_PLAN ? "disabled" : ""}>
        ${inPlan(r.id) ? "✓ In plan" : "+ Plan"}</button></p>
    <div class="cols">
      <aside>
        <h2>Ingredients</h2>
        <ul class="ingredients">${buy.map(li).join("")}</ul>
        ${pantry.length ? `<h3>Pantry</h3><ul class="ingredients pantry">${pantry.map(li).join("")}</ul>` : ""}
        ${r.cookwares.length ? `<h2>Cookware</h2><ul class="chips">${r.cookwares.map((c) => `<li>${esc(c.name)}</li>`).join("")}</ul>` : ""}
        ${nutritionHTML(r.nutrition)}
      </aside>
      <section>
        <h2>Steps</h2>
        <ol class="steps">${r.instructions.map((s) => `
          <li>
            <p>${esc(s.primary_message)}</p>
            ${s.uses.length ? `<ul class="uses">${s.uses.map((u) => `<li>${esc(u)}</li>`).join("")}</ul>` : ""}
          </li>`).join("")}</ol>
      </section>
    </div>
  </article>`;
}

const NUTRIENTS = [["energy", "Calories", "", 0], ["protein", "Protein", "g", 0], ["carbs", "Carbs", "g", 0],
  ["fiber", "Fiber", "g", 0], ["sugars", "Sugars", "g", 0], ["fat", "Fat", "g", 0], ["saturated", "Saturated", "g", 0],
  ["cholesterol", "Cholesterol", "mg", 0], ["sodium", "Sodium", "mg", 0], ["potassium", "Potassium", "mg", 0],
  ["calcium", "Calcium", "mg", 0], ["iron", "Iron", "mg", 1]];
function nutritionHTML(n) {
  if (!n) return "";
  return `<details class="nutrition"><summary>Nutrition per serving</summary><dl>${NUTRIENTS
    .filter(([k]) => n[k] != null)
    .map(([k, label, unit, dp]) => `<div><dt>${label}</dt><dd>${(+n[k]).toFixed(dp)}${unit}</dd></div>`).join("")}</dl></details>`;
}

async function renderPlan(activeId) {
  const recipes = await Promise.all(state.plan.map(getRecipe));
  const names = Object.fromEntries((await getIndex()).map((r) => [r.id, r.name]));
  if (!recipes.length) {
    view.innerHTML = `<section class="plan-empty"><h1>No plan yet</h1><p>Pick up to ${MAX_PLAN} recipes from the <a href="#/">list</a>.</p>
      ${historyHTML(names)}</section>`;
    return;
  }
  const grocery = activeId === "grocery";
  const active = grocery ? null : recipes.find((r) => r.id === +activeId) || recipes[0];
  const body = grocery ? groceryHTML(await (await fetch(`/api/grocery?ids=${state.plan.join(",")}`)).json()) : recipeHTML(active);
  view.innerHTML = `
  <nav class="tabs">
    ${recipes.map((r) => `<a class="${r === active ? "active" : ""}" href="#/plan/${r.id}">${esc(r.name)}</a>`).join("")}
    <a class="grocery-tab ${grocery ? "active" : ""}" href="#/plan/grocery">Grocery</a>
    <button class="clear" onclick="clearPlan()">Clear plan</button>
  </nav>
  ${body}
  ${historyHTML(names)}`;
  window.scrollTo(0, 0);
}

function groceryHTML(g) {
  const cats = g.order.filter((c) => g.items.some((i) => i.category === c));
  const opts = (cur) => g.order.filter((c) => c !== "Pantry").map((c) => `<option ${c === cur ? "selected" : ""}>${esc(c)}</option>`).join("");
  return `<section class="grocery">
    <p class="meta"><button class="btn copy" onclick="copyGrocery()">Copy as text</button></p>
    ${cats.map((c) => `
      <h2>${c === "Pantry" ? "Pantry · check you have" : esc(c)}</h2>
      <ul>${g.items.filter((i) => i.category === c).map((i) => `
        <li data-key="${esc(i.key)}" class="${state.checked[i.key] ? "done" : ""}">
          <label><input type="checkbox" ${state.checked[i.key] ? "checked" : ""} onchange="toggleChecked(${esc(JSON.stringify(i.key))})">
            <span>${i.lines.length ? `<b>${esc(i.lines.join(" + "))}</b> ` : ""}${esc(i.name)}${i.approx?.length ? ` <i>≈ ${esc(i.approx.join(" + "))}</i>` : ""}</span></label>
          ${i.pantry ? "" : `<select class="cat" aria-label="Category" onchange="setCategory(${esc(JSON.stringify(i.key))}, this.value)">${opts(i.category)}</select>`}
          <details><summary>${i.sources.length} ${i.sources.length === 1 ? "recipe" : "recipes"}</summary>
            <ul>${i.sources.map((s) => `<li>${esc(s.text)} <span>· ${esc(s.recipe)}</span></li>`).join("")}</ul></details>
        </li>`).join("")}</ul>`).join("")}
  </section>`;
}

function historyHTML(names) {
  if (!state.history.length) return "";
  return `<section class="history"><h2>Previous plans</h2><ul>${state.history.map((h, i) => `
    <li><button onclick="restorePlan(${i})">${new Date(h.created).toLocaleDateString()}</button>
      <span>${h.ids.map((id) => esc(names[id] || id)).join(" · ")}</span></li>`).join("")}</ul></section>`;
}

function renderTray() {
  let tray = document.getElementById("tray");
  if (!tray) { tray = document.createElement("div"); tray.id = "tray"; document.body.appendChild(tray); }
  const n = state.plan.length;
  tray.hidden = !n || document.body.classList.contains("cooking") || location.hash.startsWith("#/plan");
  tray.innerHTML = `<a href="#/plan"><b>${n}</b> ${n === 1 ? "recipe" : "recipes"} in plan · Open</a>`;
}

// --- cook mode: one step per screen, wake lock held while on this route ---
let wakeLock = null;
async function holdWake() {
  try { wakeLock = await navigator.wakeLock?.request("screen"); } catch (e) { wakeLock = null; }
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && location.hash.startsWith("#/cook/")) holdWake();
});

function renderCook(r, n) {
  const steps = r.instructions;
  n = Math.min(Math.max(n, 1), steps.length);
  const s = steps[n - 1];
  document.body.classList.add("cooking");
  view.innerHTML = `
  <section class="cook">
    <header>
      <a class="exit" href="#/recipe/${r.id}">Done</a>
      <span class="progress">${n} / ${steps.length}</span>
      <span class="title">${esc(r.name)}</span>
    </header>
    <div class="step">
      <p>${esc(s.primary_message)}</p>
      ${s.uses.length ? `<ul class="uses">${s.uses.map((u) => `<li>${esc(u)}</li>`).join("")}</ul>` : ""}
    </div>
    <nav>
      <a class="prev" href="#/cook/${r.id}/${n - 1}" ${n === 1 ? "hidden" : ""}>‹ Back</a>
      <a class="next" href="#/cook/${r.id}/${n + 1}" ${n === steps.length ? "hidden" : ""}>Next ›</a>
    </nav>
  </section>`;
  holdWake();
}
document.addEventListener("keydown", (e) => {
  if (!document.body.classList.contains("cooking")) return;
  const a = view.querySelector(e.key === "ArrowLeft" ? ".prev" : e.key === "ArrowRight" || e.key === " " ? ".next" : null);
  if (a && !a.hidden) { e.preventDefault(); a.click(); }
});

// --- router ---
async function route() {
  const h = location.hash;
  const c = h.match(/^#\/cook\/(\d+)(?:\/(\d+))?/);
  if (c) {
    filter.hidden = true;
    renderCook(await getRecipe(c[1]), +(c[2] || 1));
    renderTray();
    return;
  }
  document.body.classList.remove("cooking");
  wakeLock?.release(); wakeLock = null;
  const p = h.match(/^#\/plan(?:\/(\d+|grocery))?/);
  const m = h.match(/^#\/recipe\/(\d+)/);
  filter.hidden = !!(p || m);
  document.title = "Recipes";
  if (p) {
    await renderPlan(p[1]);
    document.title = "Plan";
  } else if (m) {
    const r = await getRecipe(m[1]);
    document.title = r.name;
    view.innerHTML = recipeHTML(r);
    window.scrollTo(0, 0);
  } else {
    renderIndex(await getIndex());
  }
  renderTray();
}

filter.addEventListener("input", () => getIndex().then(renderIndex));
window.addEventListener("hashchange", route);
loadState().then(route);
