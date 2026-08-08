// MiniMax H3 Location Scout Plus
// Collect location/set references and pass their ordered visual context downstream.

const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;

const MAX_LOCATION_ITEMS = 18;
const MAX_CHARACTERS = 9;
const MAX_REFERENCE_IMAGES = 9;

const emptyItem = () => ({ images: [], description: "" });

function emptySets() {
  return { version: 1, items: Array.from({ length: MAX_LOCATION_ITEMS }, emptyItem) };
}

function parseSets(value) {
  let parsed = null;
  try { parsed = typeof value === "string" ? JSON.parse(value) : value; } catch (_) { }
  const rawItems = Array.isArray(parsed?.items) ? parsed.items
    : (Array.isArray(parsed?.location_items) ? parsed.location_items : []);
  const result = emptySets();
  result.items = rawItems.slice(0, MAX_LOCATION_ITEMS).map((item) => ({
    images: Array.isArray(item?.images) ? item.images.slice(0, 1)
      : (item?.image ? [item.image] : []),
    description: String(item?.description || ""),
  }));
  while (result.items.length < MAX_LOCATION_ITEMS) result.items.push(emptyItem());
  return result;
}

function readJson(value) {
  try { return value ? JSON.parse(value) : {}; } catch (_) { return {}; }
}

function linkedSourceForInput(node, inputName) {
  const input = node.inputs?.find((item) => item.name === inputName);
  const link = input?.link != null ? app.graph?.links?.[input.link] : null;
  return link ? app.graph?.getNodeById(link.origin_id) : null;
}

function castSourceFor(node) {
  const direct = linkedSourceForInput(node, "cast_wardrobe");
  if (direct) return direct;
  const legacyInput = node.inputs?.find((item) => item.name === "sets_data");
  const legacyLink = legacyInput?.link != null ? app.graph?.links?.[legacyInput.link] : null;
  const legacySource = legacyLink ? app.graph?.getNodeById(legacyLink.origin_id) : null;
  const type = String(legacySource?.comfyClass || legacySource?.type || "").toLowerCase();
  return type.includes("wardrobe") || type.includes("casting") ? legacySource : null;
}

function migrateLegacyCastLink(node) {
  const castInput = node.inputs?.find((item) => item.name === "cast_wardrobe");
  const legacyInput = node.inputs?.find((item) => item.name === "sets_data");
  if (!castInput || castInput.link != null || legacyInput?.link == null) return false;
  const linkId = legacyInput.link;
  const link = app.graph?.links?.[linkId];
  const source = link ? app.graph?.getNodeById(link.origin_id) : null;
  const type = String(source?.comfyClass || source?.type || "").toLowerCase();
  if (!type.includes("wardrobe") && !type.includes("casting")) return false;
  legacyInput.link = null;
  castInput.link = linkId;
  link.target_slot = node.inputs.indexOf(castInput);
  node.properties = { ...(node.properties || {}), legacy_cast_link_migrated: true };
  node.setDirtyCanvas?.(true, true);
  app.graph?.setDirtyCanvas?.(true, true);
  console.info("[MiniMaxLocationScout] Moved legacy Wardrobe link to cast_wardrobe input.");
  return true;
}

async function fetchProjects() {
  const response = await api.fetchApi("/minimax_director/projects");
  const result = await response.json();
  if (result.status !== "success") throw new Error(result.message || "Could not list projects");
  return Array.isArray(result.projects) ? result.projects : [];
}

async function loadProject(name, path = "") {
  const query = `name=${encodeURIComponent(name)}${path ? `&path=${encodeURIComponent(path)}` : ""}`;
  const response = await api.fetchApi(`/minimax_director/projects/load?${query}`);
  const result = await response.json();
  if (result.status !== "success") throw new Error(result.message || "Could not load project");
  return result.project || {};
}

async function saveProjectSource(project, source, data, folder = "wardrobe", path = "") {
  const response = await api.fetchApi("/minimax_director/projects/save", {
    method: "POST", body: JSON.stringify({ project, source, folder, data, path }),
  });
  const result = await response.json();
  if (result.status !== "success") throw new Error(result.message || "Could not save project");
  return result.project || {};
}

