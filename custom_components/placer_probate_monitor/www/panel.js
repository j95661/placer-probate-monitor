const PPM_CSS = `
  .ppm-wrap { font: 15px/1.45 "Segoe UI", system-ui, sans-serif; color: #1c1915; background: #f7f3ec; min-height: 100%; }
  .ppm-wrap header { background: #1b2a4a; color: #f7f3ec; padding: 20px 24px; }
  .ppm-wrap header p { margin: 4px 0 0; color: #c9c3b8; font-size: 13px; }
  .ppm-wrap header a { color: #f3d089; word-break: break-all; }
  .ppm-wrap header .ppm-outside-link { font-size: 12px; }
  .ppm-wrap header .ppm-version { margin: 0 0 8px; font-size: 12px; letter-spacing: .04em; color: #c9c3b8; }
  .ppm-wrap header .ppm-app-nav { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
  .ppm-wrap details.ppm-fold { margin-top: 10px; }
  .ppm-wrap details.ppm-fold > summary {
    cursor: pointer; font-weight: 600; color: #1b2a4a; list-style: none;
  }
  .ppm-wrap details.ppm-fold > summary::-webkit-details-marker { display: none; }
  .ppm-wrap details.ppm-fold > summary::before { content: "▸ "; color: #b0893e; }
  .ppm-wrap details.ppm-fold[open] > summary::before { content: "▾ "; }
  .ppm-wrap h1 { margin: 0; font-size: 22px; }
  .ppm-page-intro { padding: 16px 20px 0; max-width: 1180px; }
  .ppm-page-intro.ppm-wide { max-width: 1440px; }
  .ppm-page-title { margin: 0; font-size: 18px; text-transform: none; color: #1b2a4a; }
  .ppm-page-intro > p { margin: 6px 0 0; color: #6b645b; font-size: 13px; }
  .ppm-page-intro .ppm-tabs { margin-top: 12px; }
  .ppm-page-intro .ppm-tabs button.ghost { color: #1c1915; border-color: #8a93a8; }
  .ppm-hide { display: none !important; }
  .ppm-wrap h2 { margin: 0 0 12px; font-size: 15px; text-transform: uppercase; color: #1b2a4a; }
  .ppm-wrap main { padding: 20px; display: grid; gap: 16px; max-width: 1180px; }
  .ppm-wrap main.ppm-wide { max-width: 1440px; }
  .ppm-fub-layout { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 16px; align-items: start; }
  .ppm-fub-side { position: sticky; top: 12px; max-height: calc(100vh - 28px); overflow: auto; }
  .ppm-assoc { font-size: 11px; color: #6b645b; }
  @media (max-width: 1100px) {
    .ppm-fub-layout { grid-template-columns: 1fr; }
    .ppm-fub-side { position: static; max-height: none; }
  }
  .ppm-card { background: #fffdf8; border: 1px solid #ddd6cc; border-radius: 10px; padding: 16px 18px; }
  .ppm-wrap label { display: block; font-size: 12px; font-weight: 600; color: #6b645b; margin: 10px 0 4px; }
  .ppm-wrap input, .ppm-wrap textarea, .ppm-wrap select {
    width: 100%; border: 1px solid #ddd6cc; border-radius: 6px; padding: 8px 10px; font: inherit; box-sizing: border-box; background: #fff;
  }
  .ppm-wrap textarea { min-height: 64px; }
  .ppm-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .ppm-layout { display: grid; grid-template-columns: 220px 1fr; gap: 16px; align-items: start; }
  @media (max-width: 800px) { .ppm-layout, .ppm-row { grid-template-columns: 1fr; } }
  .ppm-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
  .ppm-wrap button { border: 0; border-radius: 6px; padding: 8px 12px; font: inherit; cursor: pointer; background: #1b2a4a; color: #fff; }
  .ppm-wrap button.secondary { background: #ece7de; color: #1c1915; }
  .ppm-wrap button.ghost { background: transparent; color: #f7f3ec; border: 1px solid #8a93a8; }
  .ppm-wrap button.ghost.active, .ppm-tabs button.active { background: #b0893e; border-color: #b0893e; color: #fff; }
  .ppm-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
  .ppm-note { color: #6b645b; font-size: 12px; margin-top: 8px; }
  .ppm-banner { padding: 8px 10px; border-radius: 6px; margin-bottom: 10px; display: none; white-space: pre-wrap; }
  .ppm-banner.show { display: block; }
  .ppm-banner.ok { background: #e7f4ec; color: #2d6a4f; }
  .ppm-banner.err { background: #f8e8e8; color: #8b2e2e; }
  .ppm-banner.wait { background: #f3e3c3; color: #6b4f1a; }
  .ppm-job-banner { display: none; margin-top: 12px; padding: 8px 10px; border-radius: 6px; font-size: 13px; white-space: pre-wrap; }
  .ppm-job-banner.show { display: block; }
  .ppm-job-banner.ok { background: #e7f4ec; color: #2d6a4f; }
  .ppm-job-banner.err { background: #f8e8e8; color: #8b2e2e; }
  .ppm-job-banner.wait { background: #f3e3c3; color: #6b4f1a; }
  .ppm-wrap table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .ppm-wrap th, .ppm-wrap td { text-align: left; padding: 8px 6px; border-bottom: 1px solid #ddd6cc; vertical-align: top; }
  .ppm-toggle { display: flex; gap: 8px; margin: 8px 0; align-items: flex-start; }
  .ppm-toggle input { width: auto; margin-top: 3px; }
  .ppm-pill { display: inline-block; padding: 2px 8px; border-radius: 999px; background: #ece7de; font-size: 11px; }
  .ppm-pill.live { background: #e7f4ec; color: #2d6a4f; }
  .ppm-pill.wait { background: #f3e3c3; }
  .ppm-pill.off { background: #f8e8e8; color: #8b2e2e; }
  .ppm-sourcelist button { display: block; width: 100%; text-align: left; margin: 0 0 8px; background: #ece7de; color: #1c1915; }
  .ppm-sourcelist button.active { background: #1b2a4a; color: #fff; }
  .ppm-wrap .ppm-tabs button.secondary.active { background: #1b2a4a; color: #fff; }
  .ppm-compare { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 12px; }
  @media (max-width: 900px) { .ppm-compare { grid-template-columns: 1fr; } }
  .ppm-wrap td a { color: #1b2a4a; word-break: break-all; }
  .ppm-pre { white-space: pre-wrap; font: 12px/1.4 ui-monospace, Consolas, monospace; margin: 0; }
  .ppm-table-wrap { overflow-x: auto; }
  .ppm-wrap main.ppm-listings { max-width: 1440px; }
  .ppm-listings-tools { display: grid; grid-template-columns: 2fr 1fr 1fr auto; gap: 10px; align-items: end; }
  @media (max-width: 900px) { .ppm-listings-tools { grid-template-columns: 1fr; } }
  .ppm-th-sort { cursor: pointer; user-select: none; white-space: nowrap; }
  .ppm-th-sort:hover { color: #b0893e; }
  .ppm-sort-ind { font-size: 11px; color: #b0893e; margin-left: 4px; }
  .ppm-filter-row th { border-bottom: 1px solid #ddd6cc; padding-top: 0; font-weight: 400; }
  .ppm-filter-row input, .ppm-filter-row select { font-size: 12px; padding: 4px 6px; margin: 0; }
`;

const PPM_PANEL_VERSION = "1.3.156";

function ppmParseAppView(hash) {
  const raw = String(hash || "").replace(/^#\/?/, "").split("?")[0].toLowerCase();
  if (raw === "listings" || raw === "placer-probate-listings") return "listings";
  if (raw === "sources" || raw === "placer-probate-sources") return "sources";
  return "fub";
}

function ppmAppHeaderHtml(active) {
  const view = ppmParseAppView(active);
  const links = [
    ["fub", "Follow Up Boss"],
    ["listings", "Probate listings"],
    ["sources", "Probate sources"],
  ].map(([id, label]) => (
    `<button type="button" class="ghost${view === id ? " active" : ""}" data-ppm-view="${id}">${label}</button>`
  )).join("");
  return `
    <header>
      <p class="ppm-version">Version ${PPM_PANEL_VERSION}</p>
      <h1>Hammond Realty</h1>
      <p class="ppm-outside-link" hidden>
        <a id="ppm-listings-share" href="#" target="_blank" rel="noopener"></a>
      </p>
      <p>Home is Follow Up Boss. Probate listings and Probate sources stay in this header.</p>
      <nav class="ppm-app-nav" aria-label="Hammond Realty">${links}</nav>
      <div id="ppm-job-banner" class="ppm-job-banner" role="status" aria-live="polite"></div>
    </header>
  `;
}

function ppmOcrNote(st) {
  const ocr = (st && st.ocr) || {};
  if (ocr.ready) {
    return `<p class="ppm-note">Petition OCR is on (${ppmEsc(ocr.engine)}). Rescan local files on Placer and Sacramento so image DE-111s can become GO and Follow Up Boss can POST new people.</p>`;
  }
  if (ocr.engine === "installing") {
    return `<p class="ppm-note">Petition OCR is installing on this Home Assistant box (RapidOCR, once). Wait until this note says RapidOCR, then Rescan local files for both counties. The sidebar stays up while that install runs.</p>`;
  }
  if (ocr.enabled === false) {
    return `<p class="ppm-note">Petition OCR is turned off (PPM_PETITION_OCR=0). Image petitions stay native-text only.</p>`;
  }
  return `<p class="ppm-note">Petition OCR is not ready yet on this box. Reload 1.3.156, wait until this note says Tesseract or RapidOCR, then Rescan local files on Placer and Sacramento.</p>`;
}

function ppmSleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function ppmSafeJobStatus(hass) {
  if (!hass || typeof hass.callApi !== "function") return null;
  try {
    return await hass.callApi("GET", "placer_probate_monitor/job");
  } catch (_err) {
    return null;
  }
}

const ppmJobWatch = {
  hass: null,
  timer: null,
  last: null,
  listeners: new Set(),
  start(hass) {
    if (hass) this.hass = hass;
    if (this.timer || !this.hass) return;
    this._tick();
    this.timer = window.setInterval(() => this._tick(), 3000);
  },
  stop() {
    if (this.timer) window.clearInterval(this.timer);
    this.timer = null;
  },
  subscribe(fn) {
    this.listeners.add(fn);
    if (this.last) {
      try { fn(this.last); } catch (_err) { /* ignore stale view */ }
    }
    return () => this.listeners.delete(fn);
  },
  async _tick() {
    const st = await ppmSafeJobStatus(this.hass);
    if (!st || st.error) return;
    this.last = st;
    this.listeners.forEach((fn) => {
      try { fn(st); } catch (_err) { /* ignore stale view */ }
    });
  },
};

function ppmText(value) {
  if (value == null || value === "") return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value instanceof Error) return value.message || "Error";
  if (typeof value === "object") {
    if (typeof value.message === "string" && value.message) return value.message;
    if (typeof value.error === "string" && value.error) return value.error;
    if (value.error && typeof value.error === "object") return ppmText(value.error);
    if (typeof value.body === "string" && value.body) return value.body;
    try {
      const dumped = JSON.stringify(value);
      return dumped && dumped !== "{}" ? dumped : "Request failed";
    } catch (_exc) {
      return "Request failed";
    }
  }
  return String(value);
}

async function ppmRunJob(hass, action, extra, onTick) {
  const before = (await ppmSafeJobStatus(hass)) || {};
  const beforeRun = before.last_run;
  try {
    await hass.callApi("POST", "placer_probate_monitor/job", { action, ...(extra || {}) });
  } catch (err) {
    const text = ppmText(err);
    if (!before.running && !/already in progress|409/i.test(text)) {
      throw new Error(text || "Could not start the job.");
    }
  }
  ppmJobWatch.start(hass);
  for (let i = 0; i < 1200; i += 1) {
    await ppmSleep(3000);
    const st = await ppmSafeJobStatus(hass);
    if (!st) continue;
    if (typeof onTick === "function") onTick(ppmStampJobCounty(st, extra));
    if (st.running) continue;
    if (st.last_run && st.last_run !== beforeRun) {
      return ppmStampJobCounty(st, extra);
    }
    if (i >= 1 && !st.running && st.last_error && st.last_run === beforeRun) {
      return ppmStampJobCounty(st, extra);
    }
  }
  const last = (await ppmSafeJobStatus(hass)) || {};
  const live = ppmJobLiveMessage(ppmStampJobCounty(last, extra));
  return ppmStampJobCounty({
    ...last,
    last_result: "running",
    last_error: live
      ? `Still running: ${live}`
      : "Still running after 60 minutes. The job keeps going in Home Assistant. Check Status or last_run.log.",
  }, extra);
}

function ppmBannerKind(ok) {
  if (ok === "wait" || ok === "running") return "wait";
  return ok ? "ok" : "err";
}

function ppmPreviewCounty(rec, st) {
  const raw = String(
    (rec && (rec.source_id || rec.data_source))
    || (st && st.source_id)
    || ""
  ).toLowerCase();
  return raw === "sacramento" ? "sacramento" : "placer";
}

function ppmStampJobCounty(st, extra) {
  if (!st) return st;
  const raw = String(
    (st.source_id)
    || ((st.progress && st.progress.source_id) || "")
    || ((extra && extra.source_id) || "")
  ).toLowerCase();
  if (raw === "placer" || raw === "sacramento") {
    return { ...st, source_id: st.source_id || raw };
  }
  return st;
}

function ppmJobCountyLabel(st) {
  const p = (st && st.progress) || {};
  const raw = String(p.source_id || (st && st.source_id) || "").toLowerCase();
  if (raw === "sacramento") return "Sacramento";
  if (raw === "placer") return "Placer";
  return "";
}

function ppmWithCountyPrefix(text, st) {
  const msg = String(text || "").trim();
  if (!msg) return msg;
  const label = ppmJobCountyLabel(st);
  if (!label) return msg;
  const low = msg.toLowerCase();
  if (low.startsWith("placer") || low.startsWith("sacramento") || low.includes(label.toLowerCase())) return msg;
  return `${label} ${msg}`;
}

function ppmJobLiveMessage(st) {
  const p = (st && st.progress) || {};
  if (p.message) return ppmWithCountyPrefix(p.message, st);
  if (st && st.running) {
    const source = String(p.source_id || st.source_id || "").toLowerCase();
    if (source === "sacramento") return "Sacramento job is running…";
    if (source === "placer") return "Placer job is running…";
    return "Probate job is running…";
  }
  return "";
}

function ppmJobBannerState(st) {
  if (!st || st.error) return { text: "", kind: "" };
  if (st.running || st.last_result === "running") {
    return { text: ppmJobLiveMessage(st) || "Probate job is running…", kind: "wait" };
  }
  if (st.last_result === "failed") {
    return {
      text: ppmWithCountyPrefix(ppmText(st.last_error) || "Job failed. Check last_run.log.", st),
      kind: "err",
    };
  }
  if (st.last_run) {
    return { text: ppmJobDoneMessage(st), kind: "ok" };
  }
  return { text: "", kind: "" };
}

function ppmJobDoneMessage(st) {
  if (!st) return "Job finished.";
  if (st.last_result === "running") {
    return ppmWithCountyPrefix(
      ppmText(st.last_error) || "Still running. Check Status or last_run.log.",
      st,
    );
  }
  const county = ppmJobCountyLabel(st);
  const bits = [
    county
      ? `${county} finished (${st.last_result || "ok"})`
      : `Finished (${st.last_result || "ok"})`,
  ];
  const go = st.go_count != null ? st.go_count : (st.progress && st.progress.go_count);
  const nogo = st.nogo_count != null ? st.nogo_count : (st.progress && st.progress.nogo_count);
  if (st.local_audit) {
    const notices = st.notice_count != null ? st.notice_count : (st.progress && st.progress.notice_count);
    const flagged = st.new_count != null ? st.new_count : (st.progress && st.progress.new_count);
    if (notices != null) bits.push(`${notices} stored cases`);
    if (flagged != null) bits.push(`${flagged} flagged`);
    bits.push("no scrape, Follow Up Boss not updated");
    return ppmWithCountyPrefix(bits.join(" · "), st);
  }
  if (st.stored_test || (go != null && nogo != null && (st.fub_verify_note || "").toLowerCase().includes("stored test"))) {
    const notices = st.notice_count != null ? st.notice_count : (st.progress && st.progress.notice_count);
    if (notices != null) bits.push(`${notices} stored cases`);
    if (go != null) bits.push(`${go} GO`);
    if (nogo != null) bits.push(`${nogo} no-go`);
    bits.push("no scrape");
    if (st.fub_posted != null || st.fub_updated != null) {
      bits.push(
        `FUB posted ${st.fub_posted ?? 0}, updated ${st.fub_updated ?? 0}, skipped ${st.fub_skipped ?? 0}`,
      );
    } else {
      bits.push("Follow Up Boss not updated");
    }
    return ppmWithCountyPrefix(bits.join(" · "), st);
  }
  const notices = st.notice_count != null ? st.notice_count : (st.progress && st.progress.notice_count);
  const neu = st.new_count != null ? st.new_count : (st.progress && st.progress.new_count);
  if (notices != null) bits.push(`${notices} unique CNPA notices`);
  if (neu != null) bits.push(`${neu} new`);
  if (st.fub_posted != null || st.fub_updated != null) {
    bits.push(
      `FUB posted ${st.fub_posted ?? 0}, updated ${st.fub_updated ?? 0}, skipped ${st.fub_skipped ?? 0}`,
    );
  }
  if (st.fub_error) bits.push(`FUB: ${ppmText(st.fub_error)}`);
  return ppmWithCountyPrefix(bits.join(" · "), st);
}

