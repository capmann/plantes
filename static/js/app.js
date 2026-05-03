// ── State ────────────────────────────────────────────────────────────────

let currentPlantId = null;
let currentPhotos = [];
let questionPhotoB64 = null;
let pendingPhotoB64 = null;
let aiAvailable = false;

// ── Constants ────────────────────────────────────────────────────────────

const GUIDE_SECTIONS = [
    { key: "lumiere",     icon: "☀️", label: "Lumiere" },
    { key: "arrosage",    icon: "💧", label: "Arrosage" },
    { key: "temperature", icon: "🌡️", label: "Temperature" },
    { key: "humidite",    icon: "💨", label: "Humidite" },
    { key: "substrat",    icon: "🪴", label: "Substrat" },
    { key: "engrais",     icon: "🧪", label: "Engrais" },
    { key: "rempotage",   icon: "📦", label: "Rempotage" },
    { key: "problemes",   icon: "⚠️", label: "Problemes courants", fullWidth: true },
    { key: "symbolique",  icon: "✨", label: "Symbolique", fullWidth: true },
];

const STATUS_LABELS = {
    good: "Bonne sante",
    warning: "A surveiller",
    bad: "En difficulte",
    unknown: "Inconnu",
};

// ── DOM refs ─────────────────────────────────────────────────────────────

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const viewList = $("#view-list");
const viewDetail = $("#view-detail");
const plantList = $("#plant-list");
const loading = $("#loading");
const loadingText = $("#loading-text");
const modal = $("#modal-plant");
const lightbox = $("#lightbox");

// ── API helpers ──────────────────────────────────────────────────────────

async function api(url, opts = {}) {
    const res = await fetch(url, {
        headers: { "Content-Type": "application/json", ...opts.headers },
        ...opts,
    });
    if (res.status === 204) return null;
    const text = await res.text();
    let data;
    try {
        data = JSON.parse(text);
    } catch {
        throw new Error(`Erreur serveur (${res.status})`);
    }
    if (!res.ok) throw new Error(data.error || "Erreur serveur");
    return data;
}

function showLoading(text = "") {
    loadingText.textContent = text;
    loading.style.display = "flex";
}
function hideLoading() { loading.style.display = "none"; }

// ── Format dates ─────────────────────────────────────────────────────────

function timeAgo(dateStr) {
    if (!dateStr) return "Jamais";
    const date = new Date(dateStr.replace(" ", "T"));
    const now = new Date();
    const diffMs = now - date;
    const mins = Math.floor(diffMs / 60000);
    const hours = Math.floor(diffMs / 3600000);
    const days = Math.floor(diffMs / 86400000);

    if (mins < 1) return "A l'instant";
    if (mins < 60) return `Il y a ${mins} min`;
    if (hours < 24) return `Il y a ${hours}h`;
    if (days < 7) return `Il y a ${days}j`;
    return date.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}

function formatDate(dateStr) {
    if (!dateStr) return "";
    const date = new Date(dateStr.replace(" ", "T"));
    return date.toLocaleDateString("fr-FR", {
        day: "numeric", month: "long", year: "numeric",
        hour: "2-digit", minute: "2-digit",
    });
}

// ── Helpers ──────────────────────────────────────────────────────────────

function esc(str) {
    const div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
}

function fileToBase64(file) {
    return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.readAsDataURL(file);
    });
}

