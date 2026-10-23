(function () {
  const $ = (id) => document.getElementById(id);
  $("footYear").textContent = new Date().getFullYear();
  const root = $("readerArticle");
  const esc = (s) => (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (d) => d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (e) { return ""; } };

  const slug = new URLSearchParams(location.search).get("a") || "";
  if (!/^[a-z0-9-]+$/.test(slug)) return fail();

  fetch(`content/reader/${slug}.json`)
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(render)
    .catch(fail);

  function fail() {
    root.innerHTML = `<p class="reader-status">This article isn't available on this site. <a href="index.html">Back to all work</a>.</p>`;
  }

  function links(a) {
    const out = [`<a class="reader-link" href="${esc(a.fddUrl)}" target="_blank" rel="noopener">Read on FDD &#8599;</a>`];
    if (a.sourceUrl && host(a.sourceUrl) !== host(a.fddUrl)) {
      const label = a.outlet ? `Original at ${esc(a.outlet)}` : `Original at ${esc(host(a.sourceUrl))}`;
      out.push(`<a class="reader-link" href="${esc(a.sourceUrl)}" target="_blank" rel="noopener">${label} &#8599;</a>`);
    }
    if (a.kind === "pdf") {
      out.unshift(`<a class="reader-link primary" href="${encodeURI(a.pdf)}" target="_blank" rel="noopener">Open PDF &#8599;</a>`);
    }
    return out.join("");
  }

  function render(a) {
    document.title = `${a.title} — Cleo Paskal`;
    const d = a.date ? new Date(a.date) : null;
    const authors = (a.authors || []).join(", ");
    const tags = (a.issues || []).map((t) => `<a class="tag" href="index.html#issue=${encodeURIComponent(t)}">${esc(t)}</a>`).join("");
    const body = a.kind === "pdf"
      ? `<div class="reader-pdf"><iframe src="${encodeURI(a.pdf)}" title="${esc(a.title)} (PDF)" loading="lazy"></iframe></div>`
      : `<div class="reader-body">${a.html}</div>`;
    root.innerHTML = `
      <header class="reader-head">
        <div class="meta-top">
          <span class="badge article">${esc(a.category || "Analysis")}</span>
          ${d ? `<span class="date">${esc(fmt(d))}</span>` : ""}
        </div>
        <h1 class="reader-title">${esc(a.title)}</h1>
        ${a.subtitle ? `<p class="reader-dek">${esc(a.subtitle)}</p>` : ""}
        <div class="reader-byline">
          ${authors ? `<span>By <b>${esc(authors)}</b></span>` : ""}
          ${a.outlet ? `<span>Originally published in <b>${esc(a.outlet)}</b></span>` : ""}
        </div>
        <div class="reader-links">${links(a)}</div>
      </header>
      ${body}
      <footer class="reader-foot">
        ${tags ? `<div class="tags">${tags}</div>` : ""}
        <div class="reader-links">${links(a)}</div>
      </footer>`;
  }
})();