function ppmCountyStored(data, sourceId) {
  const counties = (data && data.counties) || [];
  return counties.find((item) => item.id === sourceId) || counties[0] || null;
}

function ppmStoredCountyTable(county) {
  const rows = (county.cases || []).map((item) => {
    const files = (item.files || []).join(", ") || "—";
    const de111 = item.has_de111 ? '<span class="ppm-pill live">DE-111</span>' : '<span class="ppm-pill off">no DE-111</span>';
    const de147 = item.has_de147 ? '<span class="ppm-pill live">DE-147</span>' : '<span class="ppm-pill wait">no DE-147</span>';
    return `<tr><td>${ppmEsc(item.case_number)}</td><td>${de111} ${de147}</td><td>${ppmEsc(files)}</td></tr>`;
  }).join("");
  if (!rows) {
    return `<p class="ppm-note">${ppmEsc(county.id || "County")}: no public petition PDFs in this folder yet.</p>`;
  }
  return `<h3 style="margin:12px 0 6px;font-size:13px;text-transform:uppercase;">${ppmEsc(county.id || "County")}</h3>
    <div class="ppm-table-wrap"><table><thead><tr><th>Case</th><th>Forms</th><th>Files</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function ppmStoredDocsCard(data, sourceId) {
  const hint = (data && data.copy_hint) || "";
  const counties = sourceId
    ? [ppmCountyStored(data, sourceId)].filter(Boolean)
    : ((data && data.counties) || []);
  if (!counties.length) {
    return `<section class="ppm-card" id="stored-docs">
      <h2>Stored PDFs on this Home Assistant</h2>
      <p class="ppm-note">${ppmEsc(hint || "No petition PDFs found yet. Run a county job once to download DE-111/DE-147 files.")}</p>
    </section>`;
  }
  const caseCount = counties.reduce((sum, item) => sum + (item.case_count || 0), 0);
  const pdfCount = counties.reduce((sum, item) => sum + (item.pdf_count || 0), 0);
  const buttons = counties.map((county) => {
    const count = county.pdf_count || 0;
    const id = county.id || sourceId || "";
    return `<button class="secondary" type="button" data-stored-zip="${ppmEsc(id)}"${count ? "" : " disabled"}>Download ${ppmEsc(id)} PDFs as zip</button>`;
  }).join("");
  const paths = counties.map((county) => (
    `${county.id}: ${county.ha_path} (${county.case_count || 0} cases, ${county.pdf_count || 0} PDFs)`
  )).join(" · ");
  const folded = counties.map(ppmStoredCountyTable).join("");
  return `<section class="ppm-card" id="stored-docs">
    <h2>Stored PDFs on this Home Assistant</h2>
    <p class="ppm-note">${ppmEsc(hint)}</p>
    <p class="ppm-note">${ppmEsc(paths)}. Laptop copy target uses data/reports/docs and data/reports/sacramento/docs.</p>
    <div class="ppm-actions">${buttons}</div>
    <details class="ppm-fold">
      <summary>Show stored case list (${caseCount} case${caseCount === 1 ? "" : "s"}, ${pdfCount} PDF${pdfCount === 1 ? "" : "s"})</summary>
      ${folded}
    </details>
  </section>`;
}

async function ppmDownloadStoredZip(hass, sourceId) {
  const token = hass && hass.auth && hass.auth.data && hass.auth.data.access_token;
  if (!token) throw new Error("Not signed in.");
  const qs = sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : "";
  const resp = await fetch(`/api/placer_probate_monitor/stored_docs/zip${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    let message = `Download failed (${resp.status}).`;
    try {
      const payload = await resp.json();
      message = payload.message || payload.error || message;
    } catch (_) { /* keep status message */ }
    throw new Error(message);
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = sourceId ? `probate-stored-pdfs-${sourceId}.zip` : "probate-stored-pdfs.zip";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function ppmAuditIssuesCard(st) {
  const issues = (st && st.audit_issues) || [];
  if (!(st && st.local_audit) && !issues.length) {
    return `<section class="ppm-card" id="local-audit-results">
      <h2>Last local audit</h2>
      <details class="ppm-fold">
        <summary>Show local audit</summary>
        <p class="ppm-note">Run Audit stored cases for issue / recommended solution pairs. That job does not scrape CNPA or court portals and does not post to Follow Up Boss. It also runs weekly at 8:00 PM on the configured weekly day.</p>
      </details>
    </section>`;
  }
  const rows = issues.map((item) => {
    const cases = (item.cases || []).slice(0, 8).join(", ");
    const extra = (item.count || 0) - Math.min(8, (item.cases || []).length);
    const caseText = extra > 0 ? `${cases} (+${extra} more)` : cases;
    return `<tr>
      <td>${ppmEsc(item.issue || "")}</td>
      <td>${ppmEsc(item.solution || "")}</td>
      <td>${ppmEsc(item.count || 0)}</td>
      <td>${ppmEsc(caseText || "—")}</td>
    </tr>`;
  }).join("");
  const table = rows
    ? `<div class="ppm-table-wrap"><table><thead><tr><th>Issue</th><th>Recommended solution</th><th>Count</th><th>Example cases</th></tr></thead><tbody>${rows}</tbody></table></div>`
    : `<p class="ppm-note">No issues. Keep the daily harvest as-is.</p>`;
  const count = issues.length;
  return `<section class="ppm-card" id="local-audit-results">
    <h2>Last local audit</h2>
    <p class="ppm-note">${ppmEsc(ppmJobDoneMessage(st))}</p>
    <details class="ppm-fold">
      <summary>Show issues and recommended solutions (${count})</summary>
      ${table}
    </details>
  </section>`;
}

function ppmStoredTestCard(st) {
  const cases = (st && st.stored_cases) || [];
  const go = st && st.go_count;
  const nogo = st && st.nogo_count;
  const note = (st && st.fub_verify_note) || "";
  const stored = !!(st && (st.stored_test || cases.length || (note && note.toLowerCase().includes("stored test"))));
  if (!stored && go == null) {
    return `<section class="ppm-card" id="stored-test-results">
      <h2>Last stored-data test</h2>
      <p class="ppm-note">Run Test stored data to parse PDFs already on this box and count GO vs no-go. It does not scrape CNPA or court portals and does not post to Follow Up Boss. After the scores look right, use Push stored GOs to Follow Up Boss.</p>
    </section>`;
  }
  const rows = cases.map((item) => {
    const gate = item.gate === "go"
      ? '<span class="ppm-pill live">GO</span>'
      : '<span class="ppm-pill off">NO-GO</span>';
    return `<tr>
      <td>${ppmEsc(item.case || "")}</td>
      <td>${gate}</td>
      <td>${ppmEsc(item.reason || "")}</td>
      <td>${ppmEsc(item.petitioner || "—")}</td>
      <td>${ppmEsc(item.petition_pdf || "—")}</td>
    </tr>`;
  }).join("");
  const table = rows
    ? `<div class="ppm-table-wrap"><table><thead><tr><th>Case</th><th>Gate</th><th>Reason</th><th>Petitioner</th><th>DE-111 file</th></tr></thead><tbody>${rows}</tbody></table></div>`
    : "";
  return `<section class="ppm-card" id="stored-test-results">
    <h2>Last stored-data test</h2>
    <p class="ppm-note">${ppmEsc(note || `${go ?? 0} GO / ${nogo ?? 0} no-go. Follow Up Boss not updated.`)}</p>
    ${table}
  </section>`;
}

function ppmEsc(value) {
  return ppmText(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function ppmXml(value) {
  return ppmEsc(value).replace(/\r/g, "&#13;").replace(/\n/g, "&#10;");
}

function ppmDownloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function ppmDownloadAuthFile(hass, apiPath, filename) {
  const token = hass && hass.auth && hass.auth.data && hass.auth.data.access_token;
  if (!token) throw new Error("Not signed in.");
  const resp = await fetch(`/api/placer_probate_monitor/${apiPath}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    let message = `Download failed (${resp.status}).`;
    try {
      const payload = await resp.json();
      message = payload.message || payload.error || message;
    } catch (_) { /* keep status message */ }
    throw new Error(message);
  }
  ppmDownloadBlob(filename, await resp.blob());
}

async function ppmExportFubReview(hass, sourceId) {
  const qs = sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : "";
  await ppmDownloadAuthFile(hass, `fub_review.csv${qs}`, "fub-review.csv");
  await ppmDownloadAuthFile(hass, `fub_review.xlsx${qs}`, "fub-review.xlsx");
}

function ppmCsvCell(value) {
  const text = value == null ? "" : String(value);
  if (/[",\r\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

function ppmPublicBase(hass) {
  try {
    if (hass && typeof hass.hassUrl === "function") {
      const url = String(hass.hassUrl("/")).replace(/\/$/, "");
      if (url) return url;
    }
  } catch (_exc) { /* ignore */ }
  const data = hass && hass.auth && hass.auth.data;
  if (data && data.hassUrl) return String(data.hassUrl).replace(/\/$/, "");
  if (typeof window !== "undefined" && window.location && window.location.origin) {
    return window.location.origin;
  }
  return "";
}

function ppmListingsShareUrl(hass, share) {
  const meta = share || {};
  if (meta.share_url) return String(meta.share_url);
  const token = meta.share_token;
  if (!token) return "";
  const path = meta.share_path || "/api/placer_probate_monitor/listings/public";
  const qs = new URLSearchParams({ token: String(token) });
  if (meta.share_exp) qs.set("exp", String(meta.share_exp));
  return `${ppmPublicBase(hass)}${path}?${qs.toString()}`;
}

function ppmListingFubLabel(row) {
  const status = String(row.fub_status || "");
  if (status === "deleted" || row.fub_removed) return "deleted";
  if (status === "id" && row.fub_person_id) return String(row.fub_person_id);
  if (status === "id") return "ID";
  return "no id";
}

function ppmListingGoLabel(row) {
  const status = String((row && row.go_status) || "").trim();
  const compact = status.toLowerCase().replace(/[\s_-]/g, "");
  if (compact === "go") return "GO";
  if (compact === "nogo") return "NO-GO";
  return status;
}

function ppmNabuOrigin(value) {
  const text = String(value || "").trim();
  if (!text || text.toLowerCase().indexOf("hooks.nabu.casa") >= 0) return "";
  let host = text;
  try {
    const parsed = new URL(text.indexOf("://") === -1 ? `https://${text}` : text);
    host = parsed.hostname || "";
  } catch (_err) {
    host = text.split("/")[0].split(":")[0];
  }
  host = String(host || "").toLowerCase().replace(/\.$/, "");
  if (host === "hooks.nabu.casa") return "";
  if (host === "ui.nabu.casa" || host.endsWith(".ui.nabu.casa")) return `https://${host}`;
  return "";
}

function ppmIsPrivateDocumentHost(host, port) {
  const name = String(host || "").toLowerCase().replace(/\.$/, "");
  if (!name || name === "localhost" || name === "127.0.0.1" || name === "::1") return true;
  if (name.endsWith(".local") || name.endsWith(".home") || name.endsWith(".localdomain")) return true;
  if (/^(10\.|192\.168\.|169\.254\.|127\.)/.test(name)) return true;
  if (/^172\.(1[6-9]|2\d|3[0-1])\./.test(name)) return true;
  if (String(port || "") === "8123") return true;
  if (name.indexOf(".") === -1) return true;
  return false;
}

function ppmListingDocHref(url, documentBase) {
  const raw = String(url || "").trim();
  const origin = ppmNabuOrigin(documentBase);
  if (!raw) return "";
  if (raw.startsWith("/") && !raw.startsWith("//")) {
    return origin ? origin + raw : "";
  }
  let parsed;
  try {
    parsed = new URL(raw.indexOf("://") === -1 ? `http://${raw}` : raw);
  } catch (_err) {
    return "";
  }
  const host = String(parsed.hostname || "").toLowerCase();
  if (host === "hooks.nabu.casa") return "";
  const path = `${parsed.pathname || ""}${parsed.search || ""}${parsed.hash || ""}`;
  if (host === "ui.nabu.casa" || host.endsWith(".ui.nabu.casa")) {
    return `https://${host}${path}`;
  }
  if (!origin) return "";
  if (ppmIsPrivateDocumentHost(host, parsed.port) || path.indexOf("/api/placer_probate_monitor/") === 0) {
    return origin + path;
  }
  return "";
}

async function ppmCloudRemoteOrigin(hass) {
  if (!hass || typeof hass.callApi !== "function") return "";
  try {
    const status = await hass.callApi("GET", "cloud/status");
    if (!status || status.logged_in === false) return "";
    const cert = status.remote_certificate || {};
    const prefs = status.prefs || {};
    const candidates = [
      status.remote_domain,
      status.remote_ui,
      cert.common_name,
      prefs.remote_domain,
      prefs.remote_ui,
    ];
    (cert.alternative_names || []).forEach((name) => candidates.push(name));
    for (let i = 0; i < candidates.length; i += 1) {
      const origin = ppmNabuOrigin(candidates[i]);
      if (origin) return origin;
    }
  } catch (_err) {
    return "";
  }
  return "";
}

function ppmListingDocEntries(row) {
  const rec = row || {};
  const items = Array.isArray(rec.docs) ? rec.docs : [];
  const out = [];
  items.forEach((item) => {
    if (!item) return;
    const label = String(item.label || "").trim();
    const url = String(item.url || "").trim();
    if (label && url) out.push({ label, url });
  });
  if (out.length) return out;
  if (rec.de111_url) out.push({ label: "DE-111", url: String(rec.de111_url) });
  if (rec.de147_url) out.push({ label: "DE-147", url: String(rec.de147_url) });
  return out;
}

function ppmListingDocs(row, documentBase) {
  return ppmListingDocEntries(row).map((item) => ({
    label: item.label,
    url: ppmListingDocHref(item.url, documentBase),
  })).filter((item) => item.url && item.url.indexOf("hooks.nabu.casa") === -1);
}

function ppmListingDocsLabel(row) {
  const labels = ppmListingDocEntries(row).map((item) => item.label);
  return labels.length ? labels.join(" ") : "";
}

function ppmListingGoReasonLabel(row) {
  const reason = String((row && (row.nogo_reason_label || row.nogo_reason)) || "").trim();
  if (reason === "path_a") return "Path A";
  if (reason === "path_b") return "Path B";
  if (reason === "missing_estate_real") return "Real property GMV missing";
  if (reason === "estate_real_below_minimum") return "Real property GMV under $200,000";
  return reason;
}

// --- listings table helpers ---
const PPM_LISTING_TABLE_COLUMNS = [
  { key: "date", label: "Date", kind: "date", placeholder: "contains or 2026-09..2026-10" },
  { key: "added_at", label: "Added", kind: "date", placeholder: "contains or 2026-09..2026-10" },
  { key: "source", label: "Source", kind: "text", placeholder: "contains" },
  { key: "case_number", label: "Case", kind: "text", placeholder: "contains" },
  { key: "docs", label: "Documents", kind: "docs", placeholder: "DE-111 / DE-147" },
  { key: "go_status", label: "GO/NO-GO", kind: "go", placeholder: "GO / NO-GO" },
  { key: "nogo_reason", label: "Status", kind: "text", placeholder: "path_a / fiduciary / …" },
  { key: "petitioner", label: "Petitioner", kind: "text", placeholder: "contains" },
  { key: "decedent", label: "Decedent", kind: "text", placeholder: "contains" },
  { key: "decedent_address", label: "Decedent address", kind: "text", placeholder: "contains" },
  { key: "hearing", label: "Hearing", kind: "text", placeholder: "contains" },
  { key: "estate_real", label: "estate_real", kind: "text", placeholder: "GMV / 0" },
  { key: "petition_ocr", label: "OCR", kind: "ocr", placeholder: "Yes / —" },
  { key: "fub_status", label: "Listings Status", kind: "fub", placeholder: "id / no id / deleted" },
];

function ppmListingAddedStamp(row) {
  return String(
    (row && (row.added_at || row.first_seen || row.first_collected || row.date || row.filed)) || ""
  );
}

function ppmListingColumnValue(row, key) {
  const rec = row || {};
  if (key === "added_at") return ppmListingAddedStamp(rec);
  if (key === "date") return String(rec.date || rec.filed || "");
  if (key === "fub_status") return ppmListingFubLabel(rec);
  if (key === "go_status") return ppmListingGoLabel(rec);
  if (key === "petition_ocr") return rec.petition_ocr ? "Yes" : "—";
  if (key === "nogo_reason") return ppmListingGoReasonLabel(rec);
  if (key === "docs") return ppmListingDocsLabel(rec);
  if (key === "petitioner") {
    return [rec.petitioner, rec.petitioner_address].filter(Boolean).join(" ");
  }
  return rec[key] == null ? "" : String(rec[key]);
}

function ppmListingParseDateFilter(text) {
  const raw = String(text || "").trim();
  if (!raw) return null;
  const range = raw.match(/^(\d{4}-\d{2}(?:-\d{2})?)\s*\.\.\s*(\d{4}-\d{2}(?:-\d{2})?)$/);
  if (range) {
    return {
      from: range[1].length === 7 ? `${range[1]}-01` : range[1],
      to: range[2].length === 7 ? `${range[2]}-31` : range[2],
    };
  }
  return { contains: raw.toLowerCase() };
}

function ppmListingMatchFilter(row, key, filterText, kind) {
  const raw = String(filterText || "").trim();
  if (!raw) return true;
  if (kind === "go") {
    const wanted = raw.toLowerCase().replace(/[\s_-]/g, "");
    const status = ppmListingGoLabel(row || {}).toLowerCase().replace(/[\s_-]/g, "");
    if (wanted === "nogo") return status === "nogo";
    if (wanted === "go") return status === "go";
    return ppmListingGoLabel(row || "").toLowerCase().includes(raw.toLowerCase());
  }
  if (kind === "fub") {
    const wanted = raw.toLowerCase().replace(/\s+/g, "_");
    const status = String((row || {}).fub_status || "").toLowerCase();
    const label = ppmListingFubLabel(row || {}).toLowerCase();
    if (wanted === "no_id" || wanted === "noid") return status === "no_id" || label === "no id";
    if (wanted === "deleted") return status === "deleted" || Boolean((row || {}).fub_removed);
    if (wanted === "id") return status === "id";
    return label.includes(raw.toLowerCase()) || status.includes(wanted);
  }
  if (kind === "ocr" || key === "petition_ocr") {
    const wanted = raw.toLowerCase().replace(/\s+/g, "");
    const flagged = Boolean((row || {}).petition_ocr);
    if (wanted === "yes" || wanted === "true" || wanted === "y" || wanted === "ocr") return flagged;
    if (wanted === "—" || wanted === "-" || wanted === "no" || wanted === "false" || wanted === "none") {
      return !flagged;
    }
    return ppmListingColumnValue(row, "petition_ocr").toLowerCase().includes(raw.toLowerCase());
  }
  if (kind === "docs" || key === "docs") {
    const label = ppmListingDocsLabel(row || "").toLowerCase();
    return label.includes(raw.toLowerCase());
  }
  if (key === "nogo_reason") {
    const code = String((row || {}).nogo_reason || "").toLowerCase();
    const label = ppmListingGoReasonLabel(row || {}).toLowerCase();
    const needle = raw.toLowerCase();
    const compact = needle.replace(/\s+/g, "_");
    return label.includes(needle) || code.includes(needle) || code.includes(compact);
  }
  const value = ppmListingColumnValue(row, key);
  if (kind === "date") {
    const parsed = ppmListingParseDateFilter(raw);
    if (parsed && parsed.from) {
      const stamp = value.length === 7 ? `${value}-01` : value;
      return stamp >= parsed.from && stamp <= parsed.to;
    }
  }
  return value.toLowerCase().includes(raw.toLowerCase());
}

function ppmListingApplyColumnFilters(rows, filters) {
  const list = Array.isArray(rows) ? rows : [];
  const entries = Object.entries(filters || {}).filter(([, value]) => String(value || "").trim());
  if (!entries.length) return list.slice();
  const kinds = Object.fromEntries(PPM_LISTING_TABLE_COLUMNS.map((col) => [col.key, col.kind]));
  return list.filter((row) => entries.every(([key, value]) => (
    ppmListingMatchFilter(row, key, value, kinds[key] || "text")
  )));
}

function ppmListingSortRows(rows, sortKey, sortDir) {
  const key = sortKey || "added_at";
  const dir = sortDir === "asc" ? 1 : -1;
  return (Array.isArray(rows) ? rows : []).slice().sort((left, right) => {
    const av = ppmListingColumnValue(left, key).toLowerCase();
    const bv = ppmListingColumnValue(right, key).toLowerCase();
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    const ac = String((left && left.case_number) || "");
    const bc = String((right && right.case_number) || "");
    if (ac < bc) return -1;
    if (ac > bc) return 1;
    return 0;
  });
}

function ppmListingVisibleRows(rows, options) {
  const opts = options || {};
  const filtered = ppmListingApplyColumnFilters(rows, opts.filters);
  return ppmListingSortRows(filtered, opts.sortKey || "added_at", opts.sortDir || "desc");
}
// --- end listings table helpers ---

function ppmListingExportRows(rows) {
  const headers = [
    ["added_at", "Added"],
    ["date", "Notice date"],
    ["source", "Source"],
    ["case_number", "Case"],
    ["docs", "Documents"],
    ["de111_url", "DE-111 URL"],
    ["de147_url", "DE-147 URL"],
    ["petitioner", "Petitioner"],
    ["petitioner_address", "Petitioner address"],
    ["decedent", "Decedent"],
    ["decedent_address", "Decedent address"],
    ["hearing", "Hearing"],
    ["estate_real", "estate_real"],
    ["gmv_real", "gmv_real"],
    ["estate_personal", "estate_personal"],
    ["petition_ocr", "petition_ocr"],
    ["petition_ocr_gmv", "petition_ocr_gmv"],
    ["ocr_engine", "ocr_engine"],
    ["newspaper", "Newspaper"],
    ["go_status", "GO/NO-GO"],
    ["nogo_reason", "Status"],
    ["fub_status_label", "Listings Status"],
    ["fub_person_id", "FUB person id"],
    ["fub_removed", "FUB removed"],
    ["notice_url", "Notice URL"],
    ["court_url", "Court URL"],
    ["status", "Status"],
    ["first_seen", "First seen"],
    ["last_seen", "Last seen"],
  ];
  const body = rows.map((row) => headers.map(([key]) => {
    if (key === "fub_status_label") return ppmListingFubLabel(row);
    if (key === "go_status") return ppmListingGoLabel(row);
    if (key === "nogo_reason") return ppmListingGoReasonLabel(row);
    if (key === "docs") return ppmListingDocsLabel(row);
    if (key === "fub_removed") return row.fub_removed ? "true" : "false";
    if (key === "petition_ocr" || key === "petition_ocr_gmv") return row[key] ? "true" : "";
    if (key === "gmv_real") {
      const gmv = row.estate_real;
      return gmv == null || gmv === "" ? "" : String(gmv);
    }
    const value = row[key];
    return value == null || value === "" ? "" : String(value);
  }));
  return { headers: headers.map((item) => item[1]), body };
}

function ppmListingsToCsv(rows) {
  const { headers, body } = ppmListingExportRows(rows);
  const lines = [headers.map(ppmCsvCell).join(",")].concat(
    body.map((vals) => vals.map(ppmCsvCell).join(","))
  );
  return `\ufeff${lines.join("\r\n")}`;
}

function ppmListingsToExcel(rows) {
  const { headers, body } = ppmListingExportRows(rows);
  const xmlRow = (vals) => `<Row>${vals.map((value) => `<Cell><Data ss:Type="String">${ppmXml(value)}</Data></Cell>`).join("")}</Row>`;
  return `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
<Worksheet ss:Name="Listings">
<Table>
${xmlRow(headers)}
${body.map(xmlRow).join("\n")}
</Table>
</Worksheet>
</Workbook>`;
}

function ppmFubFieldSelect(key, selected, fubFields, builtins) {
  const known = new Set([
    ...((builtins || []).map((item) => item.name)),
    ...((fubFields || []).map((item) => item.name)),
  ]);
  const extra = (selected && !known.has(selected))
    ? `<option value="${ppmEsc(selected)}" selected>${ppmEsc(selected)} (saved)</option>`
    : "";
  const builtinOpts = (builtins || []).map((item) => {
    const sel = item.name === selected ? "selected" : "";
    const disabled = item.disabled ? "disabled" : "";
    return `<option value="${ppmEsc(item.name)}" ${sel} ${disabled}>${ppmEsc(item.label)} — ${ppmEsc(item.name)}</option>`;
  }).join("");
  const customOpts = (fubFields || []).map((item) => {
    const sel = item.name === selected ? "selected" : "";
    const type = item.type ? ` · ${item.type}` : "";
    return `<option value="${ppmEsc(item.name)}" ${sel}>${ppmEsc(item.label)} — ${ppmEsc(item.name)}${ppmEsc(type)}</option>`;
  }).join("");
  return `<select data-custom="${ppmEsc(key)}">
    <option value="">Do not map</option>
    ${extra}
    <optgroup label="Built-in Follow Up Boss fields">${builtinOpts || "<option disabled>None</option>"}</optgroup>
    <optgroup label="Custom fields">${customOpts || "<option disabled>None loaded</option>"}</optgroup>
  </select>`;
}

function ppmSourceGoNoGo(data, mapData, sourceId) {
  return (data && data.source_go_no_go && data.source_go_no_go[sourceId])
    || (mapData && mapData.source_go_no_go && mapData.source_go_no_go[sourceId])
    || (mapData && mapData.catalog && mapData.catalog.source_go_no_go && mapData.catalog.source_go_no_go[sourceId])
    || {};
}

function ppmGoNoGoInner(spec, sourceName) {
  const data = spec || {};
  const always = data.always || [];
  const required = data.required || [];
  const optional = data.optional || [];
  const rules = data.rules || [];
  const alwaysRows = always.map((item) => `
    <tr>
      <td><span class="ppm-pill off">Always</span></td>
      <td><b>${ppmEsc(item.label)}</b><div class="ppm-note">${ppmEsc(item.key || "")}</div></td>
      <td>${ppmEsc(item.from || "")}${item.when ? `<div class="ppm-note">${ppmEsc(item.when)}</div>` : ""}</td>
    </tr>`).join("");
  const reqRows = required.map((item) => `
    <tr>
      <td><span class="ppm-pill off">Path A</span></td>
      <td><b>${ppmEsc(item.label)}</b><div class="ppm-note">${ppmEsc(item.key || "")}</div></td>
      <td>${ppmEsc(item.from || "")}</td>
    </tr>`).join("");
  const optRows = optional.map((item) => `
    <tr>
      <td><span class="ppm-pill wait">Optional</span></td>
      <td><b>${ppmEsc(item.label)}</b><div class="ppm-note">${ppmEsc(item.key || "")}</div></td>
      <td>${ppmEsc(item.from || "")}${item.when ? `<div class="ppm-note">${ppmEsc(item.when)}</div>` : ""}</td>
    </tr>`).join("");
  const rows = (alwaysRows + reqRows + optRows)
    || `<tr><td colspan="3">No field checklist yet for ${ppmEsc(sourceName || "this source")}.</td></tr>`;
  const ruleList = rules.length
    ? `<ul>${rules.map((line) => `<li>${ppmEsc(line)}</li>`).join("")}</ul>`
    : "";
  return `
    <p class="ppm-note">${ppmEsc(sourceName || "This source")} is NO-GO unless parsed DE-111 real-property GMV is present and at least $200,000, when the petitioner is a professional fiduciary, or when the Follow Up Boss person was deleted. Same Path A create fields for Placer and Sacramento: real petitioner first name, petitioner last name, petitioner mailing street, and estate_real GMV ≥ $200,000. Decedent residence is collected but not required for GO unless you check it below. Path B is an alternate: petitioner, decedent, decedent address, and petitioner phone — no mailing required. Case number is never required. Form captions are not person names. Missing or blank GMV (including tiny OCR $1–$9) is NO-GO. Missing Path A and Path B data is skipped, not sent as a partial Follow Up Boss person.</p>
    <table>
      <thead><tr><th></th><th>Field</th><th>From</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    ${ruleList}`;
}

function ppmGoNoGoCard(spec, sourceName) {
  return `
    <section class="ppm-card">
      <h2>Go / no-go data requirements</h2>
      ${ppmGoNoGoInner(spec, sourceName)}
    </section>`;
}

function ppmMappingRows(fields, custom, fubFields, person, builtins, defaults) {
  const titles = { petitioner: "Petitioner", decedent: "Decedent", other: "Case and other fields" };
  let lastGroup = "";
  return (fields || []).map((field) => {
    let header = "";
    const group = field.group || "";
    if (group && group !== lastGroup) {
      lastGroup = group;
      header = `<tr><td colspan="4"><b>${ppmEsc(titles[group] || group)}</b></td></tr>`;
    }
    if (!field.custom && field.unavailable) {
      return `${header}<tr><td><b>${ppmEsc(field.label)}</b></td><td>${ppmEsc(field.source)}</td><td colspan="2"><span class="ppm-pill off">Not extracted</span></td></tr>`;
    }
    if (!field.custom) return header;
    const value = (custom && custom[field.key]) || (defaults && defaults[field.key]) || "";
    const status = field.unavailable
      ? '<span class="ppm-pill wait">Extract later</span>'
      : '<span class="ppm-pill live">Available</span>';
    return `${header}<tr>
      <td><b>${ppmEsc(field.label)}</b><div class="ppm-note">${ppmEsc(field.key)}</div></td>
      <td>${ppmEsc(field.source)} ${status}</td>
      <td>${ppmFubFieldSelect(field.key, value, fubFields, builtins)}</td>
      <td data-fub-example>${ppmFubExampleCell(person, value)}</td>
    </tr>`;
  }).join("");
}

function ppmFubPersonLookup(person, name) {
  if (!person || !name) return "";
  const custom = (person.custom_fields || []).find((item) => item.name === name);
  if (custom && custom.value) return custom.value;
  const core = (person.core || []).find((item) => item.name === name);
  return (core && core.value) || "";
}

function ppmFubExampleCell(person, apiName) {
  if (!person) return '<span class="ppm-note">Pull an example person</span>';
  if (!apiName) return '<span class="ppm-note">Pick a FUB field</span>';
  const value = ppmFubPersonLookup(person, apiName);
  return value
    ? ppmCell(value)
    : '<span class="ppm-pill wait">Empty on this person</span>';
}

function ppmBindMappingExamples(root, person) {
  if (!root) return;
  root.querySelectorAll("select[data-custom]").forEach((el) => {
    el.addEventListener("change", () => {
      const cell = el.closest("tr") && el.closest("tr").querySelector("[data-fub-example]");
      if (cell) cell.innerHTML = ppmFubExampleCell(person, el.value.trim());
    });
  });
}

function ppmFieldAssociations(mapping, sourceId, catalogFields) {
  const source = sourceId || "placer";
  const custom = ((mapping && mapping.source_mappings && mapping.source_mappings[source]
    && mapping.source_mappings[source].custom_fields)
    || (source === "placer" && mapping && mapping.custom_fields)
    || {});
  const labels = {};
  (catalogFields || []).forEach((field) => {
    labels[field.key] = field.label || field.key;
  });
  const byFub = {};
  const add = (fubName, key) => {
    if (!fubName) return;
    byFub[fubName] = byFub[fubName] || [];
    if (!byFub[fubName].some((item) => item.key === key)) {
      byFub[fubName].push({ key, label: labels[key] || key });
    }
  };
  Object.keys(custom || {}).forEach((key) => add(custom[key], key));
  add("firstName", "petitioner_first");
  add("lastName", "petitioner_last");
  add("emails", "petitioner_email");
  add("phones", "petitioner_phone");
  add("assignedTo", "assignedTo");
  add("source", "lead_source");
  return byFub;
}

function ppmLiveClientHtml(person, associations) {
  if (!person || !person.person_id) {
    return `<p class="ppm-note">Pull a live Follow Up Boss contact to see its data and which probate fields map to it. This does not change FUB.</p>`;
  }
  const name = ppmFubPersonLookup(person, "name")
    || [ppmFubPersonLookup(person, "firstName"), ppmFubPersonLookup(person, "lastName")].filter(Boolean).join(" ");
  const assocOf = (fubName) => {
    const items = (associations && associations[fubName]) || [];
    if (!items.length) return '<div class="ppm-assoc">Not mapped from probate</div>';
    return `<div class="ppm-assoc">Mapped from ${items.map((item) => ppmEsc(item.label)).join(", ")}</div>`;
  };
  const core = (person.core || []).map((item) =>
    `<tr>
      <td><b>${ppmEsc(item.name)}</b>${assocOf(item.name)}</td>
      <td>${item.populated ? ppmCell(item.value) : "—"}</td>
      <td>${item.populated ? '<span class="ppm-pill live">Set</span>' : '<span class="ppm-pill wait">Empty</span>'}</td>
    </tr>`
  ).join("");
  const custom = (person.custom_fields || []).map((item) =>
    `<tr>
      <td><b>${ppmEsc(item.label)}</b><div class="ppm-note">${ppmEsc(item.name)}</div>${assocOf(item.name)}</td>
      <td>${item.populated ? ppmCell(item.value) : "—"}</td>
      <td>${item.populated ? '<span class="ppm-pill live">Set</span>' : '<span class="ppm-pill wait">Empty</span>'}</td>
    </tr>`
  ).join("");
  return `
    <p class="ppm-note"><b>${ppmEsc(name || person.person_id)}</b> · id ${ppmEsc(person.person_id)} · ${ppmEsc(person.custom_populated)}/${ppmEsc(person.custom_total)} custom fields set</p>
    <h2>Built-in fields</h2>
    <table><thead><tr><th>FUB field</th><th>Value</th><th></th></tr></thead><tbody>${core}</tbody></table>
    <h2 style="margin-top:16px;">Custom fields</h2>
    <table><thead><tr><th>FUB field</th><th>Value</th><th></th></tr></thead><tbody>${custom || "<tr><td colspan='3'>None</td></tr>"}</tbody></table>
  `;
}

function ppmPersonSnapshot(person) {
  if (!person || !person.person_id) {
    return `<p class="ppm-note">No Follow Up Boss person loaded yet.</p>`;
  }
  const name = ppmFubPersonLookup(person, "name")
    || [ppmFubPersonLookup(person, "firstName"), ppmFubPersonLookup(person, "lastName")].filter(Boolean).join(" ");
  const core = (person.core || []).filter((item) => item.populated).map((item) =>
    `<tr><th>${ppmEsc(item.name)}</th><td>${ppmCell(item.value)}</td></tr>`
  ).join("");
  const custom = (person.custom_fields || []).filter((item) => item.populated).map((item) =>
    `<tr><td><b>${ppmEsc(item.label)}</b><div class="ppm-note">${ppmEsc(item.name)}</div></td><td>${ppmCell(item.value)}</td></tr>`
  ).join("");
  return `
    <p class="ppm-note">Example person <b>${ppmEsc(name || person.person_id)}</b> · id ${ppmEsc(person.person_id)} · ${ppmEsc(person.custom_populated)} of ${ppmEsc(person.custom_total)} custom fields have values. This is a read-only FUB contact.</p>
    <table><thead><tr><th>Built-in field</th><th>Value</th></tr></thead><tbody>${core || "<tr><td colspan='2'>—</td></tr>"}</tbody></table>
    ${custom ? `<h2 style="margin-top:16px;">Populated custom fields</h2><table><thead><tr><th>FUB field</th><th>Value</th></tr></thead><tbody>${custom}</tbody></table>` : "<p class='ppm-note'>No custom fields are populated on this person.</p>"}
  `;
}

function ppmCompareExtractToFub(rec, person) {
  if (!rec || !person) return "";
  const rows = [
    ["firstName", rec.firstName, ppmFubPersonLookup(person, "firstName")],
    ["lastName", rec.lastName, ppmFubPersonLookup(person, "lastName")],
    ["assignedTo", rec.assignedTo, ppmFubPersonLookup(person, "assignedTo")],
    ["source", rec.lead_source, ppmFubPersonLookup(person, "source")],
  ];
  (rec.custom_fields || []).forEach((item) => {
    rows.push([item.fub_field, item.value, ppmFubPersonLookup(person, item.fub_field)]);
  });
  return `<h2 style="margin-top:16px;">Probate mapped value vs this FUB person</h2>
    <table><thead><tr><th>FUB field</th><th>This probate record</th><th>Example person</th></tr></thead>
    <tbody>${rows.map((item) => `<tr><th>${ppmEsc(item[0])}</th><td>${ppmCell(item[1])}</td><td>${item[2] ? ppmCell(item[2]) : "—"}</td></tr>`).join("")}</tbody></table>`;
}

async function ppmFetchFubPerson(hass, query) {
  return hass.callApi(
    "GET",
    "placer_probate_monitor/fub_person?q=" + encodeURIComponent(query),
  );
}

function ppmExamplePersonBar(query) {
  return `
    <div class="ppm-row">
      <div>
        <label>Example FUB person (id or name)</label>
        <input class="fub-person-q" placeholder="e.g. 12345 or Jane Doe" value="${ppmEsc(query || "")}" />
      </div>
    </div>
    <div class="ppm-actions" style="margin-top:8px;">
      <button class="secondary fub-person-load" type="button">Pull example person</button>
    </div>
    <div class="fub-person-shot"></div>
  `;
}

function ppmCell(value) {
  const text = String(value ?? "").trim();
  if (!text) return "—";
  if (/^https?:\/\//i.test(text)) {
    return `<a href="${ppmEsc(text)}" target="_blank" rel="noopener">${ppmEsc(text)}</a>`;
  }
  return ppmEsc(text);
}

function ppmSkipTable(skips) {
  if (!skips || !skips.length) return "";
  const rows = skips.slice(0, 12).map((item) =>
    `<tr><td>${ppmEsc(item.case || "?")}</td><td>${ppmEsc(item.reason || "")}</td></tr>`
  ).join("");
  return `<h2 style="margin-top:16px;">Other cases in this window</h2>
    <p class="ppm-note">Quality gates still apply. Local seen/FUB status is ignored on preview.</p>
    <table><thead><tr><th>Case</th><th>Why not shown</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function ppmPreviewRecord(st) {
  const rec = st && st.fub_verify;
  if (!rec || (rec.note && !rec.case_number)) return null;
  return rec;
}

function ppmRenderPreview(el, st) {
  if (!el) return;
  const rec = ppmPreviewRecord(st);
  const note = (st && (st.fub_verify_note || (st.fub_verify && st.fub_verify.note))) || "";
  const skips = (st && st.fub_skips) || (rec && rec.skips) || [];
  if (!rec) {
    el.innerHTML = `<h2>Last stored extract</h2>
      <p class="ppm-note">${ppmEsc(note || "Run Preview one extract or Verify one FUB import to show a go-case here.")}</p>
      ${ppmSkipTable(skips)}`;
    return;
  }
  const viewOnly = !!rec.view_only;
  const posted = !!rec.posted && !viewOnly;
  const updated = !!rec.updated && posted;
  const fubError = rec.fub_error || (st && st.fub_error) || "";
  const county = ppmPreviewCounty(rec, st);
  const sac = county === "sacramento";
  const countyName = sac ? "Sacramento" : "Placer";
  const courtSource = sac
    ? "Journal Technologies public portal node/397"
    : "eCourt Public node/45";
  const courtLabel = sac ? "Journal Technologies portal" : "eCourt Public";
  let extract = rec.source_extract || [];
  if (!extract.length) {
    extract = [
      { label: "Case number", source: sac ? "CNPA / Sacramento portal" : "CNPA / eCourt", value: rec.case_number, empty: !rec.case_number },
      { label: "Petitioner first name", source: "Split from petitioner", value: rec.firstName || rec.petitioner_first, empty: !(rec.firstName || rec.petitioner_first) },
      { label: "Petitioner last name", source: "Split from petitioner", value: rec.lastName || rec.petitioner_last, empty: !(rec.lastName || rec.petitioner_last) },
      { label: "Petitioner full name", source: sac ? "Sacramento portal parties" : "eCourt parties", value: rec.petitioner, empty: !rec.petitioner },
      { label: "Decedent", source: sac ? "CNPA / Sacramento portal" : "CNPA / eCourt", value: rec.decedent, empty: !rec.decedent },
      { label: "Estate location", source: "DE-111 item 3.a.(2)", value: rec.decedent_residence, empty: !rec.decedent_residence },
      { label: "Petitioner address", source: "DE-111 item 8 / 3h + DE-147", value: rec.mailing_address, empty: !rec.mailing_address },
      { label: "Petitioner email", source: "DE-111 + DE-147", value: rec.petitioner_email, empty: !rec.petitioner_email },
      { label: "Petitioner phone", source: "DE-111 + DE-147", value: rec.petitioner_phone, empty: !rec.petitioner_phone },
      { label: "Hearing", source: sac ? "Sacramento portal" : "eCourt", value: rec.hearing, empty: !rec.hearing },
      { label: "Notice URL", source: "CNPA", value: rec.notice_url, empty: !rec.notice_url },
      { label: "Court case URL", source: courtSource, value: rec.court_url || rec.court_search, empty: !(rec.court_url || rec.court_search) },
    ];
  }
  const mapped = rec.mapped || {};
  const pulledRows = extract.map((item) => {
    const status = item.unavailable
      ? '<span class="ppm-pill off">Not extracted</span>'
      : (item.empty ? '<span class="ppm-pill wait">Empty</span>' : '<span class="ppm-pill live">Pulled</span>');
    return `<tr>
      <td><b>${ppmEsc(item.label)}</b><div class="ppm-note">${ppmEsc(item.source || item.key || "")}</div></td>
      <td>${item.unavailable ? "—" : ppmCell(item.value)}</td>
      <td>${status}</td>
    </tr>`;
  }).join("");
  const personRows = (mapped.person || []).map((item) =>
    `<tr><th>${ppmEsc(item.label)}</th><td>${ppmCell(item.value)}</td></tr>`
  ).join("");
  const custom = (rec.custom_fields || []).map((item) =>
    `<tr><td>${ppmEsc(item.probate_field)}</td><td>${ppmEsc(item.fub_field)}</td><td>${ppmCell(item.value)}</td></tr>`
  ).join("");
  const addr = rec.address || {};
  const addrLine = [addr.street, addr.city, addr.state, addr.code].filter(Boolean).join(", ");
  const mappedFallback = personRows || `
    <tr><th>firstName</th><td>${ppmCell(rec.firstName)}</td></tr>
    <tr><th>lastName</th><td>${ppmCell(rec.lastName)}</td></tr>
    <tr><th>assignedTo</th><td>${ppmCell(rec.assignedTo)}</td></tr>
    <tr><th>addresses</th><td>${ppmCell(addrLine)}</td></tr>
  `;
  const attach = rec.de111_attach || {};
  const attachLine = attach.ok
    ? (attach.reason === "notes_link"
      ? `${attach.file || "DE-111"} (Notes link${attach.uri ? `: ${attach.uri}` : ""})`
      : (attach.file ? `${attach.file} (${attach.reason || "attached"})` : (attach.reason || "attached")))
    : (attach.reason || (posted ? "not attached" : ""));
  const noGo = rec.gate === "no-go";
  const heading = noGo
    ? "Last stored extract (no-go)"
    : (viewOnly
    ? "Last stored extract (view only)"
    : (posted ? (updated ? "Last verify record (updated)" : "Last verify record (posted)") : "Last verify record"));
  const blurb = noGo
    ? `This case was skipped (${ppmEsc(rec.gate_reason || "no-go")}). Follow Up Boss was not updated.`
    : (viewOnly
    ? `This is one stored go-case from ${countyName}. Follow Up Boss was not updated.`
    : (posted
      ? (updated
        ? "This existing Follow Up Boss person was updated with the current mapping, including the DE-111 on Files. Confirm Address 1/2, notes, name, and Files in FUB."
        : "This go-case was posted to Follow Up Boss, including the DE-111 on Files. Confirm it in FUB, then turn off Verify only.")
      : "This is the go-case Verify tried to upload. Follow Up Boss did not accept it."));
  const pill = noGo
    ? '<span class="ppm-pill off">NO-GO</span>'
    : (viewOnly
    ? '<span class="ppm-pill wait">VIEW ONLY</span>'
    : (posted
      ? (updated ? '<span class="ppm-pill live">GO · UPDATED</span>' : '<span class="ppm-pill live">GO · POSTED</span>')
      : '<span class="ppm-pill off">GO · NOT POSTED</span>'));
  el.innerHTML = `
    <h2>${heading}</h2>
    <p class="ppm-note">${blurb}</p>
    ${fubError ? `<div class="ppm-banner show err">${ppmEsc(fubError)}</div>` : ""}
    ${pill}
    <span class="ppm-pill">${ppmEsc(rec.case_number || "")}</span>
    ${posted && rec.fub_person_id ? `<span class="ppm-pill live">FUB person ${ppmEsc(rec.fub_person_id)}</span>` : ""}
    <div class="ppm-compare">
      <div>
        <h2>1. Pulled from ${countyName}</h2>
        <p class="ppm-note">${sac
          ? "Check these against the notice, Journal Technologies public portal, and petition PDF."
          : "Check these against the notice, eCourt, and petition PDF."}</p>
        <table>
          <thead><tr><th>Field</th><th>Value</th><th></th></tr></thead>
          <tbody>${pulledRows}</tbody>
        </table>
      </div>
      <div>
        <h2>2. How it looks for Follow Up Boss</h2>
        <p class="ppm-note">Person name is the petitioner. Decedent and counsel stay on custom fields.</p>
        <table>
          <tbody>
            ${mappedFallback}
            <tr><th>event type</th><td>${ppmCell(mapped.event_type || rec.event_type)}</td></tr>
            <tr><th>lead source</th><td>${ppmCell(mapped.lead_source || rec.lead_source)}</td></tr>
            <tr><th>system</th><td>${ppmCell(mapped.system)}</td></tr>
            ${attachLine && !viewOnly ? `<tr><th>Files</th><td>${ppmCell(attachLine)}</td></tr>` : ""}
            ${(rec.court_url || rec.court_search) ? `<tr><th>${courtLabel}</th><td>${ppmCell((rec.court_url_note && rec.court_url_note.uri) || rec.court_url || rec.court_search)}</td></tr>` : ""}
          </tbody>
        </table>
        ${mapped.message ? `<label>Event message</label><p class="ppm-pre">${ppmCell(mapped.message)}</p>` : ""}
        ${mapped.description ? `<label>Event description</label><p class="ppm-pre">${ppmCell(mapped.description)}</p>` : ""}
        ${custom ? `<h2 style="margin-top:16px;">Custom fields</h2><table><thead><tr><th>Probate</th><th>FUB</th><th>Value</th></tr></thead><tbody>${custom}</tbody></table>` : ""}
      </div>
    </div>
    ${note && !posted ? `<p class="ppm-note">${ppmEsc(note)}</p>` : ""}
    ${ppmSkipTable(skips)}
  `;
}

class PlacerProbateSourcesPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._ready = false;
    this._source = "placer";
    this._data = { sources: [], placer: {}, fields: [], source_fields: {} };
    this._jobSt = {};
    this._storedDocs = { counties: [] };
    this._mapData = { fub_custom_fields: [], mapping: {}, source_fields: {} };
    this._fubPerson = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._ready) {
      this._ready = true;
      this._renderShell();
      this._load();
    }
  }

  get hass() {
    return this._hass;
  }

  _qs(sel) {
    return this.querySelector(sel);
  }

  _flash(msg, ok) {
    const el = this._qs("#flash");
    if (!el) return;
    el.textContent = msg;
    el.className = "ppm-banner show " + ppmBannerKind(ok);
  }

  _renderShell() {
    this.innerHTML = `
      <div class="ppm-page-intro">
        <h2 class="ppm-page-title">Probate sources</h2>
        <p>County import settings and extracted-field catalogs. Follow Up Boss mapping is on the home page.</p>
      </div>
      <main>
        <div id="flash" class="ppm-banner"></div>
        <div class="ppm-layout">
          <aside class="ppm-card">
            <h2>Counties</h2>
            <div class="ppm-sourcelist" id="source-list"></div>
          </aside>
          <div id="source-body"></div>
        </div>
      </main>
    `;
  }

  _renderList() {
    this._qs("#source-list").innerHTML = (this._data.sources || []).map((src) => {
      let pill = "wait";
      let label = "Coming next";
      if (src.status === "live" && src.enabled) {
        pill = "live";
        label = "On";
      } else if (src.status === "live") {
        pill = "off";
        label = "Off";
      }
      const active = src.id === this._source ? "active" : "";
      return `<button type="button" data-source="${ppmEsc(src.id)}" class="${active}">${ppmEsc(src.name)} <span class="ppm-pill ${pill}">${label}</span></button>`;
    }).join("");
    this.querySelectorAll("[data-source]").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._source = btn.dataset.source;
        this._renderList();
        this._renderBody();
      });
    });
  }

  _renderBody() {
    const src = (this._data.sources || []).find((item) => item.id === this._source)
      || { id: this._source, name: this._source, status: "coming_soon", description: "", extracts: "" };
    const body = this._qs("#source-body");
    if (src.status === "live") {
      const on = !!src.enabled;
      const label = src.id === "sacramento" ? "Sacramento" : "Placer";
      const p = src.id === "sacramento" ? (this._data.sacramento || {}) : (this._data.placer || {});
      const keywords = src.id === "sacramento"
        ? '"NOTICE OF PETITION"'
        : (p.keywords || '"NOTICE OF PETITION TO ADMINISTER ESTATE"');
      const county = src.id === "sacramento" ? "Sacramento" : "Placer";
      const skipLabel = src.id === "sacramento" ? "Skip court-portal lookups" : "Skip eCourt lookups";
      const pauseLabel = src.id === "sacramento" ? "Portal pause (seconds)" : "eCourt pause (seconds)";
      const fields = (this._mapData.source_fields && this._mapData.source_fields[src.id])
        || this._data.fields || [];
      const custom = ((this._mapData.mapping && this._mapData.mapping.source_mappings
        && this._mapData.mapping.source_mappings[src.id]
        && this._mapData.mapping.source_mappings[src.id].custom_fields)
        || (src.id === "placer" && this._mapData.mapping && this._mapData.mapping.custom_fields)
        || {});
      body.innerHTML = `
        <section class="ppm-card">
          <h2>${ppmEsc(src.name)} import</h2>
          <p class="ppm-note">${ppmEsc(src.description)}</p>
          <div class="ppm-toggle">
            <input id="source_enabled" type="checkbox" ${on ? "checked" : ""} />
            <div>
              <label style="margin:0;">Use this county in the daily job</label>
              <p class="ppm-note" style="margin:4px 0 0;">Off keeps ${ppmEsc(label)} out of the scheduled run and Follow Up Boss import. The other county is unchanged.</p>
            </div>
          </div>
          <div class="ppm-row">
            <div><label>${src.id === "sacramento" ? "CNPA lookback days" : "Lookback days"}</label><input id="lookback_days" type="number" min="1" max="365" value="${ppmEsc(p.lookback_days ?? (src.id === "sacramento" ? 60 : 21))}" /></div>
            <div><label>${src.id === "sacramento" ? "CNPA lookahead days" : "Lookahead days"}</label><input id="lookahead_days" type="number" min="0" max="120" value="${ppmEsc(p.lookahead_days ?? (src.id === "sacramento" ? 0 : 21))}" /></div>
          </div>
          ${src.id === "sacramento" ? `
          <div class="ppm-row">
            <div>
              <label>Public Reports 415 lookback days</label>
              <input id="public_reports_lookback_days" type="number" min="1" max="365" value="${ppmEsc(p.public_reports_lookback_days ?? 2)}" />
            </div>
            <div>
              <p class="ppm-note" style="margin:22px 0 0;">Today + yesterday by default (2 one-day queries). Lookahead is always 0. Raise only for catch-up. Does not use the CNPA window.</p>
            </div>
          </div>
          ` : ""}
          <div class="ppm-row">
            <div><label>County</label><input id="county" value="${ppmEsc(county)}" disabled /></div>
            <div>
              <label>${ppmEsc(skipLabel)}</label>
              <select id="skip_portal" ${src.id === "sacramento" ? "disabled" : ""}><option value="false">No</option><option value="true">Yes</option></select>
            </div>
          </div>
          <div class="ppm-row">
            <div><label>Lead source name</label><input id="lead_source" value="${ppmEsc(src.lead_source || "")}" disabled /></div>
          </div>
          <label>CNPA keywords</label>
          <input id="keywords" value="${ppmEsc(keywords)}" ${src.id === "sacramento" ? "disabled" : ""} />
          <div class="ppm-row">
            <div>
              <label>Generate PDF</label>
              <select id="generate_pdf" ${src.id === "sacramento" ? "disabled" : ""}><option value="true">Yes</option><option value="false">No</option></select>
            </div>
            <div><label>${ppmEsc(pauseLabel)}</label><input id="ecourt_pause_seconds" type="number" step="0.1" min="0.5" max="10" value="${ppmEsc(p.ecourt_pause_seconds ?? 1.2)}" /></div>
          </div>
          <label>Max CNPA pages</label>
          <input id="max_search_pages" type="number" min="1" max="20" value="${ppmEsc(p.max_search_pages ?? 10)}" ${src.id === "sacramento" ? "disabled" : ""} />
          ${src.id === "sacramento" ? `
          <h2 style="margin-top:16px;">Court portal login</h2>
          <p class="ppm-note">Email and password for the Sacramento Journal Technologies public portal. Jobs scrape the math CAPTCHA from the login HTML. Confidential and Not Viewable filings are never downloaded. Leave the password blank to keep the saved password.</p>
          <label>Portal email</label>
          <input id="sacramento_portal_user" type="email" autocomplete="username" value="${ppmEsc(p.sacramento_portal_user || "")}" />
          <label>Portal password</label>
          <input id="sacramento_portal_password" type="password" autocomplete="new-password" placeholder="${p.sacramento_portal_password_set ? "unchanged if blank" : ""}" />
          <p class="ppm-note">${p.sacramento_portal_password_set ? "A portal password is already saved." : "No portal password saved yet. Public PDFs will not download until this is set."}</p>
          ` : ""}
          <div class="ppm-actions">
            ${src.id === "placer" ? '<button id="save-source" type="button">Save Placer import</button>' : '<button id="save-source" type="button">Save Sacramento import</button>'}
            <button class="secondary" id="preview-source" type="button">Preview one extract</button>
            <button class="secondary" id="test-stored" type="button">Test stored data</button>
            <button class="secondary" id="rescan-source" type="button">Rescan local files</button>
            <button class="secondary" id="fub-review-export" type="button">Export FUB review (CSV/Excel)</button>
            <button class="secondary" id="push-stored-fub" type="button">Push stored GOs to Follow Up Boss</button>
            <button class="secondary" id="audit-source" type="button">Audit stored cases</button>
            <button class="secondary" id="run-source" type="button">Run ${ppmEsc(label)} job</button>
          </div>
          ${ppmOcrNote(this._jobSt)}
          <p class="ppm-note">${src.id === "sacramento"
            ? "After a parser change: Rescan local files (saves listings, no court), then Export FUB review to confirm names/GMV/addresses. When that looks right, Push stored GOs to Follow Up Boss. That run does not scrape CNPA. It POSTs GOs with no person id and PUTs existing people when fields changed. Check Force PUT to rewrite unchanged people too. Test stored data only scores GO vs no-go and does not post. Audit stored cases flags extract gaps; it does not scrape or post. Run Sacramento job is the live CNPA harvest."
            : "After a parser change: Rescan local files (saves listings, no court), then Export FUB review to confirm names/GMV/addresses. When that looks right, Push stored GOs to Follow Up Boss. That run does not scrape CNPA. It POSTs GOs with no person id and PUTs existing people when fields changed. Check Force PUT to rewrite unchanged people too. Test stored data only scores GO vs no-go and does not post. Audit stored cases flags extract gaps; it does not scrape or post. Run Placer job is the live CNPA harvest."}</p>
        </section>
        ${ppmStoredDocsCard(this._storedDocs, src.id)}
        ${ppmAuditIssuesCard(this._jobSt)}
        ${ppmStoredTestCard(this._jobSt)}
        <section class="ppm-card" id="source-preview">
          <h2>Last stored extract</h2>
          <p class="ppm-note">Run Preview one extract to see pulled values and the Follow Up Boss mapping for one case. That path still contacts court/CNPA.</p>
        </section>
        ${ppmGoNoGoCard(ppmSourceGoNoGo(this._data, this._mapData, src.id), src.name)}
        <section class="ppm-card">
          <h2>Follow Up Boss mapping</h2>
          <p class="ppm-note">${(this._mapData.fub_custom_fields || []).length
            ? `Each ${ppmEsc(src.name)} field can map to a custom field that already exists in Follow Up Boss.`
            : (this._mapData.fub_custom_error || "Save a Follow Up Boss API key, then reload to load custom fields.")}</p>
          ${ppmExamplePersonBar(this._fubPerson && this._fubPerson.query)}
          <table>
            <thead><tr><th>Source field</th><th>From</th><th>FUB custom field</th><th>Example person</th></tr></thead>
            <tbody>
              ${ppmMappingRows(
                fields,
                custom,
                this._mapData.fub_custom_fields || [],
                this._fubPerson,
                this._mapData.fub_builtin_fields || [],
                (this._mapData.catalog && this._mapData.catalog.default_custom_fields) || {},
              )}
            </tbody>
          </table>
          <div class="ppm-actions"><button id="save-source-map" type="button">Save ${ppmEsc(src.name)} mapping</button></div>
        </section>
      `;
      const skip = this._qs("#skip_portal");
      if (skip) skip.value = String(!!p.skip_portal);
      const pdf = this._qs("#generate_pdf");
      if (pdf) pdf.value = String(p.generate_pdf !== false);
      const saveBtn = this._qs("#save-source");
      if (saveBtn) saveBtn.addEventListener("click", () => this._save());
      this._qs("#source_enabled").addEventListener("change", (ev) => this._toggleEnabled(src.id, ev.target.checked));
      this._qs("#preview-source").addEventListener("click", () => this._preview(src.id));
      this._qs("#test-stored").addEventListener("click", () => this._testStored(src.id));
      this._qs("#rescan-source").addEventListener("click", () => this._rescan(src.id));
      this._qs("#fub-review-export").addEventListener("click", () => this._exportFubReview(src.id));
      this._qs("#push-stored-fub").addEventListener("click", () => this._pushStoredFub(src.id));
      this._qs("#audit-source").addEventListener("click", () => this._auditStored(src.id));
      this._qs("#run-source").addEventListener("click", () => this._run(src.id));
      this.querySelectorAll("[data-stored-zip]").forEach((btn) => {
        btn.addEventListener("click", () => this._downloadStoredZip(btn.dataset.storedZip));
      });
      const saveMap = this._qs("#save-source-map");
      if (saveMap) saveMap.addEventListener("click", () => this._saveSourceMap(src.id));
      this._bindExamplePerson();
      ppmBindMappingExamples(body, this._fubPerson);
      ppmRenderPreview(this._qs("#source-preview"), this._jobSt);
      const shot = this._qs(".fub-person-shot");
      if (shot && this._fubPerson) shot.innerHTML = ppmPersonSnapshot(this._fubPerson)
        + ppmCompareExtractToFub(ppmPreviewRecord(this._jobSt), this._fubPerson);
      return;
    }
    if (src.status !== "live") {
      const fields = (this._mapData.source_fields && this._mapData.source_fields[src.id])
        || [];
      const custom = ((this._mapData.mapping && this._mapData.mapping.source_mappings
        && this._mapData.mapping.source_mappings[src.id]
        && this._mapData.mapping.source_mappings[src.id].custom_fields) || {});
      const fubFields = this._mapData.fub_custom_fields || [];
      body.innerHTML = `
        <section class="ppm-card">
          <h2>${ppmEsc(src.name)}</h2>
          <p>${ppmEsc(src.description)}</p>
          ${src.lead_source ? `<div><label>Lead source name</label><input value="${ppmEsc(src.lead_source)}" disabled /></div>` : ""}
          <p class="ppm-note">Import is not live yet. You can still map this source’s future fields to Follow Up Boss custom fields.</p>
        </section>
        ${ppmGoNoGoCard(ppmSourceGoNoGo(this._data, this._mapData, src.id), src.name)}
        <section class="ppm-card">
          <h2>Follow Up Boss mapping</h2>
          <p class="ppm-note">${fubFields.length
            ? `Choose a FUB custom field for each ${ppmEsc(src.name)} column. Pull an example person to see real values.`
            : (this._mapData.fub_custom_error || "Save a Follow Up Boss API key, then reload to load custom fields.")}</p>
          ${ppmExamplePersonBar(this._fubPerson && this._fubPerson.query)}
          <table><thead><tr><th>Source field</th><th>From</th><th>FUB custom field</th><th>Example person</th></tr></thead>
          <tbody>${ppmMappingRows(fields, custom, fubFields, this._fubPerson, this._mapData.fub_builtin_fields || [], (this._catalog && this._catalog.default_custom_fields) || (this._mapData.catalog && this._mapData.catalog.default_custom_fields) || {})}</tbody></table>
          <div class="ppm-actions"><button id="save-source-map" type="button">Save ${ppmEsc(src.name)} mapping</button></div>
        </section>`;
      const saveBtn = this._qs("#save-source-map");
      if (saveBtn) saveBtn.addEventListener("click", () => this._saveSourceMap(src.id));
      const savePortal = this._qs("#save-source");
      if (savePortal) savePortal.addEventListener("click", () => this._save());
      this._bindExamplePerson();
      const shot = this._qs(".fub-person-shot");
      if (shot && this._fubPerson) shot.innerHTML = ppmPersonSnapshot(this._fubPerson);
      ppmBindMappingExamples(body, this._fubPerson);
      return;
    }
  }

  async _load() {
    try {
      const [data, job, mapping, stored] = await Promise.all([
        this._hass.callApi("GET", "placer_probate_monitor/sources"),
        this._hass.callApi("GET", "placer_probate_monitor/job").catch(() => ({})),
        this._hass.callApi("GET", "placer_probate_monitor/fub_mapping").catch(() => ({})),
        this._hass.callApi("GET", "placer_probate_monitor/stored_docs").catch(() => ({ counties: [] })),
      ]);
      this._data = data;
      this._jobSt = job || {};
      this._mapData = mapping || {};
      this._storedDocs = stored || { counties: [] };
      this._renderList();
      this._renderBody();
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _save() {
    const src = this._source || "placer";
    const body = src === "sacramento"
      ? {
        source_id: "sacramento",
        lookback_days: Number(this._qs("#lookback_days").value),
        lookahead_days: Number(this._qs("#lookahead_days").value),
        public_reports_lookback_days: Number(this._qs("#public_reports_lookback_days").value),
        ecourt_pause_seconds: Number(this._qs("#ecourt_pause_seconds").value),
        sacramento_portal_user: (this._qs("#sacramento_portal_user") || {}).value || "",
        sacramento_portal_password: (this._qs("#sacramento_portal_password") || {}).value || "",
      }
      : {
        source_id: "placer",
        lookback_days: Number(this._qs("#lookback_days").value),
        lookahead_days: Number(this._qs("#lookahead_days").value),
        keywords: this._qs("#keywords").value,
        skip_portal: this._qs("#skip_portal").value === "true",
        generate_pdf: this._qs("#generate_pdf").value === "true",
        ecourt_pause_seconds: Number(this._qs("#ecourt_pause_seconds").value),
        max_search_pages: Number(this._qs("#max_search_pages").value),
      };
    try {
      this._data = await this._hass.callApi("POST", "placer_probate_monitor/sources", body);
      this._renderList();
      this._renderBody();
      this._flash(
        src === "sacramento"
          ? "Sacramento import settings saved."
          : "Placer import settings saved.",
        true,
      );
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _toggleEnabled(sourceId, enabled) {
    try {
      this._data = await this._hass.callApi("POST", "placer_probate_monitor/sources", {
        source_id: sourceId,
        enabled,
      });
      this._renderList();
      this._renderBody();
      const name = sourceId === "sacramento" ? "Sacramento County" : "Placer County";
      this._flash(
        enabled
          ? `${name} is on. Scheduled jobs and Follow Up Boss import include this county.`
          : `${name} is off. The other county and Follow Up Boss settings are unchanged.`,
        true,
      );
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _run(sourceId) {
    const id = sourceId || "placer";
    const label = id === "sacramento" ? "Sacramento" : "Placer";
    this._flash(`Starting ${label} job…`, "wait");
    try {
      const st = await ppmRunJob(this._hass, "run", { source_id: id }, (live) => {
        this._flash(ppmJobLiveMessage(live) || `${label} job is running…`, "wait");
      });
      const ok = st.last_result !== "failed" && st.last_result !== "running";
      this._flash(
        ok
          ? ppmJobDoneMessage(ppmStampJobCounty(st, { source_id: id }))
          : (ppmWithCountyPrefix(ppmText(st.last_error) || "Job failed. Check last_run.log.", { source_id: id })),
        ok,
      );
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _downloadStoredZip(sourceId) {
    const id = sourceId || "placer";
    const label = id === "sacramento" ? "Sacramento" : "Placer";
    this._flash(`Downloading stored ${label} PDFs…`, "wait");
    try {
      await ppmDownloadStoredZip(this._hass, id);
      this._flash(`Saved ${label} stored PDFs zip.`, true);
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _exportFubReview(sourceId) {
    const id = sourceId || "placer";
    const label = id === "sacramento" ? "Sacramento" : "Placer";
    this._flash(`Exporting ${label} Follow Up Boss review from stored listings. This does not create FUB people.`, "wait");
    try {
      await ppmExportFubReview(this._hass, id);
      this._flash(`${label} FUB review CSV and Excel downloaded. Follow Up Boss was not updated.`, true);
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _pushStoredFub(sourceId) {
    const id = sourceId || "placer";
    const label = id === "sacramento" ? "Sacramento" : "Placer";
    this._flash(
      `Pushing stored ${label} GOs to Follow Up Boss. No CNPA, no court.`,
      "wait",
    );
    try {
      const st = await ppmRunJob(this._hass, "push_stored_fub", { source_id: id }, (live) => {
        this._flash(ppmJobLiveMessage(live) || `Pushing stored ${label} GOs…`, "wait");
      });
      this._jobSt = st;
      this._renderBody();
      const ok = st.last_result !== "failed" && st.last_result !== "running";
      this._flash(
        ok
          ? (ppmJobDoneMessage(st) || `${label} stored Follow Up Boss push finished.`)
          : (ppmWithCountyPrefix(ppmText(st.last_error) || "stored FUB push failed. Check last_run.log.", { source_id: id })),
        ok,
      );
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _testStored(sourceId) {
    const id = sourceId || "placer";
    const label = id === "sacramento" ? "Sacramento" : "Placer";
    this._flash(`Testing stored ${label} PDFs… no CNPA, no court, Follow Up Boss off.`, "wait");
    try {
      const st = await ppmRunJob(this._hass, "test_stored", { source_id: id }, (live) => {
        this._flash(ppmJobLiveMessage(live) || `Scoring stored ${label} files…`, "wait");
      });
      this._jobSt = st;
      this._storedDocs = await this._hass.callApi("GET", "placer_probate_monitor/stored_docs").catch(() => this._storedDocs);
      this._renderBody();
      const ok = st.last_result !== "failed" && st.last_result !== "running";
      this._flash(
        ok
          ? (ppmJobDoneMessage(st) || `${label} stored test finished.`)
          : (ppmWithCountyPrefix(ppmText(st.last_error) || "stored test failed. Check last_run.log.", { source_id: id })),
        ok,
      );
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _rescan(sourceId) {
    const id = sourceId || "placer";
    const label = id === "sacramento" ? "Sacramento" : "Placer";
    this._flash(`Rescanning local ${label} PDFs… no court servers.`, "wait");
    try {
      const st = await ppmRunJob(this._hass, "rescan", { source_id: id }, (live) => {
        this._flash(ppmJobLiveMessage(live) || `Rescanning ${label} files…`, "wait");
      });
      const ok = st.last_result !== "failed" && st.last_result !== "running";
      this._flash(
        ok
          ? (ppmJobDoneMessage(st) || `${label} local rescan finished.`)
          : (ppmWithCountyPrefix(ppmText(st.last_error) || "local rescan failed. Check last_run.log.", { source_id: id })),
        ok,
      );
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _auditStored(sourceId) {
    const id = sourceId || "placer";
    const label = id === "sacramento" ? "Sacramento" : "Placer";
    this._flash(`Auditing stored ${label} listings and PDFs… no CNPA, no court, Follow Up Boss off.`, "wait");
    try {
      const st = await ppmRunJob(this._hass, "local_audit", { source_id: id }, (live) => {
        this._flash(ppmJobLiveMessage(live) || `Auditing ${label} files…`, "wait");
      });
      this._jobSt = st;
      const ok = st.last_result !== "failed" && st.last_result !== "running";
      this._flash(
        ok
          ? (ppmJobDoneMessage(st) || `${label} local audit finished.`)
          : (ppmWithCountyPrefix(ppmText(st.last_error) || "local audit failed. Check last_run.log.", { source_id: id })),
        ok,
      );
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _preview(sourceId) {
    const id = sourceId || "placer";
    const label = id === "sacramento" ? "Sacramento" : "Placer";
    this._flash(`Preview started… using stored ${label} PDFs for one go-case (view only).`, "wait");
    try {
      const st = await ppmRunJob(this._hass, "preview", { source_id: id }, (live) => {
        this._flash(ppmJobLiveMessage(live) || "Preview is running…", "wait");
      });
      this._jobSt = st;
      ppmRenderPreview(this._qs("#source-preview"), st);
      const ok = st.last_result !== "failed" && st.last_result !== "running";
      const rec = ppmPreviewRecord(st);
      this._flash(
        ok
          ? (rec
            ? `Preview loaded ${rec.case_number}. Review pulled values below.`
            : (st.fub_verify_note || "Preview finished. No go-case in this window."))
          : (ppmText(st.last_error) || "Preview failed."),
        ok,
      );
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _saveSourceMap(sourceId) {
    const mapping = this._mapData.mapping || {};
    const custom_fields = {};
    this.querySelectorAll("[data-custom]").forEach((el) => {
      const value = el.value.trim();
      if (value) custom_fields[el.dataset.custom] = value;
    });
    try {
      this._mapData = await this._hass.callApi("POST", "placer_probate_monitor/fub_mapping", {
        source_id: sourceId,
        system: mapping.system || "PlacerProbateMonitor",
        subject_address_type: mapping.subject_address_type || "subject property",
        court_search_url: mapping.court_search_url || "",
        skip_petitioner_contains: mapping.skip_petitioner_contains || [],
        send: mapping.send || {},
        custom_fields,
      });
      this._renderList();
      this._renderBody();
      this._flash("Follow Up Boss mapping saved.", true);
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  _bindExamplePerson() {
    const btn = this._qs(".fub-person-load");
    if (!btn) return;
    btn.addEventListener("click", () => this._loadFubExample());
  }

  async _loadFubExample() {
    const input = this._qs(".fub-person-q");
    const q = ((input && input.value) || "").trim();
    if (!q) {
      this._flash("Enter a Follow Up Boss person id or name.", false);
      return;
    }
    this._flash("Loading example person from Follow Up Boss…", true);
    try {
      this._fubPerson = await ppmFetchFubPerson(this._hass, q);
      this._renderList();
      this._renderBody();
      this._flash(`Loaded example FUB person ${this._fubPerson.person_id}.`, true);
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }
}

class PlacerProbateFubPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._catalog = { probate_fields: [], send_toggles: [], go_no_go: [], default_custom_fields: {} };
    this._fubFields = [];
    this._fubBuiltins = [];
    this._ready = false;
    this._tab = "connection";
    this._mapSource = "placer";
    this._mapData = {};
    this._fubPerson = null;
    this._storedDocs = { counties: [] };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._ready) {
      this._ready = true;
      this._renderShell();
      this._loadAll(false);
    }
  }

  get hass() {
    return this._hass;
  }

  _qs(sel) {
    return this.querySelector(sel);
  }

  _flash(msg, ok) {
    const el = this._qs("#flash");
    if (!el) return;
    el.textContent = msg;
    el.className = "ppm-banner show " + ppmBannerKind(ok);
  }

  _renderShell() {
    this.innerHTML = `
      <div class="ppm-page-intro ppm-wide">
        <h2 class="ppm-page-title">Follow Up Boss</h2>
        <p>CRM connection, one-case verification, and field mapping. County import screens are under Probate sources.</p>
        <div class="ppm-tabs">
          <button class="ghost active" type="button" data-tab="connection">Connection &amp; preview</button>
          <button class="ghost" type="button" data-tab="mapping">Field mapping</button>
        </div>
      </div>
      <main class="ppm-wide">
        <div id="flash" class="ppm-banner"></div>
        <div id="stored-docs-host"></div>
          <div class="ppm-fub-layout">
            <div>
          <section class="ppm-card" id="tab-connection">
            <h2>Connection</h2>
            <details class="ppm-fold">
              <summary>Show connection settings</summary>
            <label class="ppm-toggle"><input id="fub_enabled" type="checkbox" /><span>Enable Follow Up Boss export</span></label>
            <label>API URL</label>
            <input id="fub_api_url" />
            <label>API key (leave blank to keep the saved key)</label>
            <input id="fub_api_key" type="password" placeholder="unchanged if blank" />
            <p class="ppm-note" id="key-note"></p>
            <label>FUB system key (optional, for Files). Leave blank to keep the saved key</label>
            <input id="fub_system_key" type="password" placeholder="unchanged if blank" />
            <p class="ppm-note" id="system-key-note">Follow Up Boss Files requires a registered X-System-Key. Without it the DE-111 is posted as a Notes link instead.</p>
            <div class="ppm-row">
              <div><label>Lead source name</label><input id="fub_source" /></div>
              <div><label>Assign to</label><input id="fub_assigned_to" /></div>
            </div>
            <p class="ppm-note">County people use the read-only lead source on each Probate sources card (probate for every county). This field is a fallback for other events.</p>
            <label>Person stage</label>
            <input id="fub_stage" placeholder="Must match a Follow Up Boss stage name (leave blank for FUB default)" />
            <label>Event type</label>
            <select id="fub_event_type"></select>
            <h2 style="margin-top:16px;">Required for Go</h2>
            <p class="ppm-note">Always-on NO-GO rules cannot be unchecked: real-property GMV present and at least $200,000, not a professional fiduciary, and the Follow Up Boss person was not deleted. Path A checklist (same for Placer and Sacramento FUB create): petitioner first name (real person, not a form caption), petitioner last name, petitioner mailing address (street, not caption or legal description). estate_real GMV ≥ $200,000 is always required. Decedent residence is collected but not required for GO unless checked. Path B is always an alternate: petitioner name, decedent name, decedent address, and petitioner phone — mailing is not required on Path B. Case number is never required. Unchecked Path A fields stay optional. Petitioner is the Follow Up Boss person. Save with Save FUB connection.</p>
            <div id="fub-go-always"></div>
            <p class="ppm-note" style="margin-top:10px;">Path A checklist</p>
            <div id="fub-go-required"></div>
            <label class="ppm-toggle"><input id="fub_verify_only" type="checkbox" /><span>Verify only: update one person per run</span></label>
            <label class="ppm-toggle"><input id="fub_update_existing" type="checkbox" /><span>Force PUT even when the person payload is unchanged</span></label>
            <p class="ppm-note">Daily harvest already POSTs when there is no Follow Up Boss id, and PUTs the existing person plus the probate note in place when fields change. Turn this on before Push stored GOs (or Rescan local files with FUB on) to rewrite people even when the payload matches the last send. Deleted Follow Up Boss people stay skipped (fub_removed): Force PUT does not recreate them. Probate, DE-111, DE-147, and eCourt notes are updated in place; extras of those types are removed. Skip professional fiduciary. Leave it off for daily runs.</p>
            <div class="ppm-actions">
              <button id="save-fub" type="button">Save FUB connection</button>
            </div>
            <h2 style="margin-top:16px;">Duplicate probate notes</h2>
            <p class="ppm-note">Dry-run counts extra Placer/Sacramento probate notes created by this monitor. Apply keeps one note (merged/latest body) and deletes only extras with [PPM-NOTE] or our probate subject. DE-111 / DE-147 / eCourt notes stay unless they are exact duplicates. CRM notes are never deleted. Live apply requires one person ID and will not run for every listing.</p>
            <label>Person ID (required to apply)</label>
            <input id="fub_cleanup_person_id" inputmode="numeric" placeholder="e.g. 5172" />
            <div class="ppm-actions">
              <button class="secondary" id="cleanup-fub-notes-dry" type="button">Dry-run duplicate notes</button>
              <button class="secondary" id="cleanup-fub-notes-apply" type="button">Apply one person</button>
            </div>
            <pre class="ppm-pre" id="cleanup-fub-notes-out"></pre>
            </details>
          </section>
          <section class="ppm-card" id="fub-preview-one">
            <h2>Preview / update single record</h2>
            <p class="ppm-note">Preview and Verify use stored listings (and the PDFs already attached to that case). They do not rescan every petition. Check Use existing and enter a Follow Up Boss person ID to open that listing. Leave it unchecked to preview the first GO listing. Preview does not post.</p>
            <label class="ppm-toggle"><input id="fub_verify_existing" type="checkbox" /><span>Use existing Follow Up Boss person</span></label>
            <label>Existing person ID</label>
            <input id="fub_verify_person_id" inputmode="numeric" placeholder="e.g. 12345" />
            <div class="ppm-actions">
              <button class="secondary" id="preview-one" type="button">Preview one record</button>
              <button class="secondary" id="verify-fub" type="button">Verify one FUB import</button>
            </div>
          </section>
          <section class="ppm-card" id="verify-record">
            <h2>Last verify record</h2>
            <p class="ppm-note">Run Verify one FUB import to show the go-case that was posted.</p>
          </section>
          <div id="tab-mapping" class="ppm-hide">
            <section class="ppm-card" id="go-no-go">
              <h2>Go / no-go data requirements</h2>
              <div id="go-no-go-body"></div>
              <p class="ppm-note" id="path-line"></p>
            </section>
            <section class="ppm-card">
              <h2>Person &amp; event sends</h2>
              <div id="toggles"></div>
              <div class="ppm-row">
                <div><label>Event system name</label><input id="system" /></div>
                <div><label>Subject address type</label><input id="subject_address_type" /></div>
              </div>
              <label>Court search URL</label>
              <input id="court_search_url" />
              <label>Skip petitioner names containing (one phrase per line)</label>
              <textarea id="skip_petitioner_contains"></textarea>
            </section>
            <section class="ppm-card">
              <h2>Custom field associations</h2>
              <p class="ppm-note">Dropdowns are live custom fields from Follow Up Boss. Pick a county source, then map each extract column. Built-in person fields (name, address) are not listed here.</p>
              <div class="ppm-tabs" id="map-sources"></div>
              <div class="ppm-actions" style="margin-top:12px;">
                <button class="secondary" id="load-fub" type="button">Reload FUB custom fields</button>
              </div>
              <p class="ppm-note" id="fub-fields-note"></p>
              <table><thead><tr><th>Source field</th><th>From</th><th>FUB custom field</th><th>Example person</th></tr></thead>
              <tbody id="matrix"></tbody></table>
              <div class="ppm-actions"><button id="save" type="button">Save mapping</button></div>
            </section>
          </div>
            </div>
            <aside class="ppm-card ppm-fub-side" id="live-client">
              <h2>Live FUB client</h2>
              <p class="ppm-note">Stays open while you map. Pull a real contact to see its values and which probate fields are associated.</p>
              <label>Person id or name</label>
              <input id="live-client-q" placeholder="e.g. 12345 or Jane Doe" />
              <div class="ppm-actions">
                <button class="secondary" id="load-live-client" type="button">Pull live client</button>
              </div>
              <div id="live-client-body"></div>
            </aside>
          </div>
        </main>
    `;
    this.querySelectorAll("[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => this._setTab(btn.dataset.tab));
    });
    this._qs("#save").addEventListener("click", () => this._saveMapping());
    this._qs("#load-fub").addEventListener("click", () => this._loadMapping(true));
    this._qs("#load-live-client").addEventListener("click", () => this._loadPerson());
    this._qs("#save-fub").addEventListener("click", () => this._saveSettings());
    this._qs("#verify-fub").addEventListener("click", () => this._verify());
    this._qs("#preview-one").addEventListener("click", () => this._preview());
    this._qs("#cleanup-fub-notes-dry").addEventListener("click", () => this._cleanupNotes(false));
    this._qs("#cleanup-fub-notes-apply").addEventListener("click", () => this._cleanupNotes(true));
    this._renderStoredDocs();
  }

  _renderStoredDocs() {
    const host = this._qs("#stored-docs-host");
    if (!host) return;
    host.innerHTML = ppmStoredDocsCard(this._storedDocs);
    host.querySelectorAll("[data-stored-zip]").forEach((btn) => {
      btn.addEventListener("click", () => this._downloadStoredZip(btn.dataset.storedZip));
    });
  }

  async _downloadStoredZip(sourceId) {
    try {
      await ppmDownloadStoredZip(this._hass, sourceId);
      this._flash(`Saved ${sourceId || "all"} stored PDFs zip.`, true);
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  _setTab(tab) {
    this._tab = tab;
    this.querySelectorAll("[data-tab]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === tab);
    });
    this._qs("#tab-connection").classList.toggle("ppm-hide", tab !== "connection");
    this._qs("#verify-record").classList.toggle("ppm-hide", tab !== "connection");
    this._qs("#tab-mapping").classList.toggle("ppm-hide", tab !== "mapping");
  }

  _applySettings(data) {
    this._qs("#fub_enabled").checked = !!data.fub_enabled;
    this._qs("#fub_api_url").value = data.fub_api_url || "https://api.followupboss.com/v1";
    this._qs("#fub_api_key").value = "";
    this._qs("#fub_system_key").value = "";
    this._qs("#key-note").textContent = data.fub_api_key_set
      ? "An API key is already saved."
      : "No API key saved yet.";
    this._qs("#system-key-note").textContent = data.fub_system_key_set
      ? "A FUB system key is already saved. Files uploads will use it."
      : "No FUB system key saved. Files API will 403; DE-111 goes to Notes as a download link.";
    this._qs("#fub_source").value = data.fub_source || "probate";
    this._qs("#fub_assigned_to").value = data.fub_assigned_to || "";
    this._qs("#fub_stage").value = data.fub_stage || "";
    const types = data.event_types || ["Seller Inquiry"];
    this._qs("#fub_event_type").innerHTML = types
      .map((item) => `<option value="${ppmEsc(item)}">${ppmEsc(item)}</option>`)
      .join("");
    this._qs("#fub_event_type").value = data.fub_event_type || "Seller Inquiry";
    this._renderGoRequired(data);
    this._qs("#fub_verify_only").checked = data.fub_verify_only !== false;
    this._qs("#fub_update_existing").checked = !!data.fub_update_existing;
    this._qs("#fub_verify_existing").checked = !!data.fub_verify_existing;
    this._qs("#fub_verify_person_id").value = data.fub_verify_person_id || "";
  }

  _renderGoRequired(data) {
    const alwaysEl = this._qs("#fub-go-always");
    const always = (data && data.fub_go_always_nogo) || [
      {
        key: "estate_real",
        label: "Real property GMV at least $200,000",
        when: "Always. Missing or blank GMV is NO-GO. Tiny OCR crumbs ($1/$2/$6/$9) count as missing. Under $200,000 (including $0) is NO-GO. Annual income from real property is not this gate.",
      },
      {
        key: "professional_fiduciary",
        label: "Not a professional fiduciary",
        when: "Always. Fiduciary listings stay on the board as NO-GO and are not created or updated in Follow Up Boss.",
      },
      {
        key: "fub_removed",
        label: "Follow Up Boss person was not deleted",
        when: "Always. A deleted person is marked fub_removed and is not recreated.",
      },
    ];
    if (alwaysEl) {
      alwaysEl.innerHTML = always.map((item) => `
      <label class="ppm-toggle">
        <input type="checkbox" checked disabled />
        <span>${ppmEsc(item.label)}${item.when ? `<div class="ppm-note">${ppmEsc(item.when)}</div>` : ""}</span>
      </label>`).join("");
    }
    const el = this._qs("#fub-go-required");
    if (!el) return;
    const fields = (data && data.fub_go_gate_fields) || [
      { key: "petitioner_first", label: "Petitioner first name" },
      { key: "petitioner_last", label: "Petitioner last name" },
      { key: "mailing_address", label: "Petitioner mailing address" },
      { key: "decedent_residence", label: "Estate location (decedent residence)" },
    ];
    const selected = new Set(
      (data && data.fub_go_required_fields)
        || ["petitioner_first", "petitioner_last", "mailing_address"]
    );
    if (data && data.fub_strict_property) selected.add("decedent_residence");
    el.innerHTML = fields.map((item) => `
      <label class="ppm-toggle">
        <input type="checkbox" data-go-required value="${ppmEsc(item.key)}" ${selected.has(item.key) ? "checked" : ""} />
        <span>${ppmEsc(item.label)}</span>
      </label>`).join("");
  }

  _goRequiredFields() {
    return [...this.querySelectorAll("#fub-go-required [data-go-required]:checked")]
      .map((el) => el.value);
  }

  _renderVerify(st) {
    this._jobSt = st || this._jobSt;
    this._lastRec = ppmPreviewRecord(st);
    ppmRenderPreview(this._qs("#verify-record"), st);
    this._renderLiveClient();
  }

  _applyMapping(data) {
    this._mapData = data || {};
    this._catalog = data.catalog || this._catalog;
    this._fubFields = data.fub_custom_fields || [];
    this._fubBuiltins = data.fub_builtin_fields || [];
    this._mapSource = data.source_id || this._mapSource || "placer";
    const mapping = data.mapping || {};
    const send = mapping.send || {};
    this._renderGoNoGo();
    const sources = data.data_sources || [];
    this._qs("#map-sources").innerHTML = sources.map((src) => {
      const active = src.id === this._mapSource ? "active" : "";
      const label = src.status === "live" ? "Live" : "Later";
      return `<button class="secondary ${active}" type="button" data-map-source="${ppmEsc(src.id)}">${ppmEsc(src.name)} <span class="ppm-pill ${src.status === "live" ? "live" : "wait"}">${label}</span></button>`;
    }).join("");
    this.querySelectorAll("[data-map-source]").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._mapSource = btn.dataset.mapSource;
        this._renderGoNoGo();
        this._renderMatrix();
        this._renderLiveClient();
        this.querySelectorAll("[data-map-source]").forEach((el) => {
          el.classList.toggle("active", el.dataset.mapSource === this._mapSource);
        });
      });
    });
    const sourceName = (sources.find((item) => item.id === this._mapSource) || {}).name
      || this._catalog.data_source_name
      || "Placer County";
    this._qs("#path-line").textContent =
      "Mapping file: " + (data.path || "fub_mapping.yaml")
      + " · Source: " + sourceName
      + (data.exists ? "" : " (bundled defaults until you save)");
    this._qs("#system").value = mapping.system || "PlacerProbateMonitor";
    this._qs("#subject_address_type").value = mapping.subject_address_type || "subject property";
    this._qs("#court_search_url").value = mapping.court_search_url || "";
    this._qs("#skip_petitioner_contains").value = (mapping.skip_petitioner_contains || []).join("\n");
    this._qs("#toggles").innerHTML = (this._catalog.send_toggles || []).map((item) => {
      const on = item.forced === false ? false : send[item.key] !== false;
      const disabled = item.editable === false ? "disabled" : "";
      const reason = item.reason ? `<span class="ppm-note">${ppmEsc(item.reason)}</span>` : "";
      return `<label class="ppm-toggle"><input type="checkbox" data-send="${ppmEsc(item.key)}" ${on ? "checked" : ""} ${disabled} /><span>${ppmEsc(item.label)} ${reason}</span></label>`;
    }).join("");
    this._renderMatrix();
    this._qs("#fub-fields-note").textContent = data.fub_custom_error
      ? data.fub_custom_error
      : (this._fubFields.length
        ? `Loaded ${this._fubFields.length} custom fields plus built-in person fields as dropdown options.`
        : "No custom fields came back from Follow Up Boss. Create them in FUB, then reload.");
    this._renderLiveClient();
  }

  _renderGoNoGo() {
    const el = this._qs("#go-no-go-body");
    if (!el) return;
    const data = this._mapData || {};
    const sources = data.data_sources || [];
    const sourceName = (sources.find((item) => item.id === this._mapSource) || {}).name
      || this._catalog.data_source_name
      || this._mapSource
      || "this source";
    const spec = ppmSourceGoNoGo(data, data, this._mapSource || "placer");
    el.innerHTML = ppmGoNoGoInner(spec, sourceName);
  }

  _renderMatrix() {
    const data = this._mapData || {};
    const fields = (data.source_fields && data.source_fields[this._mapSource])
      || this._catalog.probate_fields
      || [];
    const mapping = data.mapping || {};
    const custom = ((mapping.source_mappings
      && mapping.source_mappings[this._mapSource]
      && mapping.source_mappings[this._mapSource].custom_fields)
      || (this._mapSource === "placer" ? mapping.custom_fields : {})
      || {});
    this._qs("#matrix").innerHTML = ppmMappingRows(
      fields,
      custom,
      this._fubFields || [],
      this._fubPerson,
      this._fubBuiltins || [],
      this._catalog.default_custom_fields || {},
    );
    ppmBindMappingExamples(this._qs("#matrix"), this._fubPerson);
    this.querySelectorAll("#matrix select[data-custom]").forEach((el) => {
      el.addEventListener("change", () => this._renderLiveClient());
    });
  }

  _renderLiveClient() {
    const el = this._qs("#live-client-body");
    if (!el) return;
    const data = this._mapData || {};
    const fields = (data.source_fields && data.source_fields[this._mapSource])
      || this._catalog.probate_fields
      || [];
    const mapping = Object.assign({}, data.mapping || {});
    const custom = {};
    this.querySelectorAll("#matrix select[data-custom]").forEach((input) => {
      if (input.value.trim()) custom[input.dataset.custom] = input.value.trim();
    });
    if (Object.keys(custom).length) {
      mapping.source_mappings = Object.assign({}, mapping.source_mappings || {});
      mapping.source_mappings[this._mapSource || "placer"] = { custom_fields: custom };
    }
    const associations = ppmFieldAssociations(mapping, this._mapSource, fields);
    el.innerHTML = ppmLiveClientHtml(this._fubPerson, associations)
      + (this._fubPerson && this._lastRec ? ppmCompareExtractToFub(this._lastRec, this._fubPerson) : "");
  }

  _mappingPayload() {
    const send = {};
    this.querySelectorAll("[data-send]").forEach((el) => {
      send[el.dataset.send] = !!el.checked;
    });
    const custom_fields = {};
    this.querySelectorAll("[data-custom]").forEach((el) => {
      const value = el.value.trim();
      if (value) custom_fields[el.dataset.custom] = value;
    });
    return {
      system: this._qs("#system").value.trim(),
      subject_address_type: this._qs("#subject_address_type").value.trim(),
      court_search_url: this._qs("#court_search_url").value.trim(),
      skip_petitioner_contains: this._qs("#skip_petitioner_contains").value
        .split(/\n/).map((x) => x.trim()).filter(Boolean),
      send,
      custom_fields,
      source_id: this._mapSource,
    };
  }

  async _loadAll(refreshMapping) {
    try {
      const [settings, mapping, job, stored] = await Promise.all([
        this._hass.callApi("GET", "placer_probate_monitor/fub_settings"),
        this._hass.callApi("GET", "placer_probate_monitor/fub_mapping"),
        this._hass.callApi("GET", "placer_probate_monitor/job").catch(() => ({})),
        this._hass.callApi("GET", "placer_probate_monitor/stored_docs").catch(() => ({ counties: [] })),
      ]);
      this._storedDocs = stored || { counties: [] };
      this._applySettings(settings);
      this._applyMapping(mapping);
      this._renderVerify(job);
      this._renderStoredDocs();
      if (refreshMapping) {
        this._flash(this._fubFields.length ? "Loaded FUB custom fields." : "No FUB fields loaded.", !!this._fubFields.length);
      }
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _loadMapping(refresh) {
    await this._loadAll(refresh);
  }

  async _loadPerson() {
    const input = this._qs("#live-client-q");
    const q = ((input && input.value) || "").trim();
    if (!q) {
      this._flash("Enter a Follow Up Boss person id or name.", false);
      return;
    }
    this._flash("Loading live FUB client…", true);
    try {
      this._fubPerson = await ppmFetchFubPerson(this._hass, q);
      this._renderMatrix();
      this._renderLiveClient();
      this._flash(`Loaded live FUB client ${this._fubPerson.person_id}.`, true);
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _saveSettings() {
    const body = {
      fub_enabled: this._qs("#fub_enabled").checked,
      fub_api_url: this._qs("#fub_api_url").value.trim(),
      fub_api_key: this._qs("#fub_api_key").value,
      fub_system_key: this._qs("#fub_system_key").value,
      fub_source: this._qs("#fub_source").value.trim(),
      fub_assigned_to: this._qs("#fub_assigned_to").value.trim(),
      fub_stage: this._qs("#fub_stage").value.trim(),
      fub_event_type: this._qs("#fub_event_type").value,
      fub_go_required_fields: this._goRequiredFields(),
      fub_verify_only: this._qs("#fub_verify_only").checked,
      fub_update_existing: this._qs("#fub_update_existing").checked,
      fub_verify_existing: this._qs("#fub_verify_existing").checked,
      fub_verify_person_id: this._qs("#fub_verify_person_id").value.trim(),
    };
    try {
      const data = await this._hass.callApi("POST", "placer_probate_monitor/fub_settings", body);
      this._applySettings(data);
      this._flash("Follow Up Boss connection saved.", true);
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _saveMapping() {
    try {
      const data = await this._hass.callApi(
        "POST",
        "placer_probate_monitor/fub_mapping",
        this._mappingPayload(),
      );
      this._applyMapping(data);
      this._flash("FUB field mapping saved.", true);
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _verify() {
    const useExisting = this._qs("#fub_verify_existing").checked;
    const personId = (this._qs("#fub_verify_person_id").value || "").trim();
    if (useExisting && !/^\d+$/.test(personId)) {
      this._flash("Enter the Follow Up Boss person ID to update.", false);
      return;
    }
    this._flash(
      useExisting
        ? `Verify started… updating FUB person ${personId}.`
        : "Verify started… using stored listings for one go-case.",
      "wait",
    );
    try {
      const st = await ppmRunJob(this._hass, "verify", {
        fub_verify_existing: useExisting,
        fub_verify_person_id: personId,
        source_id: this._mapSource || "placer",
      }, (live) => {
        this._flash(ppmJobLiveMessage(live) || "Verify is running…", "wait");
      });
      const ok = st.last_result !== "failed" && st.last_result !== "running";
      this._renderVerify(st);
      const rec = ppmPreviewRecord(st);
      this._flash(
        ok
          ? (rec
            ? (rec.posted
              ? (rec.updated
                ? `Verify updated ${rec.case_number} (FUB person ${rec.fub_person_id}).`
                : `Verify posted ${rec.case_number} as FUB person ${rec.fub_person_id}.`)
              : `Verify mapped ${rec.case_number} but Follow Up Boss did not accept it. Record is shown below.`)
            : (st.fub_verify_note || "Verify finished. No go-case was mapped."))
          : (ppmText(st.last_error) || "Verify failed."),
        ok && !(rec && rec.fub_error),
      );
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _cleanupNotes(apply) {
    const personId = (this._qs("#fub_cleanup_person_id").value || "").trim();
    const out = this._qs("#cleanup-fub-notes-out");
    if (apply && !/^\d+$/.test(personId)) {
      this._flash("Enter one Follow Up Boss person ID to apply note cleanup.", false);
      return;
    }
    this._flash(
      apply
        ? `Cleaning duplicate probate notes for FUB person ${personId}…`
        : "Dry-running duplicate probate notes…",
      "wait",
    );
    try {
      const payload = await this._hass.callApi(
        "POST",
        "placer_probate_monitor/fub_notes_cleanup",
        {
          dry_run: !apply,
          apply: !!apply,
          person_id: personId,
        },
      );
      const dups = payload.people_with_duplicate_notes ?? 0;
      const extra = payload.extra_notes ?? 0;
      const people = payload.people ?? 0;
      out.textContent = JSON.stringify(
        {
          dry_run: payload.dry_run,
          people,
          people_with_duplicate_notes: dups,
          extra_notes: extra,
          rows: (payload.rows || []).filter((row) => row.would_change).slice(0, 20),
        },
        null,
        2,
      );
      this._flash(
        apply
          ? `Cleaned FUB person ${personId}. Extra notes removed: ${extra}.`
          : `Dry-run: ${people} people, ${dups} with duplicate monitor notes, ${extra} extras.`,
        true,
      );
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _preview() {
    const useExisting = this._qs("#fub_verify_existing").checked;
    const personId = (this._qs("#fub_verify_person_id").value || "").trim();
    if (useExisting && !/^\d+$/.test(personId)) {
      this._flash("Enter the Follow Up Boss person ID to preview.", false);
      return;
    }
    this._flash(
      useExisting
        ? `Preview started… stored listing for FUB person ${personId} (view only).`
        : "Preview started… using stored listings for one go-case (view only).",
      "wait",
    );
    try {
      const st = await ppmRunJob(this._hass, "preview", {
        fub_verify_existing: useExisting,
        fub_verify_person_id: personId,
      }, (live) => {
        this._flash(ppmJobLiveMessage(live) || "Preview is running…", "wait");
      });
      const ok = st.last_result !== "failed" && st.last_result !== "running";
      this._renderVerify(st);
      const rec = ppmPreviewRecord(st);
      this._flash(
        ok
          ? (rec
            ? `Preview loaded ${rec.case_number} (not posted).`
            : (st.fub_verify_note || "Preview finished. No go-case in this window."))
          : (ppmText(st.last_error) || "Preview failed."),
        ok,
      );
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }
}

customElements.define("placer-probate-sources-panel", PlacerProbateSourcesPanel);
customElements.define("placer-probate-fub-panel", PlacerProbateFubPanel);

class PlacerProbateListingsPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._ready = false;
    this._rows = [];
    this._share = {};
    this._query = "";
    this._source = "";
    this._fub = "";
    this._sortKey = "added_at";
    this._sortDir = "desc";
    this._colFilters = {};
    this._documentBase = "";
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._ready) {
      this._ready = true;
      this._renderShell();
      this._load();
    }
  }

  get hass() {
    return this._hass;
  }

  _qs(sel) {
    return this.querySelector(sel);
  }

  _flash(msg, ok) {
    const el = this._qs("#flash");
    if (!el) return;
    el.textContent = msg;
    el.className = "ppm-banner show " + ppmBannerKind(ok);
  }

  _renderShell() {
    this.innerHTML = `
      <div class="ppm-page-intro ppm-wide">
        <h2 class="ppm-page-title">Probate listings</h2>
        <p>Collected county cases. Date is the newspaper notice date. Source is the county import. Placer decedent address is DE-111 item 3.a.(2) when marked, else 3c. Sacramento uses the published notice, Journal Technologies public portal (node/397), and public DE-111 / DE-147 PDFs. After Test stored or Rescan with Follow Up Boss off, use Export FUB review: exact FUB payload from stored listings; API not called.</p>
      </div>
      <main class="ppm-listings">
        <div id="flash" class="ppm-banner"></div>
          <section class="ppm-card">
            <div class="ppm-listings-tools">
              <div>
                <label>Filter</label>
                <input id="listing-q" placeholder="Case, petitioner, decedent, address, FUB id" />
              </div>
              <div>
                <label>Source</label>
                <select id="listing-source">
                  <option value="">All sources</option>
                  <option value="placer">Placer County</option>
                  <option value="sacramento">Sacramento County</option>
                </select>
              </div>
              <div>
                <label>Listings Status</label>
                <select id="listing-fub">
                  <option value="">All Listings</option>
                  <option value="no_id">no id</option>
                  <option value="id">ID</option>
                  <option value="deleted">deleted</option>
                </select>
              </div>
              <div>
                <label>&nbsp;</label>
                <div class="ppm-actions" style="margin-top:0;">
                  <button type="button" id="listing-reload">Reload</button>
                  <button type="button" id="listing-share" class="secondary">Copy share link</button>
                  <button type="button" id="listing-csv" class="secondary">Export CSV</button>
                  <button type="button" id="listing-xlsx" class="secondary">Export Excel</button>
                  <button type="button" id="listing-fub-review" class="secondary">Export FUB review (CSV/Excel)</button>
                </div>
              </div>
            </div>
            <p class="ppm-note">Export FUB review: exact FUB payload from stored listings; API not called.</p>
            <p class="ppm-note" id="listing-count"></p>
            <div class="ppm-table-wrap" id="listing-table"></div>
          </section>
        </main>
    `;
    this._qs("#listing-reload").addEventListener("click", () => this._load());
    this._qs("#listing-share").addEventListener("click", () => this._copyShare());
    this._qs("#listing-csv").addEventListener("click", () => this._export("csv"));
    this._qs("#listing-xlsx").addEventListener("click", () => this._export("xlsx"));
    this._qs("#listing-fub-review").addEventListener("click", () => this._exportFubReview());
    this._qs("#listing-q").addEventListener("input", (ev) => {
      this._query = ev.target.value || "";
      this._renderTable();
    });
    this._qs("#listing-source").addEventListener("change", (ev) => {
      this._source = ev.target.value || "";
      this._renderTable();
    });
    this._qs("#listing-fub").addEventListener("change", (ev) => {
      this._fub = ev.target.value || "";
      this._renderTable();
    });
  }

  _filtered() {
    const q = this._query.trim().toLowerCase();
    const source = this._source;
    const fub = this._fub;
    const rows = this._rows.filter((row) => {
      if (source && String(row.source_id || "").toLowerCase() !== source) return false;
      if (fub && String(row.fub_status || "") !== fub) return false;
      if (!q) return true;
      const blob = [
        row.case_number, row.date, row.added_at, row.source, row.petitioner, row.decedent,
        row.decedent_address, row.petitioner_address, row.newspaper, row.filed, row.hearing,
        row.go_status, ppmListingGoLabel(row), row.nogo_reason, ppmListingGoReasonLabel(row),
        row.fub_status, ppmListingFubLabel(row), row.fub_person_id,
      ].map((item) => String(item || "").toLowerCase()).join(" ");
      return blob.includes(q);
    });
    return ppmListingApplyColumnFilters(rows, this._colFilters);
  }

  _visible() {
    return ppmListingVisibleRows(this._filtered(), {
      sortKey: this._sortKey,
      sortDir: this._sortDir,
    });
  }

  _toggleSort(key) {
    if (!key) return;
    if (this._sortKey === key) {
      this._sortDir = this._sortDir === "desc" ? "asc" : "desc";
    } else {
      this._sortKey = key;
      this._sortDir = (key === "added_at" || key === "date" || key === "hearing") ? "desc" : "asc";
    }
    this._renderTable();
  }

  _filterControl(col) {
    const value = ppmEsc(this._colFilters[col.key] || "");
    if (col.kind === "go") {
      const selected = this._colFilters[col.key] || "";
      const opts = [
        ["", "All GO"],
        ["GO", "GO"],
        ["NO-GO", "NO-GO"],
      ].map(([code, label]) => (
        `<option value="${code}"${selected === code ? " selected" : ""}>${label}</option>`
      )).join("");
      return `<select class="ppm-col-filter" data-filter="${col.key}">${opts}</select>`;
    }
    if (col.kind === "ocr") {
      const selected = this._colFilters[col.key] || "";
      const opts = [
        ["", "All OCR"],
        ["yes", "Yes"],
        ["-", "—"],
      ].map(([code, label]) => (
        `<option value="${code}"${selected === code ? " selected" : ""}>${label}</option>`
      )).join("");
      return `<select class="ppm-col-filter" data-filter="${col.key}">${opts}</select>`;
    }
    if (col.kind === "fub") {
      const selected = this._colFilters[col.key] || "";
      const opts = [
        ["", "All Listings"],
        ["no_id", "no id"],
        ["id", "ID"],
        ["deleted", "deleted"],
      ].map(([code, label]) => (
        `<option value="${code}"${selected === code ? " selected" : ""}>${label}</option>`
      )).join("");
      return `<select class="ppm-col-filter" data-filter="${col.key}">${opts}</select>`;
    }
    return `<input class="ppm-col-filter" data-filter="${col.key}" value="${value}" placeholder="${ppmEsc(col.placeholder)}" />`;
  }

  _docsCell(row) {
    const docs = ppmListingDocs(row, this._documentBase);
    if (!docs.length) return "—";
    return docs.map((item) => (
      `<a href="${ppmEsc(item.url)}" target="_blank" rel="noopener">${ppmEsc(item.label)}</a>`
    )).join(" · ");
  }

  _goCell(row) {
    const label = ppmListingGoLabel(row);
    if (label === "GO") return `<span class="ppm-pill live">GO</span>`;
    if (label === "NO-GO") return `<span class="ppm-pill off">NO-GO</span>`;
    return `<span class="ppm-pill">${ppmEsc(label || "—")}</span>`;
  }

  _fubCell(row) {
    const label = ppmListingFubLabel(row);
    const status = String(row.fub_status || "");
    if (status === "deleted" || row.fub_removed) {
      return `<span class="ppm-pill off">deleted</span>`;
    }
    if (status === "id") {
      return `<span class="ppm-pill live">${ppmEsc(label)}</span>`;
    }
    return `<span class="ppm-pill">no id</span>`;
  }

  async _copyShare() {
    const url = ppmListingsShareUrl(this._hass, this._share);
    if (!url) {
      this._flash("Share link is not available yet. Reload listings after the integration is configured.", false);
      return;
    }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(url);
      } else {
        const box = document.createElement("textarea");
        box.value = url;
        document.body.appendChild(box);
        box.select();
        document.execCommand("copy");
        box.remove();
      }
      this._flash("Copied public listings link. Anyone with the URL can view it until you rotate the integration entry.", true);
    } catch (err) {
      this._flash(ppmText(err) || "Could not copy the share link.", false);
    }
  }

  async _exportFubReview() {
    this._flash("Exporting Follow Up Boss review from stored listings. This does not create FUB people.", "wait");
    try {
      await ppmExportFubReview(this._hass, this._source || "");
      this._flash("FUB review CSV and Excel downloaded. Follow Up Boss was not updated.", true);
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  async _export(kind) {
    const ext = kind === "xlsx" ? "xlsx" : "csv";
    const qs = new URLSearchParams();
    if ((this._query || "").trim()) qs.set("q", this._query.trim());
    if (this._source) qs.set("source_id", this._source);
    if (this._fub) qs.set("fub_status", this._fub);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    const label = ext === "xlsx" ? "Excel" : "CSV";
    this._flash(`Exporting listings ${label}…`, "wait");
    try {
      await ppmDownloadAuthFile(
        this._hass,
        `listings.${ext}${suffix}`,
        `probate-listings.${ext}`,
      );
      this._flash(`Exported listings to ${label}.`, true);
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }

  _renderTable() {
    const focused = this._qs(".ppm-col-filter:focus");
    const focusKey = focused && focused.dataset.filter;
    const caret = focused && typeof focused.selectionStart === "number" ? focused.selectionStart : null;
    const rows = this._visible();
    const total = this._rows.length;
    if (!total) {
      this._qs("#listing-count").textContent = "No collected listings yet. Run a county import or Preview one extract.";
    } else {
      this._qs("#listing-count").textContent = rows.length
        ? `${rows.length} listing${rows.length === 1 ? "" : "s"}`
        : "No listings match the current filters.";
    }
    const heads = PPM_LISTING_TABLE_COLUMNS.map((col) => {
      const arrow = this._sortKey === col.key ? (this._sortDir === "asc" ? "▲" : "▼") : "";
      const ind = arrow ? `<span class="ppm-sort-ind">${arrow}</span>` : "";
      return `<th class="ppm-th-sort" data-key="${col.key}" title="Sort by ${ppmEsc(col.label)}">${ppmEsc(col.label)}${ind}</th>`;
    }).join("");
    const filters = PPM_LISTING_TABLE_COLUMNS.map((col) => `<th>${this._filterControl(col)}</th>`).join("");
    const body = rows.map((row) => {
      const caseCell = row.notice_url
        ? `<a href="${ppmEsc(row.notice_url)}" target="_blank" rel="noopener">${ppmEsc(row.case_number)}</a>`
        : ppmEsc(row.case_number);
      return `<tr>
        <td>${ppmEsc(row.date || row.filed || "—")}</td>
        <td>${ppmEsc(row.added_at || "—")}</td>
        <td>${ppmEsc(row.source || "Placer County")}</td>
        <td>${caseCell}</td>
        <td>${this._docsCell(row)}</td>
        <td>${this._goCell(row)}</td>
        <td>${ppmEsc(ppmListingGoReasonLabel(row) || "—")}</td>
        <td>${ppmEsc(row.petitioner || "—")}<div class="ppm-note">${ppmEsc(row.petitioner_address || "")}</div></td>
        <td>${ppmEsc(row.decedent || "—")}</td>
        <td>${ppmEsc(row.decedent_address || "—")}</td>
        <td>${ppmEsc(row.hearing || "—")}</td>
        <td>${ppmEsc(row.estate_real == null || row.estate_real === "" ? "—" : String(row.estate_real))}</td>
        <td>${ppmEsc(row.petition_ocr ? "Yes" : "—")}</td>
        <td>${this._fubCell(row)}</td>
      </tr>`;
    }).join("");
    this._qs("#listing-table").innerHTML = `
      <table>
        <thead>
          <tr>${heads}</tr>
          <tr class="ppm-filter-row">${filters}</tr>
        </thead>
        <tbody>${body || `<tr><td colspan="${PPM_LISTING_TABLE_COLUMNS.length}">${total ? "No matching listings." : "No collected listings yet."}</td></tr>`}</tbody>
      </table>
    `;
    this._qs("#listing-table").querySelectorAll("th.ppm-th-sort").forEach((th) => {
      th.addEventListener("click", () => this._toggleSort(th.dataset.key));
    });
    this._qs("#listing-table").querySelectorAll("[data-filter]").forEach((el) => {
      el.addEventListener("click", (ev) => ev.stopPropagation());
      const apply = () => {
        this._colFilters = { ...this._colFilters, [el.dataset.filter]: el.value || "" };
        this._renderTable();
      };
      el.addEventListener("input", apply);
      el.addEventListener("change", apply);
    });
    if (focusKey) {
      const inp = this._qs(`[data-filter="${focusKey}"]`);
      if (inp) {
        inp.focus();
        if (caret != null && inp.setSelectionRange) {
          const pos = Math.min(caret, String(inp.value || "").length);
          inp.setSelectionRange(pos, pos);
        }
      }
    }
  }

  async _load() {
    this._flash("Loading collected listings…", true);
    try {
      const data = await this._hass.callApi("GET", "placer_probate_monitor/listings");
      let origin = ppmNabuOrigin(data.document_base);
      if (!origin) origin = await ppmCloudRemoteOrigin(this._hass);
      this._documentBase = origin || "";
      this._rows = data.listings || [];
      this._share = {
        share_url: data.share_url || "",
        share_path: data.share_path || "/api/placer_probate_monitor/listings/public",
        share_token: data.share_token || "",
        share_exp: data.share_exp || "",
      };
      this._renderTable();
      this._flash(`Loaded ${this._rows.length} collected listing${this._rows.length === 1 ? "" : "s"}.`, true);
    } catch (err) {
      this._flash(ppmText(err), false);
    }
  }
}

customElements.define("placer-probate-listings-panel", PlacerProbateListingsPanel);

class HammondRealtyPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._ready = false;
    this._view = "fub";
    this._shareUrl = "";
    this._unsubJob = null;
    this._onHash = () => this._syncFromHash();
  }

  connectedCallback() {
    window.addEventListener("hashchange", this._onHash);
    this._bindJobWatch();
  }

  disconnectedCallback() {
    window.removeEventListener("hashchange", this._onHash);
    if (this._unsubJob) {
      this._unsubJob();
      this._unsubJob = null;
    }
    ppmJobWatch.stop();
  }

  set hass(hass) {
    this._hass = hass;
    ppmJobWatch.start(hass);
    if (!this._ready) {
      this._ready = true;
      this._view = ppmParseAppView(window.location.hash);
      this._renderShell();
      this._applyView();
      this._loadShareLink();
    }
    this._bindJobWatch();
    this._forwardHass();
  }

  get hass() {
    return this._hass;
  }

  _renderShell() {
    this.innerHTML = `
      <style>${PPM_CSS}</style>
      <div class="ppm-wrap">
        ${ppmAppHeaderHtml(this._view)}
        <div class="ppm-view" data-view="fub">
          <placer-probate-fub-panel></placer-probate-fub-panel>
        </div>
        <div class="ppm-view" data-view="listings" hidden>
          <placer-probate-listings-panel></placer-probate-listings-panel>
        </div>
        <div class="ppm-view" data-view="sources" hidden>
          <placer-probate-sources-panel></placer-probate-sources-panel>
        </div>
      </div>
    `;
    this.querySelectorAll("[data-ppm-view]").forEach((btn) => {
      btn.addEventListener("click", () => this._showView(btn.dataset.ppmView));
    });
    this._fillShareLink();
  }

  async _loadShareLink() {
    if (!this._hass || this._shareUrl) {
      this._fillShareLink();
      return;
    }
    try {
      const data = await this._hass.callApi("GET", "placer_probate_monitor/listings");
      this._shareUrl = ppmListingsShareUrl(this._hass, {
        share_url: data.share_url || "",
        share_path: data.share_path || "/api/placer_probate_monitor/listings/public",
        share_token: data.share_token || "",
        share_exp: data.share_exp || "",
      });
    } catch (_err) {
      this._shareUrl = "";
    }
    this._fillShareLink();
  }

  _fillShareLink() {
    const wrap = this.querySelector(".ppm-outside-link");
    const link = this.querySelector("#ppm-listings-share");
    if (!wrap || !link || !this._shareUrl) return;
    link.href = this._shareUrl;
    link.textContent = this._shareUrl;
    wrap.hidden = false;
  }

  _bindJobWatch() {
    if (this._unsubJob || !this._ready) return;
    this._unsubJob = ppmJobWatch.subscribe((st) => this._paintJobBanner(st));
    if (ppmJobWatch.last) this._paintJobBanner(ppmJobWatch.last);
  }

  _paintJobBanner(st) {
    const el = this.querySelector("#ppm-job-banner");
    if (!el) return;
    const painted = ppmJobBannerState(st);
    if (!painted.text) {
      el.className = "ppm-job-banner";
      el.textContent = "";
      return;
    }
    el.textContent = painted.text;
    el.className = "ppm-job-banner show " + painted.kind;
  }

  _forwardHass() {
    if (!this._hass) return;
    const tag = {
      fub: "placer-probate-fub-panel",
      listings: "placer-probate-listings-panel",
      sources: "placer-probate-sources-panel",
    }[this._view];
    const el = tag ? this.querySelector(tag) : null;
    if (el) el.hass = this._hass;
  }

  _showView(view) {
    this._view = ppmParseAppView(view);
    const hash = this._view === "fub" ? "#/" : `#/${this._view}`;
    if ((window.location.hash || "") !== hash && window.location.hash !== `#${this._view}`) {
      window.location.hash = hash;
    }
    this._applyView();
  }

  _syncFromHash() {
    this._view = ppmParseAppView(window.location.hash);
    this._applyView();
  }

  _applyView() {
    this.querySelectorAll("[data-ppm-view]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.ppmView === this._view);
    });
    this.querySelectorAll(".ppm-view").forEach((el) => {
      el.hidden = el.dataset.view !== this._view;
    });
    this._forwardHass();
  }
}

customElements.define("hammond-realty-panel", HammondRealtyPanel);
