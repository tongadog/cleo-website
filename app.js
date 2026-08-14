(function () {
  const fmt = (d) => d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });

  // Normalize the two sources into one model.
  const articles = (window.ARTICLES || []).map((a) => {
    const d = new Date(a.date);
    return {
      group: "Articles",
      category: a.category || "",
      kind: "article",
      badge: a.category || "Analysis",
      badgeClass: "article",
      title: a.title,
      outlet: a.outlet,
      url: a.url,
      sourceUrl: a.sourceUrl || "",
      sourceLabel: a.sourceLabel || "",
      issues: a.issues || [],
      programs: [],
      dek: a.subtitle || a.excerpt || "",
      thumb: a.thumbnail || "",
      yt: "",
      dateStr: fmt(d), _time: d.getTime(), _year: d.getFullYear(),
    };
  });

  const posts = (window.POSTS || []).map((p) => {
    const d = new Date(p.date);
    const isB = p.type === "Broadcast Appearances";
    return {
      group: p.type,
      category: "",
      kind: isB ? "broadcast" : "quote",
      badge: isB ? "Broadcast" : "Quote",
      badgeClass: isB ? "broadcast" : "quote",
      title: p.title,
      outlet: p.outlet,
      url: p.url,
      sourceUrl: "",
      issues: p.issues || [],
      programs: p.programs || [],
      dek: "",
      thumb: p.yt ? `https://i.ytimg.com/vi/${p.yt.split("&")[0]}/hqdefault.jpg` : "",
      yt: p.yt ? p.yt.split("&")[0] : "",
      dateStr: p.date, _time: d.getTime(), _year: d.getFullYear(),
    };
  });

  const all = articles.concat(posts);

  const $ = (id) => document.getElementById(id);
  const els = {
    q: $("q"), year: $("year"), issue: $("issue"), program: $("program"),
    outlet: $("outlet"), videoOnly: $("videoOnly"), sort: $("sort"),
    clear: $("clear"), grid: $("grid"), count: $("count"), typeSeg: $("typeSeg"),
    maps: $("maps"), resultBar: document.querySelector(".result-bar"),
    lightbox: $("lightbox"),
    footYear: $("footYear"),
    filters: $("filters"), filtersToggle: $("filtersToggle"), filtersCount: $("filtersCount"),
  };
  if (els.footYear) els.footYear.textContent = new Date().getFullYear();

  const state = { q: "", type: "all", year: "", issue: "", program: "", outlet: "", videoOnly: false, sort: "newest" };

  function uniqueSorted(fn) {
    const set = new Set();
    all.forEach((p) => fn(p).forEach((v) => v && set.add(v)));
    return [...set].sort((a, b) => a.localeCompare(b));
  }
  function fillSelect(el, values) {
    values.forEach((v) => {
      const o = document.createElement("option");
      o.value = v; o.textContent = v; el.appendChild(o);
    });
  }

  fillSelect(els.year, [...new Set(all.map((p) => p._year))].sort((a, b) => b - a).map(String));
  fillSelect(els.issue, uniqueSorted((p) => p.issues));
  fillSelect(els.program, uniqueSorted((p) => p.programs));
  fillSelect(els.outlet, uniqueSorted((p) => [p.outlet]));

  function matches(p) {
    if (state.type !== "all" && p.group !== state.type && p.category !== state.type) return false;
    if (state.year && String(p._year) !== state.year) return false;
    if (state.issue && !p.issues.includes(state.issue)) return false;
    if (state.program && !p.programs.includes(state.program)) return false;
    if (state.outlet && p.outlet !== state.outlet) return false;
    if (state.videoOnly && !p.yt) return false;
    if (state.q) {
      const hay = (p.title + " " + p.outlet + " " + p.badge + " " + p.dek + " " + p.issues.join(" ") + " " + p.programs.join(" ")).toLowerCase();
      if (!state.q.toLowerCase().split(/\s+/).every((t) => hay.includes(t))) return false;
    }
    return true;
  }

  function sortFn(a, b) {
    if (state.sort === "oldest") return a._time - b._time;
    if (state.sort === "title") return a.title.localeCompare(b.title);
    return b._time - a._time;
  }

  const esc = (s) => (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function card(p) {
    let thumb = "";
    if (p.thumb && p.yt) {
      thumb = `<a class="thumb" href="https://www.youtube.com/watch?v=${p.yt}" target="_blank" rel="noopener">
                 <img loading="lazy" src="${esc(p.thumb)}" alt="" /><span class="play"></span></a>`;
    } else if (p.thumb) {
      thumb = `<a class="thumb" href="${esc(p.url)}" target="_blank" rel="noopener">
                 <img loading="lazy" src="${esc(p.thumb)}" alt="" /></a>`;
    }
    const dek = p.dek ? `<p class="dek">${esc(p.dek)}</p>` : "";
    const tags = p.issues.map((t) => `<button class="tag" data-issue="${esc(t)}">${esc(t)}</button>`).join("");
    const watch = p.yt
      ? `<a class="foot-link watch" href="https://www.youtube.com/watch?v=${p.yt}" target="_blank" rel="noopener">Watch &#9654;</a>`
      : "";
    const source = p.sourceUrl
      ? `<a class="foot-link source" href="${esc(p.sourceUrl)}" target="_blank" rel="noopener">${esc(p.sourceLabel || "View source")} &rarr;</a>`
      : "";
    return `<article class="card">
      ${thumb}
      <div class="card-body">
        <div class="meta-top">
          <span class="badge ${p.badgeClass}">${esc(p.badge)}</span>
          <span class="date">${esc(p.dateStr)}</span>
        </div>
        <h2 class="title"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a></h2>
        ${p.outlet ? `<div class="outlet"><b>${esc(p.outlet)}</b></div>` : ""}
        ${dek}
        <div class="tags">${tags}</div>
      </div>
      <div class="card-foot">
        <a class="foot-link" href="${esc(p.url)}" target="_blank" rel="noopener">Read on FDD &rarr;</a>
        ${source}
        ${watch}
      </div>
    </article>`;
  }

  const mapSets = window.MAP_SETS || [];

  function fileName(path) { return path.split("/").pop(); }

  function mapSection(set, i) {
    const thumbs = set.images.map((src, j) =>
      `<button class="map-thumb" data-set="${i}" data-i="${j}">
        <img loading="lazy" src="${esc(src)}" alt="${esc(set.title)} — ${j + 1}" />
      </button>`
    ).join("");
    return `<section class="map-set" data-set="${i}">
      <div class="map-set-head">
        <h2 class="map-title">${esc(set.title)}</h2>
        <span class="map-counter">${set.images.length} maps</span>
      </div>
      <div class="map-thumb-grid">${thumbs}</div>
    </section>`;
  }

  function renderMaps() {
    els.maps.innerHTML = mapSets.length
      ? mapSets.map(mapSection).join("")
      : `<div class="empty">No maps yet.</div>`;
  }

  const lb = { set: 0, i: 0 };

  function updateLightbox() {
    const set = mapSets[lb.set];
    const src = set.images[lb.i];
    els.lightbox.querySelector(".lb-img").src = src;
    els.lightbox.querySelector(".lb-img").alt = `${set.title} — ${lb.i + 1}`;
    els.lightbox.querySelector(".lb-counter").textContent = `${lb.i + 1} / ${set.images.length}`;
    const dl = els.lightbox.querySelector(".lb-dl");
    dl.href = src;
    dl.setAttribute("download", fileName(src));
  }

  function openLightbox(setIdx, i) {
    lb.set = setIdx;
    lb.i = i;
    updateLightbox();
    els.lightbox.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeLightbox() {
    els.lightbox.hidden = true;
    document.body.style.overflow = "";
  }

  function lbNav(dir) {
    const n = mapSets[lb.set].images.length;
    lb.i = ((lb.i + dir) % n + n) % n;
    updateLightbox();
  }

  function updateFiltersCount() {
    const n = ["year", "issue", "program", "outlet"].filter((k) => state[k]).length
      + (state.videoOnly ? 1 : 0);
    els.filtersCount.textContent = String(n);
    els.filtersCount.hidden = n === 0;
  }

  function setFiltersOpen(open) {
    els.filters.hidden = !open;
    els.filtersToggle.setAttribute("aria-expanded", String(open));
    localStorage.setItem("filtersOpen", open ? "1" : "0");
  }

  els.filtersToggle.addEventListener("click", () => setFiltersOpen(els.filters.hidden));
  setFiltersOpen(localStorage.getItem("filtersOpen") === "1");

  function render() {
    updateFiltersCount();
    const mapsMode = state.type === "Maps";
    els.maps.hidden = !mapsMode;
    els.grid.hidden = mapsMode;
    els.resultBar.hidden = mapsMode;
    if (mapsMode) { renderMaps(); return; }
    const list = all.filter(matches).sort(sortFn);
    els.count.innerHTML = `<b>${list.length}</b> of ${all.length} posts`;
    els.grid.innerHTML = list.length
      ? list.map(card).join("")
      : `<div class="empty" style="grid-column:1/-1;">No posts match your filters.</div>`;
  }

  els.q.addEventListener("input", (e) => { state.q = e.target.value; render(); });
  els.year.addEventListener("change", (e) => { state.year = e.target.value; render(); });
  els.issue.addEventListener("change", (e) => { state.issue = e.target.value; render(); });
  els.program.addEventListener("change", (e) => { state.program = e.target.value; render(); });
  els.outlet.addEventListener("change", (e) => { state.outlet = e.target.value; render(); });
  els.videoOnly.addEventListener("change", (e) => { state.videoOnly = e.target.checked; render(); });
  els.sort.addEventListener("change", (e) => { state.sort = e.target.value; render(); });

  els.typeSeg.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    state.type = btn.dataset.type;
    [...els.typeSeg.children].forEach((b) => b.classList.toggle("on", b === btn));
    render();
  });

  els.grid.addEventListener("click", (e) => {
    const t = e.target.closest(".tag");
    if (!t) return;
    state.issue = t.dataset.issue;
    els.issue.value = state.issue;
    window.scrollTo({ top: 0, behavior: "smooth" });
    render();
  });

  els.maps.addEventListener("click", (e) => {
    const thumb = e.target.closest(".map-thumb");
    if (!thumb) return;
    openLightbox(Number(thumb.dataset.set), Number(thumb.dataset.i));
  });

  els.lightbox.addEventListener("click", (e) => {
    if (e.target === els.lightbox || e.target.closest(".lb-close")) { closeLightbox(); return; }
    const nav = e.target.closest(".lb-nav");
    if (nav) lbNav(Number(nav.dataset.dir));
  });

  document.addEventListener("keydown", (e) => {
    if (els.lightbox.hidden) return;
    if (e.key === "Escape") closeLightbox();
    else if (e.key === "ArrowLeft") lbNav(-1);
    else if (e.key === "ArrowRight") lbNav(1);
  });

  els.clear.addEventListener("click", () => {
    Object.assign(state, { q: "", type: "all", year: "", issue: "", program: "", outlet: "", videoOnly: false, sort: "newest" });
    els.q.value = ""; els.year.value = ""; els.issue.value = ""; els.program.value = "";
    els.outlet.value = ""; els.videoOnly.checked = false; els.sort.value = "newest";
    [...els.typeSeg.children].forEach((b) => b.classList.toggle("on", b.dataset.type === "all"));
    render();
  });

  render();
})();