function sourceCastFor(node) {
  try {
    const input = node.inputs?.find((item) => item.name === "cast_wardrobe");
    const source = castSourceFor(node);
    const raw = source?.properties?.cast_wardrobe_output
      || source?.properties?.cast_data || input?.value || "";
    const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!parsed || !Array.isArray(parsed.characters)) return null;
    return { ...parsed,
      characters: parsed.characters.filter((character) => character?.hired !== false) };
  } catch (_) { return null; }
}

function sourceAnalyzeSettingsFor(node) {
  try {
    const input = node.inputs?.find((item) => item.name === "analyze_settings");
    const link = input?.link != null ? app.graph?.links?.[input.link] : null;
    const source = link ? app.graph?.getNodeById(link.origin_id) : null;
    if (!source) return null;
    // Read the live Casting Director state first; the cached settings output can be
    // stale while the user is editing the analysis controls.
    const castWidget = source?.widgets?.find((item) => item.name === "cast_data");
    const raw = castWidget?.value || source?.properties?.cast_data
      || source?.properties?.analyze_settings_output || input?.value || "";
    const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!parsed || typeof parsed !== "object") return null;
    return {
      provider: String(parsed.provider || parsed.analyzeProvider || "ollama").toLowerCase(),
      base_url: String(parsed.base_url || parsed.analyzeBaseUrl || ""),
      model: String(parsed.model || parsed.analyzeModel || ""),
      api_key: String(parsed.api_key || parsed.analyzeApiKey || ""),
    };
  } catch (_) { return null; }
}

function imageSrc(image) {
  if (!image) return "";
  if (image.b64) return image.b64;
  if (!image.name) return "";
  const parts = image.name.split("/");
  const filename = parts.pop();
  return api.apiURL(`/view?filename=${encodeURIComponent(filename)}&type=input&subfolder=${encodeURIComponent(parts.join("/"))}`);
}

function inputFileForImage(onFile) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (file) onFile(file);
  });
  input.click();
}

function referenceBaseFor(cast) {
  if (!cast || !Array.isArray(cast.characters)) return 0;
  let count = cast.characters.slice(0, MAX_CHARACTERS)
    .filter((character) => character?.hired !== false)
    .reduce((total, character) => total + (Array.isArray(character.images) ? character.images.length : 0), 0);
  const collages = Array.isArray(cast.wardrobe_collages) ? cast.wardrobe_collages : [];
  if (collages.length) {
    count += collages.filter((item) => Array.isArray(item?.images) && item.images.length).length;
  } else {
    const items = Array.isArray(cast.wardrobe_items) ? cast.wardrobe_items : [];
    count += items.filter((item) => Array.isArray(item?.images) && item.images.length).length;
  }
  return Math.min(MAX_REFERENCE_IMAGES, count);
}