function parseGuide(careGuide) {
    if (!careGuide) return null;
    try {
        const parsed = JSON.parse(careGuide);
        if (typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
    } catch { /* not JSON, return null */ }
    return null;
}

// ── Navigation ───────────────────────────────────────────────────────────

function showView(view) {
    $$(".view").forEach((v) => v.classList.remove("active"));
    view.classList.add("active");
    if (view === viewList) window.scrollTo(0, 0);
}

// ── Plant List ───────────────────────────────────────────────────────────

async function loadPlants() {
    const plants = await api("/api/plants");
    if (plants.length === 0) {
        plantList.innerHTML = `
            <div class="empty-state">
                <div class="icon">📷</div>
                <p>Prends une photo d'une plante<br>pour commencer !</p>
            </div>`;
        return;
    }
    plantList.innerHTML = plants.map((p) => `
        <div class="plant-card" data-id="${p.id}">
            ${p.last_photo
                ? `<img class="plant-card-img" src="/uploads/${p.last_photo}" alt="${esc(p.name)}" loading="lazy">`
                : `<div class="plant-card-img placeholder">🌿</div>`
            }
            <div class="plant-card-body">
                <div class="plant-card-name">${esc(p.name)}</div>
                ${p.species ? `<div class="plant-card-species">${esc(p.species)}</div>` : ""}
                <div class="plant-card-watered">💧 ${timeAgo(p.last_watered)}</div>
            </div>
        </div>
    `).join("");
}

// ── Add plant flow ───────────────────────────────────────────────────────

async function handleNewPlantPhoto(file) {
    const b64 = await fileToBase64(file);
    pendingPhotoB64 = b64;

    if (!aiAvailable) {
        modal.classList.add("active");
        setTimeout(() => $("#input-name").focus(), 100);
        return;
    }

    showLoading("Identification en cours...");
    try {
        const plant = await api("/api/plants/identify", {
            method: "POST",
            body: JSON.stringify({ photo_base64: b64 }),
        });
        hideLoading();
        await loadPlants();
        openPlant(plant.id);
    } catch (e) {
        hideLoading();
        alert("Erreur d'identification : " + e.message);
    }
}

async function saveManualPlant() {
    const name = $("#input-name").value.trim();
    if (!name) { alert("Le nom est requis"); return; }

    showLoading();
    try {
        const plant = await api("/api/plants", {
            method: "POST",
            body: JSON.stringify({ name, species: $("#input-species").value.trim() }),
        });
        if (pendingPhotoB64) {
            await api(`/api/plants/${plant.id}/photos`, {
                method: "POST",
                body: JSON.stringify({ photo_base64: pendingPhotoB64 }),
            });
            pendingPhotoB64 = null;
        }
        closeModal();
        await loadPlants();
        openPlant(plant.id);
    } catch (e) {
        alert(e.message);
    } finally { hideLoading(); }
}

function closeModal() {
    modal.classList.remove("active");
    $("#input-name").value = "";
    $("#input-species").value = "";
}

// ── Plant Detail ─────────────────────────────────────────────────────────

async function openPlant(id) {
    currentPlantId = id;
    showView(viewDetail);

    const plant = await api(`/api/plants/${id}`);
    $("#detail-title").textContent = plant.name;
    $("#species-line").textContent = plant.species || "";

    // Guide
    renderGuide(plant.care_guide);

    // AI
    $("#ai-unavailable").style.display = aiAvailable ? "none" : "block";
    $("#ask-form").style.display = aiAvailable ? "block" : "none";
    $("#checkup-btn-label").style.display = aiAvailable ? "flex" : "none";

    loadPhotos(id);
    loadWaterings(id);
    loadRepottings(id);
    loadConversations(id);
    loadCheckups(id);
}

// ── Guide rendering ──────────────────────────────────────────────────────

function renderGuide(careGuide) {
    const container = $("#guide-display");
    const editBtn = $("#btn-edit-guide");
    const guide = parseGuide(careGuide);

    if (!guide) {
        // Legacy plain text or empty
        if (careGuide && careGuide.trim()) {
            container.innerHTML = `<div class="guide-card full-width" style="grid-column:1/-1"><div class="guide-card-text">${esc(careGuide)}</div></div>`;
            editBtn.style.display = "";
        } else {
            container.innerHTML = `<div class="guide-empty">Aucun guide d'entretien pour l'instant.</div>`;
            editBtn.style.display = "none";
        }
        return;
    }

    editBtn.style.display = "";
    container.innerHTML = GUIDE_SECTIONS.map((s) => {
        const text = guide[s.key];
        if (!text) return "";
        return `
            <div class="guide-card${s.fullWidth ? ' full-width' : ''}${s.key === 'symbolique' ? ' symbolique' : ''}">
                <div class="guide-card-header">
                    <span class="guide-card-icon">${s.icon}</span>
                    <span class="guide-card-title">${s.label}</span>
                </div>
                <div class="guide-card-text">${esc(text)}</div>
            </div>`;
    }).join("");
}

function showGuideEditor() {
    const editor = $("#guide-editor");
    const plant_guide = parseGuide($("#guide-display").dataset.raw || "{}") || {};

    // Try to get current guide from DOM
    let currentGuide = {};
    // Re-fetch from API is cleaner
    api(`/api/plants/${currentPlantId}`).then((plant) => {
        currentGuide = parseGuide(plant.care_guide) || {};
        editor.innerHTML = GUIDE_SECTIONS.map((s) => `
            <div class="guide-editor-field">
                <label>${s.icon} ${s.label}</label>
                <textarea data-key="${s.key}" rows="3">${esc(currentGuide[s.key] || "")}</textarea>
            </div>
        `).join("") + `
            <div class="guide-editor-actions">
                <button id="btn-cancel-guide" class="btn-secondary">Annuler</button>
                <button id="btn-save-guide" class="btn-primary">Sauvegarder</button>
            </div>`;

        editor.style.display = "flex";
        $("#btn-edit-guide").style.display = "none";
        $("#guide-display").style.display = "none";

        $("#btn-cancel-guide").addEventListener("click", hideGuideEditor);
        $("#btn-save-guide").addEventListener("click", saveGuide);
    });
}

function hideGuideEditor() {
    $("#guide-editor").style.display = "none";
    $("#btn-edit-guide").style.display = "";
    $("#guide-display").style.display = "";
}

async function saveGuide() {
    showLoading();
    try {
        const guide = {};
        $$("#guide-editor textarea[data-key]").forEach((ta) => {
            if (ta.value.trim()) guide[ta.dataset.key] = ta.value.trim();
        });
        const careGuide = JSON.stringify(guide, null, 2);
        await api(`/api/plants/${currentPlantId}`, {
            method: "PUT",
            body: JSON.stringify({ care_guide: careGuide }),
        });
        renderGuide(careGuide);
        hideGuideEditor();
    } finally { hideLoading(); }
}

// ── Photos ───────────────────────────────────────────────────────────────

async function loadPhotos(pid) {
    currentPhotos = await api(`/api/plants/${pid}/photos`);
    const hero = $("#hero-photo");
    const strip = $("#photo-strip");

    if (currentPhotos.length === 0) {
        hero.innerHTML = `<div class="placeholder-hero">🌿</div>`;
        strip.innerHTML = "";
        return;
    }

    hero.innerHTML = `<img src="/uploads/${currentPhotos[0].filename}" alt="Photo" data-full="/uploads/${currentPhotos[0].filename}">`;
    strip.innerHTML = currentPhotos.map((p, i) => `
        <img src="/uploads/${p.filename}" alt="Photo"
             data-full="/uploads/${p.filename}"
             data-index="${i}"
             class="${i === 0 ? 'active' : ''}">
    `).join("");
}

function setHeroPhoto(filename, activeIndex) {
    $("#hero-photo").innerHTML = `<img src="/uploads/${filename}" alt="Photo" data-full="/uploads/${filename}">`;
    $$("#photo-strip img").forEach((img, i) => {
        img.classList.toggle("active", i === activeIndex);
    });
}

async function uploadPlantPhoto(file) {
    const formData = new FormData();
    formData.append("photo", file);
    showLoading("Ajout de la photo...");
    try {
        await fetch(`/api/plants/${currentPlantId}/photos`, { method: "POST", body: formData });
        await loadPhotos(currentPlantId);
        await loadPlants();
    } finally { hideLoading(); }
}

// ── Waterings ────────────────────────────────────────────────────────────

async function loadWaterings(pid) {
    const waterings = await api(`/api/plants/${pid}/waterings`);
    const info = $("#last-watered");
    const history = $("#watering-history");

    if (waterings.length === 0) {
        info.innerHTML = "Aucun arrosage enregistre";
        history.innerHTML = "";
        return;
    }
    info.innerHTML = `Dernier arrosage : <strong>${timeAgo(waterings[0].watered_at)}</strong>`;
    history.innerHTML = waterings.slice(0, 10).map((w) =>
        `<li>${formatDate(w.watered_at)}${w.notes ? ` — ${esc(w.notes)}` : ""}</li>`
    ).join("");
}

async function addWatering() {
    showLoading();
    try {
        await api(`/api/plants/${currentPlantId}/waterings`, { method: "POST", body: "{}" });
        await loadWaterings(currentPlantId);
        await loadPlants();
    } finally { hideLoading(); }
}

// ── Repottings ───────────────────────────────────────────────────────────

async function loadRepottings(pid) {
    const repottings = await api(`/api/plants/${pid}/repottings`);
    const info = $("#last-repotted");
    const history = $("#repotting-history");

    if (repottings.length === 0) {
        info.innerHTML = "Aucun rempotage enregistre";
        history.innerHTML = "";
        return;
    }
    info.innerHTML = `Dernier rempotage : <strong>${timeAgo(repottings[0].repotted_at)}</strong>`;
    history.innerHTML = repottings.slice(0, 10).map((r) =>
        `<li>${formatDate(r.repotted_at)}${r.notes ? ` — ${esc(r.notes)}` : ""}</li>`
    ).join("");
}

async function addRepotting() {
    showLoading();
    try {
        await api(`/api/plants/${currentPlantId}/repottings`, { method: "POST", body: "{}" });
        await loadRepottings(currentPlantId);
    } finally { hideLoading(); }
}

// ── Checkups ─────────────────────────────────────────────────────────────

function renderCheckupCard(c, expanded = true) {
    const statusLabel = STATUS_LABELS[c.status] || STATUS_LABELS.unknown;
    return `
        <div class="checkup-card">
            <div class="checkup-header">
                <span class="checkup-status-badge ${c.status}">${statusLabel}</span>
                <span class="checkup-date">${formatDate(c.checked_at)}</span>
            </div>
            <div class="checkup-body">
                <div class="checkup-photo-row">
                    <img src="/uploads/${c.photo_filename}" alt="Bilan">
                </div>
                <div class="checkup-summary">${esc(c.summary)}</div>
                ${expanded ? `
                    <div class="checkup-label">Observations</div>
                    <div class="checkup-details">${esc(c.details)}</div>
                    ${c.comparison ? `
                        <div class="checkup-label">Evolution</div>
                        <div class="checkup-comparison">${esc(c.comparison)}</div>
                    ` : ""}
                    <div class="checkup-label">Recommandations</div>
                    <div class="checkup-recs">${esc(c.recommendations)}</div>
                ` : ""}
            </div>
        </div>`;
}

async function loadCheckups(pid) {
    const checkups = await api(`/api/plants/${pid}/checkups`);
    const latest = $("#checkup-latest");
    const historyWrapper = $("#checkup-history-wrapper");
    const history = $("#checkup-history");

    if (checkups.length === 0) {
        latest.innerHTML = `<p style="color:var(--text-lighter);text-align:center;padding:8px;font-size:0.88rem">Aucun bilan de sante pour l'instant. Prends une photo !</p>`;
        historyWrapper.style.display = "none";
        return;
    }

    // Show latest checkup expanded
    latest.innerHTML = renderCheckupCard(checkups[0], true);

    // History (older checkups)
    if (checkups.length > 1) {
        historyWrapper.style.display = "block";
        history.innerHTML = checkups.slice(1).map((c) => renderCheckupCard(c, false)).join("");
    } else {
        historyWrapper.style.display = "none";
    }
}

async function doCheckup(file) {
    const b64 = await fileToBase64(file);
    showLoading("Analyse en cours...");
    try {
        await api(`/api/plants/${currentPlantId}/checkup`, {
            method: "POST",
            body: JSON.stringify({ photo_base64: b64 }),
        });
        // Also save photo to the plant's gallery
        await api(`/api/plants/${currentPlantId}/photos`, {
            method: "POST",
            body: JSON.stringify({ photo_base64: b64 }),
        });
        await loadCheckups(currentPlantId);
        await loadPhotos(currentPlantId);
    } catch (e) {
        alert("Erreur : " + e.message);
    } finally { hideLoading(); }
}

// ── Questions / AI ───────────────────────────────────────────────────────

async function loadConversations(pid) {
    const convs = await api(`/api/plants/${pid}/conversations`);
    const container = $("#conversations");
    if (convs.length === 0) {
        container.innerHTML = `<p style="color:var(--text-lighter);text-align:center;padding:16px">Aucune question posee</p>`;
        return;
    }
    container.innerHTML = convs.map((c) => `
        <div class="conv-item">
            <div class="conv-question">
                ${c.photo_filename ? `<img src="/uploads/${c.photo_filename}" alt="Photo">` : ""}
                <span>${esc(c.question)}</span>
            </div>
            <div class="conv-answer">${esc(c.answer)}</div>
            <div class="conv-date">${formatDate(c.asked_at)}</div>
        </div>
    `).join("");
}

async function askQuestion() {
    const input = $("#question-input");
    const question = input.value.trim();
    if (!question) return;

    showLoading("Reflexion en cours...");
    try {
        const body = { question };
        if (questionPhotoB64) body.photo_base64 = questionPhotoB64;

        await api(`/api/plants/${currentPlantId}/ask`, {
            method: "POST",
            body: JSON.stringify(body),
        });

        input.value = "";
        questionPhotoB64 = null;
        $("#question-photo-preview").innerHTML = "";
        await loadConversations(currentPlantId);
    } catch (e) {
        alert(e.message);
    } finally { hideLoading(); }
}

// ── Delete plant ─────────────────────────────────────────────────────────

async function deletePlant() {
    if (!confirm("Supprimer cette plante et toutes ses donnees ?")) return;
    showLoading();
    try {
        await api(`/api/plants/${currentPlantId}`, { method: "DELETE" });
        currentPlantId = null;
        showView(viewList);
        await loadPlants();
    } finally { hideLoading(); }
}

// ── Event listeners ──────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
    try {
        const status = await api("/api/ai-status");
        aiAvailable = status.available;
    } catch { aiAvailable = false; }

    await loadPlants();

    // ── List view ──
    plantList.addEventListener("click", (e) => {
        const card = e.target.closest(".plant-card");
        if (card) openPlant(Number(card.dataset.id));
    });

    $("#fab-photo-input").addEventListener("change", (e) => {
        if (e.target.files[0]) handleNewPlantPhoto(e.target.files[0]);
        e.target.value = "";
    });

    // ── Detail view ──
    $("#btn-back").addEventListener("click", async () => {
        showView(viewList);
        await loadPlants();
    });

    $("#btn-delete-plant").addEventListener("click", deletePlant);

    // Hero photo → lightbox
    $("#hero-photo").addEventListener("click", (e) => {
        const img = e.target.closest("img[data-full]");
        if (img) {
            $("#lightbox-img").src = img.dataset.full;
            lightbox.style.display = "flex";
        }
    });

    // Photo strip click → change hero
    $("#photo-strip").addEventListener("click", (e) => {
        const img = e.target.closest("img");
        if (img) {
            setHeroPhoto(img.dataset.full.replace("/uploads/", ""), Number(img.dataset.index));
        }
    });

    // Add photo
    $("#add-photo-input").addEventListener("change", (e) => {
        if (e.target.files[0]) uploadPlantPhoto(e.target.files[0]);
        e.target.value = "";
    });

    // Watering
    $("#btn-water").addEventListener("click", addWatering);

    // Repotting
    $("#btn-repot").addEventListener("click", addRepotting);

    // Guide
    $("#btn-edit-guide").addEventListener("click", showGuideEditor);

    // Checkup
    $("#checkup-photo-input").addEventListener("change", (e) => {
        if (e.target.files[0]) doCheckup(e.target.files[0]);
        e.target.value = "";
    });

    $("#btn-toggle-checkup-history").addEventListener("click", () => {
        const h = $("#checkup-history");
        const btn = $("#btn-toggle-checkup-history");
        if (h.style.display === "none") {
            h.style.display = "block";
            btn.textContent = "Masquer l'historique";
        } else {
            h.style.display = "none";
            btn.textContent = "Voir l'historique des bilans";
        }
    });

    // Question photo
    $("#question-photo-input").addEventListener("change", async (e) => {
        if (e.target.files[0]) {
            questionPhotoB64 = await fileToBase64(e.target.files[0]);
            $("#question-photo-preview").innerHTML = `<img src="${questionPhotoB64}" alt="preview">`;
        }
        e.target.value = "";
    });

    // Ask question
    $("#btn-ask").addEventListener("click", askQuestion);

    // ── Modal ──
    $("#btn-cancel-modal").addEventListener("click", closeModal);
    $("#btn-save-plant").addEventListener("click", saveManualPlant);
    modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });
    modal.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); saveManualPlant(); }
    });

    // ── Lightbox ──
    $("#lightbox-close").addEventListener("click", () => { lightbox.style.display = "none"; });
    lightbox.addEventListener("click", (e) => { if (e.target === lightbox) lightbox.style.display = "none"; });
});
