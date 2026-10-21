// Vanilla JS, hash routing. #/ index, #/recipe/<id>.
const view = document.getElementById("view");
const filter = document.getElementById("filter");
let index = null;
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

function renderIndex(list) {
  const q = filter.value.trim().toLowerCase();
  const shown = q ? list.filter((r) => r.name.toLowerCase().includes(q)) : list;
  view.innerHTML = `<section class="grid">${shown.map((r) => `
    <a class="card" href="#/recipe/${r.id}">
      <img src="${esc(r.image)}" alt="" loading="lazy">
      <div class="card-body">
        <h2>${esc(r.name)}</h2>
        <p class="meta">${r.minutes} min · ${r.servings} servings</p>
      </div>
    </a>`).join("")}</section>`;
}

function renderRecipe(r) {
  const buy = r.line_items.filter((li) => !li.pantry);
  const pantry = r.line_items.filter((li) => li.pantry);
  const li = (x) => `<li>${x.quantity ? `<b>${esc(x.quantity)}</b> ` : ""}${esc(x.ingredient_name)}</li>`;
  view.innerHTML = `
  <article class="recipe">
    <img class="hero" src="${esc(r.image)}" alt="">
    <h1>${esc(r.name)}</h1>
    <p class="meta">${r.cooking_minutes} min · ${r.serving_count} servings</p>
    <div class="cols">
      <aside>
        <h2>Ingredients</h2>
        <ul class="ingredients">${buy.map(li).join("")}</ul>
        ${pantry.length ? `<h3>Pantry</h3><ul class="ingredients pantry">${pantry.map(li).join("")}</ul>` : ""}
        ${r.cookwares.length ? `<h2>Cookware</h2><ul class="chips">${r.cookwares.map((c) => `<li>${esc(c.name)}</li>`).join("")}</ul>` : ""}
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
  window.scrollTo(0, 0);
}

async function route() {
  const m = location.hash.match(/^#\/recipe\/(\d+)/);
  filter.hidden = !!m;
  if (m) {
    document.title = "Recipes";
    const r = await getRecipe(m[1]);
    document.title = r.name;
    renderRecipe(r);
  } else {
    document.title = "Recipes";
    renderIndex(await getIndex());
  }
}

filter.addEventListener("input", () => getIndex().then(renderIndex));
window.addEventListener("hashchange", route);
route();