const LOCATION_STYLES = `
  .mmxd-location-wrapper { width:100%; box-sizing:border-box; color:#d8d8d8; font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
  .mmxd-location-head { display:flex; align-items:center; gap:8px; margin:0 0 6px; }
  .mmxd-location-title { color:#888; font-size:10px; font-weight:700; letter-spacing:.7px; }
  .mmxd-location-help { color:#666; font-size:9px; flex:1; }
  .mmxd-location-projects { display:flex; align-items:center; gap:4px; flex-wrap:wrap; margin:0 0 7px; }
  .mmxd-location-projects label { color:#777; font-size:8px; text-transform:uppercase; letter-spacing:.35px; }
  .mmxd-location-project-select, .mmxd-location-project-name { box-sizing:border-box; min-width:0; height:23px; padding:2px 5px; background:#111; color:#d8d8d8; border:1px solid #3a3a3a; border-radius:4px; font-size:9px; font-family:inherit; outline:none; }
  .mmxd-location-project-select { flex:1 1 150px; }
  .mmxd-location-project-name { flex:1 1 130px; }
  .mmxd-location-project-button { height:23px; padding:2px 7px; background:#252525; color:#bdbdbd; border:1px solid #444; border-radius:4px; font-size:8px; font-weight:700; cursor:pointer; }
  .mmxd-location-project-button:hover { color:#fff; border-color:#777; }
  .mmxd-location-status { color:#666; font-size:9px; margin:0 0 7px; }
  .mmxd-location-items { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; width:100%; height:680px; max-height:680px; overflow-y:auto; overflow-x:hidden; align-content:start; padding-right:5px; box-sizing:border-box; }
  .mmxd-location-item { min-width:0; height:220px; box-sizing:border-box; background:#1e1e1e; border:1.5px dashed #444; border-radius:7px; padding:5px; position:relative; overflow:hidden; }
  .mmxd-location-item:hover { border-color:#666; background:#252525; }
  .mmxd-location-item.drag-over { border-color:#4fff8f; background:rgba(79,255,143,.05); }
  .mmxd-location-item-head { display:flex; align-items:center; justify-content:space-between; height:16px; }
  .mmxd-location-item-label { color:#888; font-size:9px; font-weight:700; letter-spacing:.4px; }
  .mmxd-location-tag { color:#4fff8f; font-size:9px; font-weight:700; margin-left:4px; }
  .mmxd-location-remove, .mmxd-location-analyze { background:#252525; border-radius:3px; padding:1px 5px; font-size:8px; font-weight:700; cursor:pointer; }
  .mmxd-location-remove { color:#b66; border:1px solid #533; }
  .mmxd-location-analyze { color:#8fd8aa; border:1px solid #365844; }
  .mmxd-location-analyze.loading { color:#888; border-color:#444; cursor:wait; pointer-events:none; }
  .mmxd-location-preview-wrap { width:100%; height:96px; margin-top:4px; position:relative; border-radius:3px; background:#111; overflow:hidden; cursor:pointer; }
  .mmxd-location-preview { width:100%; height:100%; object-fit:contain; pointer-events:none; }
  .mmxd-location-drop { color:#666; text-align:center; font-size:9px; line-height:96px; cursor:pointer; }
  .mmxd-location-delete-image { position:absolute; top:2px; right:2px; width:15px; height:15px; padding:0; border:0; border-radius:50%; background:rgba(0,0,0,.85); color:#ff5555; cursor:pointer; }
  .mmxd-location-field-label { display:block; color:#777; font-size:8px; line-height:10px; margin-top:5px; text-transform:uppercase; letter-spacing:.35px; }
  .mmxd-location-description { width:100%; height:56px; box-sizing:border-box; padding:3px 4px; resize:none; outline:none; background:#111; color:#e0e0e0; border:1px solid #333; border-radius:4px; font-family:inherit; font-size:9px; }
  .mmxd-location-description:focus { border-color:#4fff8f; }
`;

let styleEl = document.getElementById("minimax-h3-location-plus-styles");
if (!styleEl) {
  styleEl = document.createElement("style");
  styleEl.id = "minimax-h3-location-plus-styles";
  document.head.appendChild(styleEl);
}
styleEl.textContent = LOCATION_STYLES;

app.registerExtension({
  name: "MiniMaxH3LocationScoutPlusCS",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "MiniMaxH3LocationScoutPlusCS") return;

    const originalCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      originalCreated?.apply(this, arguments);
      const node = this;
      const castInput = node.inputs?.find((input) => input.name === "cast_wardrobe");
      const settingsInput = node.inputs?.find((input) => input.name === "analyze_settings");
      const setsWidget = node.widgets?.find((widget) => widget.name === "sets_data");
      for (const input of [castInput, settingsInput]) {
        if (input) { input.hidden = false; input.options = { ...(input.options || {}), hidden: false }; }
      }
      if (setsWidget) {
        setsWidget.hidden = true;
        setsWidget.options = { ...(setsWidget.options || {}), hidden: true };
        setsWidget.computeSize = () => [0, -4];
      }

      const container = document.createElement("div");
      container.className = "mmxd-location-wrapper";
      const uiWidget = node.addDOMWidget("location_ui", "location_ui", container, {
        getValue: () => "", setValue: () => {},
      });
      uiWidget.serialize = false;
      uiWidget.computeSize = (width) => [Math.max(10, width || node.size?.[0] || 760), 820];

      let sets = parseSets(setsWidget?.value || node.properties?.sets_data || "");
      let projects = [];
      let selectedProject = String(node.properties?.project_name || "");
      let projectSelect = null;
      let projectNameInput = null;
      let status = null;
      let projectStatus = null;
      let saveProjectButton = null;
      let itemsContainer = null;

      const setStatus = (message, error = false) => {
        if (status) { status.textContent = message || ""; status.style.color = error ? "#d86f6f" : "#666"; }
      };

      const renderProjectOptions = () => {
        if (!projectSelect) return;
        projectSelect.innerHTML = "";
        const blank = document.createElement("option"); blank.value = ""; blank.textContent = "Select project...";
        projectSelect.appendChild(blank);
        projects.forEach((project) => {
          const option = document.createElement("option"); option.value = project.name; option.textContent = project.name;
          projectSelect.appendChild(option);
        });
        projectSelect.value = selectedProject;
        if (projectNameInput && selectedProject) projectNameInput.value = selectedProject;
      };

      const refreshProjects = async () => {
        try { projects = await fetchProjects(); renderProjectOptions(); }
        catch (error) { setStatus(error.message || String(error), true); }
      };

      const imageDataUrl = async (image) => {
        const src = imageSrc(image);
        if (!src) return null;
        if (src.startsWith("data:")) return src;
        try {
          const response = await fetch(src); const blob = await response.blob();
          return await new Promise((resolve) => { const reader = new FileReader(); reader.onloadend = () => resolve(reader.result); reader.readAsDataURL(blob); });
        } catch (_) { return null; }
      };

      const uploadImage = (file, index) => {
        if (!file?.type?.startsWith("image/")) return;
        const reader = new FileReader();
        reader.onload = (event) => {
          const source = new Image();
          source.onload = async () => {
            const maxDim = 1920; let width = source.width; let height = source.height;
            if (width > maxDim || height > maxDim) {
              if (width > height) { height = Math.round(height * maxDim / width); width = maxDim; }
              else { width = Math.round(width * maxDim / height); height = maxDim; }
            }
            const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height;
            canvas.getContext("2d").drawImage(source, 0, 0, width, height);
            let stored = null;
            try {
              const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", .95));
              const base = (file.name || "location").replace(/\.[^.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_");
              const body = new FormData(); body.append("image", new File([blob], `mmxlocation_${base}_${Date.now()}.jpg`, { type: "image/jpeg" })); body.append("subfolder", "whatdreamscost");
              const response = await api.fetchApi("/upload/image", { method: "POST", body });
              if (response.status === 200) { const data = await response.json(); stored = { name: data.subfolder ? `${data.subfolder}/${data.name}` : data.name }; }
            } catch (error) { console.warn("[MiniMaxLocationScout] reference upload failed", error); }
            sets.items[index].images = [stored || { b64: canvas.toDataURL("image/jpeg", .95), name: file.name }];
            renderItems(); save();
          };
          source.src = event.target.result;
        };
        reader.readAsDataURL(file);
      };

      const analyzeItem = async (index, button) => {
        const settings = sourceAnalyzeSettingsFor(node);
        if (!settings || settings.provider === "off") { alert("Connect ANALYZE SETTINGS to analyze locations."); return; }
        const imageB64 = await imageDataUrl(sets.items[index]?.images?.[0]);
        if (!imageB64) { alert("No readable location image is available for analysis."); return; }
        button.classList.add("loading"); button.textContent = "...";
        const body = { image_b64: [imageB64], item_index: index, provider: settings.provider, base_url: settings.base_url, model: settings.model };
        if (settings.api_key && (settings.provider === "lmstudio" || settings.provider === "custom")) body.api_key = settings.api_key;
        try {
          const response = await api.fetchApi("/minimax_director/analyze_location", { method: "POST", body: JSON.stringify(body) });
          const result = await response.json();
          if (result.status !== "success") throw new Error(result.message || "Analysis failed");
          sets.items[index].description = String(result.description || "").trim(); renderItems(); save();
        } catch (error) { alert("Location Analysis Error: " + (error.message || error)); button.classList.remove("loading"); button.textContent = "ANALYZE"; }
      };

      let projectSaveTimer = null;
      const connectedProjectConfig = () => {
        const input = node.inputs?.find((item) => item.name === "project");
        const link = input?.link != null ? app.graph?.links?.[input.link] : null;
        const projectNode = link ? app.graph?.getNodeById(link.origin_id) : null;
        const project = String(projectNode?.properties?.project_name || node.properties?.project_name || "").trim();
        const projectsPath = String(projectNode?.properties?.projects_path || projectNode?.properties?.project_root
          || node.properties?.projects_path || node.properties?.project_root || "").trim();
        const path = projectsPath ? "" : String(projectNode?.properties?.project_path
          || node.properties?.project_path || "").trim();
        return { project, path, projectsPath };
      };
      const queueProjectSave = (serialized) => {
        const { project, path, projectsPath } = connectedProjectConfig();
        if (!project || (!path && !projectsPath)) return;
        clearTimeout(projectSaveTimer);
        projectSaveTimer = setTimeout(async () => {
          try {
            await api.fetchApi("/minimax_director/projects/save", {
              method: "POST",
              body: JSON.stringify({ project, source: "sets", folder: "Sets", path,
                projects_path: projectsPath, data: { sets_data: serialized, items: sets.items } }),
            });
          } catch (error) { console.warn("[MiniMaxLocationScout] project save failed", error); }
        }, 500);
      };

      const saveToProjectNow = async () => {
        const { project, path, projectsPath } = connectedProjectConfig();
        if (!project || (!path && !projectsPath)) {
          if (projectStatus) { projectStatus.textContent = "Connect and configure a Director Project node first."; projectStatus.style.color = "#d86f6f"; }
          return;
        }
        if (saveProjectButton) saveProjectButton.disabled = true;
        try {
          const serialized = JSON.stringify(sets);
          const response = await api.fetchApi("/minimax_director/projects/save", {
            method: "POST",
            body: JSON.stringify({ project, source: "sets", folder: "Sets", path,
              projects_path: projectsPath, data: { sets_data: serialized, items: sets.items } }),
          });
          const result = await response.json();
          if (!response.ok || result.status !== "success") throw new Error(result.message || "Could not save project");
          if (projectStatus) { projectStatus.textContent = `Saved to ${result.project?.project_path || `${projectsPath}/${project}`}/Sets.`; projectStatus.style.color = "#666"; }
        } catch (error) {
          if (projectStatus) { projectStatus.textContent = error.message || String(error); projectStatus.style.color = "#d86f6f"; }
        } finally {
          if (saveProjectButton) saveProjectButton.disabled = false;
        }
      };

      const save = () => {
        const serialized = JSON.stringify(sets);
        if (setsWidget) { setsWidget.value = serialized; if (setsWidget.element) setsWidget.element.value = serialized; }
        node.properties = { ...(node.properties || {}), sets_data: serialized };
        queueProjectSave(serialized);
        node.setDirtyCanvas?.(true, true); app.graph?.setDirtyCanvas?.(true, true);
      };

      const saveProjectSnapshot = async () => {
        const project = String(projectNameInput?.value || selectedProject || "").trim();
        if (!project) { setStatus("Enter a project name first.", true); projectNameInput?.focus(); return; }
        selectedProject = project; node.properties = { ...(node.properties || {}), project_name: project };
        try {
          const document = await saveProjectSource(project, "sets", {
            sets_data: sets, cast_wardrobe: sourceCastFor(node), analyze_settings: sourceAnalyzeSettingsFor(node),
           }, "sets", node.properties?.project_path || "");
          projects = await fetchProjects(); renderProjectOptions(); setStatus(`Saved ${document.project_name}/sets.`);
        } catch (error) { setStatus(error.message || String(error), true); }
      };

      const loadSelectedProject = async () => {
        const project = String(projectSelect?.value || projectNameInput?.value || "").trim();
        if (!project) return;
        try {
          const document = await loadProject(project); const saved = document?.sources?.sets?.sets_data;
          if (saved) { sets = parseSets(saved); save(); renderItems(); }
          selectedProject = project; node.properties = { ...(node.properties || {}), project_name: project };
          if (projectNameInput) projectNameInput.value = project; setStatus(`Loaded ${project}/sets.`);
        } catch (error) { setStatus(error.message || String(error), true); }
      };

      const renderItems = () => {
        if (!itemsContainer) return;
        itemsContainer.innerHTML = "";
        const cast = sourceCastFor(node); const settings = sourceAnalyzeSettingsFor(node);
        const canAnalyze = !!settings && settings.provider !== "off";
        const activeCount = cast?.characters?.length || 0;
        const base = referenceBaseFor(cast);
        setStatus(cast ? `Connected cast/wardrobe: ${activeCount} character${activeCount === 1 ? "" : "s"}. ` +
          (canAnalyze ? `Set analysis: ${settings.provider}.` : "Connect ANALYZE SETTINGS for descriptions.") :
          "Connect CAST + WARDROBE from Wardrobe Director.");
        let locationOrdinal = 0;
        for (let index = 0; index < MAX_LOCATION_ITEMS; index++) {
          const item = sets.items[index] || emptyItem();
          const hasImage = !!item.images.length;
          const picture = hasImage && base + locationOrdinal + 1 <= MAX_REFERENCE_IMAGES ? base + locationOrdinal + 1 : 0;
          if (hasImage) locationOrdinal++;
          const card = document.createElement("div"); card.className = "mmxd-location-item";
          card.addEventListener("dragover", (event) => { event.preventDefault(); card.classList.add("drag-over"); });
          card.addEventListener("dragleave", () => card.classList.remove("drag-over"));
          card.addEventListener("drop", (event) => { event.preventDefault(); card.classList.remove("drag-over"); const file = Array.from(event.dataTransfer?.files || [])[0]; if (file) uploadImage(file, index); });
          card.addEventListener("click", (event) => { if (!event.target.closest("button, textarea")) inputFileForImage((file) => uploadImage(file, index)); });
          const head = document.createElement("div"); head.className = "mmxd-location-item-head";
          const label = document.createElement("span"); label.className = "mmxd-location-item-label"; label.textContent = `SET ${index + 1}`;
          if (picture) { const tag = document.createElement("span"); tag.className = "mmxd-location-tag"; tag.textContent = `<image ${picture}>`; label.appendChild(tag); }
          head.appendChild(label); const actions = document.createElement("span"); actions.style.display = "flex"; actions.style.gap = "3px";
          if (hasImage && canAnalyze) { const button = document.createElement("button"); button.className = "mmxd-location-analyze"; button.textContent = "ANALYZE"; button.addEventListener("click", (event) => { event.stopPropagation(); analyzeItem(index, button); }); actions.appendChild(button); }
          if (hasImage || String(item.description || "").trim()) { const remove = document.createElement("button"); remove.className = "mmxd-location-remove"; remove.textContent = "REMOVE"; remove.addEventListener("click", (event) => { event.stopPropagation(); sets.items[index] = emptyItem(); renderItems(); save(); }); actions.appendChild(remove); }
          head.appendChild(actions); card.appendChild(head);
          const preview = document.createElement("div"); preview.className = "mmxd-location-preview-wrap";
          if (hasImage) { const image = document.createElement("img"); image.className = "mmxd-location-preview"; image.src = imageSrc(item.images[0]); preview.appendChild(image); const removeImage = document.createElement("button"); removeImage.className = "mmxd-location-delete-image"; removeImage.textContent = "×"; removeImage.addEventListener("click", (event) => { event.stopPropagation(); item.images = []; renderItems(); save(); }); preview.appendChild(removeImage); }
          else { const drop = document.createElement("div"); drop.className = "mmxd-location-drop"; drop.textContent = "Drop location/set image"; preview.appendChild(drop); }
          card.appendChild(preview);
          const fieldLabel = document.createElement("label"); fieldLabel.className = "mmxd-location-field-label"; fieldLabel.textContent = "Location description"; card.appendChild(fieldLabel);
          const textarea = document.createElement("textarea"); textarea.className = "mmxd-location-description"; textarea.value = item.description || ""; textarea.placeholder = "Describe the place, set, and important visual details..."; textarea.addEventListener("click", (event) => event.stopPropagation()); textarea.addEventListener("input", () => { item.description = textarea.value; save(); }); card.appendChild(textarea);
          itemsContainer.appendChild(card);
        }
      };

      const controls = document.createElement("div"); controls.className = "mmxd-location-head";
      const title = document.createElement("span"); title.className = "mmxd-location-title"; title.textContent = "LOCATION SCOUT";
      const help = document.createElement("span"); help.className = "mmxd-location-help"; help.textContent = "Collect set references and descriptions for the prompt.";
      saveProjectButton = document.createElement("button"); saveProjectButton.className = "mmxd-location-project-button";
      saveProjectButton.textContent = "SAVE TO PROJECT"; saveProjectButton.title = "Save the current sets to the connected Director Project.";
      saveProjectButton.addEventListener("click", (event) => { event.stopPropagation(); void saveToProjectNow(); });
      controls.appendChild(title); controls.appendChild(help); controls.appendChild(saveProjectButton);
      projectStatus = document.createElement("div"); projectStatus.className = "mmxd-location-status";
      projectStatus.textContent = "Project data saves automatically; use SAVE TO PROJECT for an immediate snapshot.";
      container.appendChild(controls); container.appendChild(projectStatus);
      status = document.createElement("div"); status.className = "mmxd-location-status"; container.appendChild(status);
      status.textContent = "Project is inherited from the connected Director Project node.";
      itemsContainer = document.createElement("div"); itemsContainer.className = "mmxd-location-items"; container.appendChild(itemsContainer);
      const refreshFromProject = async (projectName, projectPath = "", projectsPath = "") => {
        const project = String(projectName || "").trim();
        if (!project) return;
        try {
          const document = await loadProject(project, projectPath || projectsPath);
          const saved = document?.sources?.sets;
          const value = saved?.sets_data || saved?.widgets?.sets_data;
          if (!value) return;
          sets = parseSets(value);
          if (setsWidget) {
            setsWidget.value = JSON.stringify(sets);
            if (setsWidget.element) setsWidget.element.value = setsWidget.value;
          }
          selectedProject = project;
          node.properties = { ...(node.properties || {}), project_name: project,
            project_path: String(document.project_path || projectPath || ""),
            projects_path: String(document.projects_path || projectsPath || ""), sets_data: JSON.stringify(sets) };
          if (projectNameInput) projectNameInput.value = project;
          renderItems();
          save();
          setStatus(`Loaded ${project}/sets.`);
        } catch (error) {
          setStatus(error.message || String(error), true);
        }
      };
      node._mmxProjectRefresh = refreshFromProject;
      renderItems();
      setTimeout(() => migrateLegacyCastLink(node), 0);
      setTimeout(() => migrateLegacyCastLink(node), 100);
      setTimeout(() => {
        const input = node.inputs?.find((item) => item.name === "project");
        const link = input?.link != null ? app.graph?.links?.[input.link] : null;
        const source = link ? app.graph?.getNodeById(link.origin_id) : null;
        if (source?.properties?.project_name) void refreshFromProject(source.properties.project_name,
          source.properties.project_path || "", source.properties.projects_path || source.properties.project_root || "");
      }, 150);
    };
    const originalConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = originalConfigure?.apply(this, arguments);
      setTimeout(() => migrateLegacyCastLink(this), 0);
      setTimeout(() => migrateLegacyCastLink(this), 100);
      return result;
    };
    const originalConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function () {
      const result = originalConnectionsChange?.apply(this, arguments);
      setTimeout(() => migrateLegacyCastLink(this), 0);
      const input = this.inputs?.find((item) => item.name === "project");
      const link = input?.link != null ? app.graph?.links?.[input.link] : null;
      const source = link ? app.graph?.getNodeById(link.origin_id) : null;
      if (source?.properties?.project_name) void this._mmxProjectRefresh?.(
        source.properties.project_name, source.properties.project_path || "",
        source.properties.projects_path || source.properties.project_root || "");
      return result;
    };
  },
});
