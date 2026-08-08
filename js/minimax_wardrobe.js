// MiniMax H3 Wardrobe Director Plus
// Assign clothing and accessory reference images to the characters from a Casting Director.

const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;

const MAX_WARDROBE_ITEMS = 18;
const MAX_CHARACTERS = 9;
const WARDROBE_CATEGORIES = ["Full Outfits", "Tops", "Bottoms", "Accessories", "Anatomy"];

const emptyItem = () => ({ images: [], description: "", category: WARDROBE_CATEGORIES[0], character_slots: [] });

function emptyWardrobe() {
  return {
    version: 1,
    items: Array.from({ length: MAX_WARDROBE_ITEMS }, emptyItem),
  };
}

function parseWardrobe(value) {
  let parsed = null;
  try { parsed = typeof value === "string" ? JSON.parse(value) : value; } catch (_) { }
  const result = emptyWardrobe();
  if (!parsed || typeof parsed !== "object") return result;
  const items = Array.isArray(parsed.items) ? parsed.items : parsed.wardrobe_items;
  if (!Array.isArray(items)) return result;
  result.items = items.slice(0, MAX_WARDROBE_ITEMS).map((item) => ({
    images: Array.isArray(item?.images) ? item.images.slice(0, 1) :
      (item?.image ? [item.image] : []),
    description: String(item?.description || ""),
    category: WARDROBE_CATEGORIES.includes(item?.category) ? item.category : WARDROBE_CATEGORIES[0],
    character_slots: Array.from(new Set(
      (item?.character_slots || item?.characters || [])
        .map((slot) => Number(slot))
        .filter((slot) => Number.isInteger(slot) && slot >= 1 && slot <= MAX_CHARACTERS)
    )),
  }));
  while (result.items.length < MAX_WARDROBE_ITEMS) result.items.push(emptyItem());
  return result;
}

function readJson(value) {
  try { return value ? JSON.parse(value) : {}; } catch (_) { return {}; }
}

async function fetchProjects() {
  const response = await api.fetchApi("/minimax_director/projects");
  const result = await response.json();
  if (result.status !== "success") throw new Error(result.message || "Could not list projects");
  return Array.isArray(result.projects) ? result.projects : [];
}

async function loadProject(name) {
  const response = await api.fetchApi(`/minimax_director/projects/load?name=${encodeURIComponent(name)}`);
  const result = await response.json();
  if (result.status !== "success") throw new Error(result.message || "Could not load project");
  return result.project || {};
}

async function saveProjectSource(project, source, data) {
  const response = await api.fetchApi("/minimax_director/projects/save", {
    method: "POST",
    body: JSON.stringify({ project, source, data }),
  });
  const result = await response.json();
  if (result.status !== "success") throw new Error(result.message || "Could not save project");
  return result.project || {};
}

function sourceCastFor(node) {
  try {
    const input = node.inputs?.find((item) => item.name === "cast_wardrobe");
    const link = input?.link != null ? app.graph?.links?.[input.link] : null;
    const source = link ? app.graph?.getNodeById(link.origin_id) : null;
    const widget = source?.widgets?.find((item) => item.name === "cast_data");
    const raw = source?.properties?.cast_wardrobe_output
      || widget?.value || source?.properties?.cast_data || input?.value || "";
    const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!parsed || !Array.isArray(parsed.characters)) return null;
    return {
      ...parsed,
      characters: parsed.characters.filter((character) => character?.hired !== false),
    };
  } catch (_) {
    return null;
  }
}

function sourceAnalyzeSettingsFor(node) {
  try {
    const input = node.inputs?.find((item) => item.name === "analyze_settings");
    const link = input?.link != null ? app.graph?.links?.[input.link] : null;
    const source = link ? app.graph?.getNodeById(link.origin_id) : null;
    if (!source) return null;
    const castWidget = source.widgets?.find((item) => item.name === "cast_data");
    const raw = source?.properties?.analyze_settings_output
      || castWidget?.value || source?.properties?.cast_data || input?.value || "";
    const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!parsed || typeof parsed !== "object") return null;
    return {
      provider: String(parsed.provider || parsed.analyzeProvider || "ollama").toLowerCase(),
      base_url: String(parsed.base_url || parsed.analyzeBaseUrl || ""),
      model: String(parsed.model || parsed.analyzeModel || ""),
      api_key: String(parsed.api_key || parsed.analyzeApiKey || ""),
    };
  } catch (_) {
    return null;
  }
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

const WARDROBE_STYLES = `
  .mmxd-wardrobe-wrapper { width:100%; box-sizing:border-box; color:#d8d8d8;
    font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
  .mmxd-wardrobe-head { display:flex; align-items:center; gap:8px; margin:0 0 6px; }
  .mmxd-wardrobe-title { color:#888; font-size:10px; font-weight:700; letter-spacing:.7px; }
  .mmxd-wardrobe-help { color:#666; font-size:9px; flex:1; }
  .mmxd-wardrobe-projects { display:flex; align-items:center; gap:4px; flex-wrap:wrap; margin:0 0 7px; }
  .mmxd-wardrobe-projects label { color:#777; font-size:8px; text-transform:uppercase; letter-spacing:.35px; }
  .mmxd-wardrobe-project-select, .mmxd-wardrobe-project-name, .mmxd-wardrobe-category {
    box-sizing:border-box; min-width:0; height:23px; padding:2px 5px; background:#111;
    color:#d8d8d8; border:1px solid #3a3a3a; border-radius:4px; font-size:9px; font-family:inherit; outline:none;
  }
  .mmxd-wardrobe-project-select { flex:1 1 150px; }
  .mmxd-wardrobe-project-name { flex:1 1 130px; }
  .mmxd-wardrobe-project-button { height:23px; padding:2px 7px; background:#252525; color:#bdbdbd;
    border:1px solid #444; border-radius:4px; font-size:8px; font-weight:700; cursor:pointer; }
  .mmxd-wardrobe-project-button:hover { color:#fff; border-color:#777; }
  .mmxd-wardrobe-status { color:#666; font-size:9px; margin:0 0 7px; }
  .mmxd-wardrobe-items { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; width:100%;
    height:680px; max-height:680px; overflow-y:auto; overflow-x:hidden; align-content:start;
    padding-right:5px; box-sizing:border-box; }
  .mmxd-wardrobe-item { min-width:0; height:220px; box-sizing:border-box; background:#1e1e1e;
    border:1.5px dashed #444; border-radius:7px; padding:5px; position:relative; overflow:hidden; }
  .mmxd-wardrobe-item:hover { border-color:#666; background:#252525; }
  .mmxd-wardrobe-item.drag-over { border-color:#4fff8f; background:rgba(79,255,143,.05); }
  .mmxd-wardrobe-item-head { display:flex; align-items:center; justify-content:space-between; height:16px; }
  .mmxd-wardrobe-item-label { color:#888; font-size:9px; font-weight:700; letter-spacing:.4px; }
  .mmxd-wardrobe-remove { background:#252525; color:#b66; border:1px solid #533; border-radius:3px;
    padding:1px 5px; font-size:8px; font-weight:700; cursor:pointer; }
  .mmxd-wardrobe-remove:hover { background:#4a2020; color:#ff9999; border-color:#a55; }
  .mmxd-wardrobe-analyze { background:#252525; color:#8fd8aa; border:1px solid #365844; border-radius:3px;
    padding:1px 5px; font-size:8px; font-weight:700; cursor:pointer; }
  .mmxd-wardrobe-analyze:hover { background:#1a3a2a; color:#4fff8f; border-color:#4fff8f; }
  .mmxd-wardrobe-analyze.loading { color:#888; border-color:#444; cursor:wait; pointer-events:none; }
  .mmxd-wardrobe-preview-wrap { width:100%; height:58px; margin-top:4px; position:relative;
    border-radius:3px; background:#111; overflow:hidden; cursor:pointer; }
  .mmxd-wardrobe-preview { width:100%; height:100%; object-fit:contain; pointer-events:none; }
  .mmxd-wardrobe-drop { color:#666; text-align:center; font-size:9px; line-height:58px; cursor:pointer; }
  .mmxd-wardrobe-delete-image { position:absolute; top:2px; right:2px; width:15px; height:15px; padding:0;
    border:0; border-radius:50%; background:rgba(0,0,0,.85); color:#ff5555; cursor:pointer; }
  .mmxd-wardrobe-field-label { display:block; color:#777; font-size:8px; line-height:10px;
    margin-top:5px; text-transform:uppercase; letter-spacing:.35px; }
  .mmxd-wardrobe-description { width:100%; height:31px; box-sizing:border-box; padding:2px 4px;
    resize:none; outline:none; background:#111; color:#e0e0e0; border:1px solid #333;
    border-radius:4px; font-family:inherit; font-size:9px; }
  .mmxd-wardrobe-description:focus { border-color:#4fff8f; }
  .mmxd-wardrobe-category { width:100%; margin-top:4px; }
  .mmxd-wardrobe-assign-label { color:#777; font-size:8px; line-height:10px; margin-top:4px;
    text-transform:uppercase; letter-spacing:.35px; }
  .mmxd-wardrobe-assignments { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:3px; margin-top:2px; }
  .mmxd-wardrobe-character { height:18px; padding:0; background:#252525; color:#888; border:1px solid #444;
    border-radius:3px; font-size:8px; cursor:pointer; }
  .mmxd-wardrobe-character:hover { color:#fff; border-color:#777; }
  .mmxd-wardrobe-character.assigned { background:#1a3a2a; color:#4fff8f; border-color:#4fff8f; }
  .mmxd-wardrobe-footer { color:#666; font-size:9px; margin-top:5px; }
`;

let styleEl = document.getElementById("minimax-h3-wardrobe-plus-styles");
if (!styleEl) {
  styleEl = document.createElement("style");
  styleEl.id = "minimax-h3-wardrobe-plus-styles";
  document.head.appendChild(styleEl);
}
styleEl.textContent = WARDROBE_STYLES;

app.registerExtension({
  name: "MiniMaxH3WardrobeDirectorPlusCS",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "MiniMaxH3WardrobeDirectorPlusCS") return;

    const originalCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      originalCreated?.apply(this, arguments);
      const node = this;
      const castInput = node.inputs?.find((input) => input.name === "cast_wardrobe");
      const analyzeSettingsInput = node.inputs?.find((input) => input.name === "analyze_settings");
      const wardrobeWidget = node.widgets?.find((widget) => widget.name === "wardrobe_data");
      if (castInput) {
        castInput.hidden = true;
        castInput.options = { ...(castInput.options || {}), hidden: true };
      }
      if (analyzeSettingsInput) {
        analyzeSettingsInput.hidden = true;
        analyzeSettingsInput.options = { ...(analyzeSettingsInput.options || {}), hidden: true };
      }
      if (wardrobeWidget) {
        wardrobeWidget.hidden = true;
        wardrobeWidget.options = { ...(wardrobeWidget.options || {}), hidden: true };
        wardrobeWidget.computeSize = () => [0, -4];
      }

      const container = document.createElement("div");
      container.className = "mmxd-wardrobe-wrapper";
      const uiWidget = node.addDOMWidget("wardrobe_ui", "wardrobe_ui", container, {
        getValue: () => "",
        setValue: () => {},
      });
      uiWidget.serialize = false;
      uiWidget.computeSize = function (width) {
        return [Math.max(10, width || node.size?.[0] || 760), 820];
      };

      let wardrobe = parseWardrobe(wardrobeWidget?.value || "");
      let outputRevision = 0;
      let projectList = [];
      let selectedProject = String(node.properties?.project_name || "");
      let projectSelect = null;
      let projectNameInput = null;
      let projectStatus = null;

      const setProjectStatus = (message, isError = false) => {
        if (!projectStatus) return;
        projectStatus.textContent = message || "";
        projectStatus.style.color = isError ? "#d86f6f" : "#666";
      };

      const renderProjectOptions = () => {
        if (!projectSelect) return;
        projectSelect.innerHTML = "";
        const blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "Select project...";
        projectSelect.appendChild(blank);
        for (const project of projectList) {
          const option = document.createElement("option");
          option.value = project.name;
          option.textContent = project.name;
          projectSelect.appendChild(option);
        }
        projectSelect.value = selectedProject;
        if (projectNameInput && selectedProject) projectNameInput.value = selectedProject;
      };

      const refreshProjects = async () => {
        try {
          projectList = await fetchProjects();
          renderProjectOptions();
          if (selectedProject) setProjectStatus(`Project: ${selectedProject}`);
        } catch (error) {
          setProjectStatus(error.message || String(error), true);
        }
      };

      const imageDataUrl = async (image) => {
        if (!image) return null;
        if (image.b64) {
          return String(image.b64).includes(",") ? image.b64 : `data:image/jpeg;base64,${image.b64}`;
        }
        const src = imageSrc(image);
        if (!src) return null;
        try {
          const response = await fetch(src);
          const blob = await response.blob();
          return await new Promise((resolve) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result);
            reader.readAsDataURL(blob);
          });
        } catch (_) {
          return null;
        }
      };

      const loadImage = (src) => new Promise((resolve) => {
        if (!src) { resolve(null); return; }
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = () => resolve(null);
        image.src = src;
      });

      const makeCollage = async (images) => {
        const loaded = (await Promise.all(images.map(async (image) =>
          loadImage(await imageDataUrl(image))))).filter(Boolean);
        if (!loaded.length) return null;
        const tile = 192;
        const columns = 4;
        const rows = Math.ceil(loaded.length / columns);
        const canvas = document.createElement("canvas");
        canvas.width = columns * tile;
        canvas.height = rows * tile;
        const context = canvas.getContext("2d");
        context.fillStyle = "#181818";
        context.fillRect(0, 0, canvas.width, canvas.height);
        loaded.forEach((image, index) => {
          const x = (index % columns) * tile;
          const y = Math.floor(index / columns) * tile;
          const scale = Math.min((tile - 12) / image.width, (tile - 28) / image.height);
          const width = Math.max(1, Math.round(image.width * scale));
          const height = Math.max(1, Math.round(image.height * scale));
          context.drawImage(image, x + Math.round((tile - width) / 2),
            y + 20 + Math.round((tile - 20 - height) / 2), width, height);
          context.fillStyle = "rgba(0,0,0,.8)";
          context.fillRect(x + 5, y + 5, 19, 15);
          context.fillStyle = "#fff";
          context.font = "11px sans-serif";
          context.fillText(String(index + 1), x + 11, y + 16);
          context.fillStyle = "#181818";
        });
        return canvas.toDataURL("image/jpeg", 0.88);
      };

      const analyzeItem = async (index, button) => {
        if (button.classList.contains("loading")) return;
        const settings = sourceAnalyzeSettingsFor(node);
        if (!settings || settings.provider === "off") {
          alert("Connect the Casting Director's ANALYZE SETTINGS output and enable analysis.");
          return;
        }
        const image = wardrobe.items[index]?.images?.[0];
        const imageB64 = await imageDataUrl(image);
        if (!imageB64) {
          alert("No readable item image is available for analysis.");
          return;
        }
        button.classList.add("loading");
        button.textContent = "...";
        const body = {
          image_b64: [imageB64],
          item_index: index,
          provider: settings.provider,
          base_url: settings.base_url,
          model: settings.model,
        };
        if (settings.api_key && (settings.provider === "lmstudio" || settings.provider === "custom")) {
          body.api_key = settings.api_key;
        }
        try {
          const response = await api.fetchApi("/minimax_director/analyze_wardrobe_item", {
            method: "POST", body: JSON.stringify(body),
          });
          const result = await response.json();
          if (result.status !== "success") throw new Error(result.message || "Analysis failed");
          wardrobe.items[index].description = String(result.description || "").trim();
          renderItems();
          save();
        } catch (error) {
          alert("Wardrobe Analysis Error: " + (error.message || error));
          button.classList.remove("loading");
          button.textContent = "ANALYZE";
        }
      };

      const buildOutput = async () => {
        const revision = ++outputRevision;
        const cast = sourceCastFor(node) || { version: 2, characters: [] };
        const characters = (cast.characters || []).filter((character) => character?.hired !== false)
          .map((character) => ({ ...character, hired: true }));
        const items = wardrobe.items.map((item) => ({
          images: (item.images || []).slice(0, 1),
          description: String(item.description || "").trim(),
          category: WARDROBE_CATEGORIES.includes(item.category) ? item.category : WARDROBE_CATEGORIES[0],
          character_slots: Array.from(new Set((item.character_slots || [])
            .map((slot) => Number(slot))
            .filter((slot) => Number.isInteger(slot) && slot >= 1 && slot <= characters.length))),
        }));
        const wardrobeCollages = [];
        for (let characterSlot = 1; characterSlot <= characters.length; characterSlot++) {
          const assigned = items.filter((item) => item.character_slots.includes(characterSlot));
          const images = assigned.flatMap((item) => item.images || []);
          const collage = await makeCollage(images);
          if (!collage) continue;
          wardrobeCollages.push({
            character_slot: characterSlot,
            images: [{ b64: collage, name: `wardrobe_collage_char${characterSlot}.jpg` }],
            description: assigned.map((item) => item.description).filter(Boolean).join("; "),
            item_count: images.length,
          });
        }
        if (revision !== outputRevision) return null;
        return JSON.stringify({ version: 2, characters, wardrobe_items: items,
          wardrobe_collages: wardrobeCollages });
      };

      const save = () => {
        const serialized = JSON.stringify(wardrobe);
        if (wardrobeWidget) {
          wardrobeWidget.value = serialized;
          if (wardrobeWidget.element) wardrobeWidget.element.value = serialized;
        }
        node.properties = { ...(node.properties || {}), wardrobe_data: serialized };
        node._wardrobeData = serialized;
        node._widgetSlotsDirty = true;
        node.setDirtyCanvas?.(true, true);
        app.graph?.setDirtyCanvas?.(true, true);
        void buildOutput().then((output) => {
          if (!output) return;
          node.properties = { ...(node.properties || {}), cast_wardrobe_output: output };
          node._wardrobeOutput = output;
          node.setDirtyCanvas?.(true, true);
          app.graph?.setDirtyCanvas?.(true, true);
          for (const other of app.graph?._nodes || []) {
            const input = other.inputs?.find((item) => item.name === "cast");
            const link = input?.link != null ? app.graph.links?.[input.link] : null;
            if (link?.origin_id === node.id) {
              other._mmxRefreshCharacterSlots?.();
              other._mmxRefreshPrompt?.();
              other._mmxRefreshReferenceCounter?.();
            }
          }
        });
      };

      const saveProjectSnapshot = async () => {
        const project = String(projectNameInput?.value || selectedProject || "").trim();
        if (!project) {
          setProjectStatus("Enter a project name first.", true);
          projectNameInput?.focus();
          return;
        }
        selectedProject = project;
        node.properties = { ...(node.properties || {}), project_name: project };
        try {
          const document = await saveProjectSource(project, "wardrobe", {
            wardrobe_data: wardrobe,
            cast_wardrobe: sourceCastFor(node),
            analyze_settings: sourceAnalyzeSettingsFor(node),
          });
          projectList = await fetchProjects();
          renderProjectOptions();
          setProjectStatus(`Saved ${document.project_name}.`);
        } catch (error) {
          setProjectStatus(error.message || String(error), true);
        }
      };

      const loadSelectedProject = async () => {
        const project = String(projectSelect?.value || projectNameInput?.value || "").trim();
        if (!project) return;
        try {
          const document = await loadProject(project);
          const saved = document?.sources?.wardrobe?.wardrobe_data;
          if (saved) {
            wardrobe = parseWardrobe(saved);
            save();
            renderItems();
          }
          selectedProject = project;
          node.properties = { ...(node.properties || {}), project_name: project };
          if (projectNameInput) projectNameInput.value = project;
          setProjectStatus(`Loaded ${project}.`);
        } catch (error) {
          setProjectStatus(error.message || String(error), true);
        }
      };

      const imageSrc = (image) => {
        if (!image) return "";
        if (image.b64) return image.b64;
        if (image.name) {
          const parts = image.name.split("/");
          const filename = parts.pop();
          return api.apiURL(`/view?filename=${encodeURIComponent(filename)}&type=input&subfolder=${encodeURIComponent(parts.join("/"))}`);
        }
        return "";
      };

      const uploadImage = (file, index) => {
        if (!file?.type?.startsWith("image/")) return;
        const reader = new FileReader();
        reader.onload = (event) => {
          const source = new Image();
          source.onload = async () => {
            const maxDim = 1920;
            let width = source.width;
            let height = source.height;
            if (width > maxDim || height > maxDim) {
              if (width > height) { height = Math.round(height * maxDim / width); width = maxDim; }
              else { width = Math.round(width * maxDim / height); height = maxDim; }
            }
            const canvas = document.createElement("canvas");
            canvas.width = width; canvas.height = height;
            canvas.getContext("2d").drawImage(source, 0, 0, width, height);
            let stored = null;
            try {
              const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.95));
              const base = (file.name || "wardrobe").replace(/\.[^.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_");
              const body = new FormData();
              body.append("image", new File([blob], `mmxwardrobe_${base}_${Date.now()}.jpg`, { type: "image/jpeg" }));
              body.append("subfolder", "whatdreamscost");
              const response = await api.fetchApi("/upload/image", { method: "POST", body });
              if (response.status === 200) {
                const data = await response.json();
                stored = { name: data.subfolder ? `${data.subfolder}/${data.name}` : data.name };
              }
            } catch (error) {
              console.warn("[MiniMaxWardrobeDirector] reference upload failed", error);
            }
            if (!stored) stored = { b64: canvas.toDataURL("image/jpeg", 0.95), name: file.name };
            wardrobe.items[index].images = [stored];
            renderItems();
            save();
          };
          source.src = event.target.result;
        };
        reader.readAsDataURL(file);
      };

      const renderItems = () => {
        itemsContainer.innerHTML = "";
        const cast = sourceCastFor(node);
        const analyzeSettings = sourceAnalyzeSettingsFor(node);
        const canAnalyze = !!analyzeSettings && analyzeSettings.provider !== "off";
        const characterCount = Math.min(MAX_CHARACTERS, cast?.characters?.length || 0);
        status.textContent = cast
          ? `Connected cast: ${characterCount} active character${characterCount === 1 ? "" : "s"}. ` +
            (canAnalyze ? `Item analysis: ${analyzeSettings.provider}.` :
              "Connect ANALYZE SETTINGS to analyze item descriptions.")
          : "Connect CAST + WARDROBE from Casting Director to assign items to characters.";
        for (let index = 0; index < MAX_WARDROBE_ITEMS; index++) {
          const item = wardrobe.items[index] || emptyItem();
          const card = document.createElement("div");
          card.className = "mmxd-wardrobe-item";
          card.addEventListener("dragover", (event) => { event.preventDefault(); card.classList.add("drag-over"); });
          card.addEventListener("dragleave", () => card.classList.remove("drag-over"));
          card.addEventListener("drop", (event) => {
            event.preventDefault(); card.classList.remove("drag-over");
            const file = Array.from(event.dataTransfer?.files || [])[0];
            if (file) uploadImage(file, index);
          });
          card.addEventListener("click", (event) => {
            if (event.target.closest("button, textarea, select, input")) return;
            inputFileForImage((file) => uploadImage(file, index));
          });

          const cardHead = document.createElement("div");
          cardHead.className = "mmxd-wardrobe-item-head";
          const label = document.createElement("span");
          label.className = "mmxd-wardrobe-item-label";
          label.textContent = `ITEM ${index + 1}`;
          cardHead.appendChild(label);
          const actions = document.createElement("span");
          actions.style.display = "flex";
          actions.style.gap = "3px";
          if (item.images.length && canAnalyze) {
            const analyze = document.createElement("button");
            analyze.className = "mmxd-wardrobe-analyze";
            analyze.textContent = "ANALYZE";
            analyze.title = "Analyze this clothing/accessory image";
            analyze.addEventListener("click", (event) => {
              event.stopPropagation();
              analyzeItem(index, analyze);
            });
            actions.appendChild(analyze);
          }
          if (item.images.length || String(item.description || "").trim() || item.character_slots.length) {
            const remove = document.createElement("button");
            remove.className = "mmxd-wardrobe-remove";
            remove.textContent = "REMOVE";
            remove.addEventListener("click", (event) => {
              event.stopPropagation(); wardrobe.items[index] = emptyItem(); renderItems(); save();
            });
            actions.appendChild(remove);
          }
          cardHead.appendChild(actions);
          card.appendChild(cardHead);

          const previewWrap = document.createElement("div");
          previewWrap.className = "mmxd-wardrobe-preview-wrap";
          if (item.images.length) {
            const image = document.createElement("img");
            image.className = "mmxd-wardrobe-preview";
            image.src = imageSrc(item.images[0]);
            previewWrap.appendChild(image);
            const removeImage = document.createElement("button");
            removeImage.className = "mmxd-wardrobe-delete-image";
            removeImage.textContent = "×";
            removeImage.title = "Delete item image";
            removeImage.addEventListener("click", (event) => {
              event.stopPropagation(); item.images = []; renderItems(); save();
            });
            previewWrap.appendChild(removeImage);
          } else {
            const drop = document.createElement("div");
            drop.className = "mmxd-wardrobe-drop";
            drop.textContent = "Drop clothing/accessory image";
            previewWrap.appendChild(drop);
          }
          card.appendChild(previewWrap);

          const category = document.createElement("select");
          category.className = "mmxd-wardrobe-category";
          for (const categoryName of WARDROBE_CATEGORIES) {
            const option = document.createElement("option");
            option.value = categoryName;
            option.textContent = categoryName;
            category.appendChild(option);
          }
          category.value = WARDROBE_CATEGORIES.includes(item.category)
            ? item.category : WARDROBE_CATEGORIES[0];
          category.title = "Reference category";
          category.addEventListener("click", (event) => event.stopPropagation());
          category.addEventListener("change", () => { item.category = category.value; save(); });
          card.appendChild(category);

          const descriptionLabel = document.createElement("label");
          descriptionLabel.className = "mmxd-wardrobe-field-label";
          descriptionLabel.textContent = "Item description";
          card.appendChild(descriptionLabel);
          const description = document.createElement("textarea");
          description.className = "mmxd-wardrobe-description";
          description.value = item.description || "";
          description.placeholder = "e.g. a fitted red leather jacket...";
          description.addEventListener("click", (event) => event.stopPropagation());
          description.addEventListener("input", () => { item.description = description.value; save(); });
          card.appendChild(description);

          const assignLabel = document.createElement("div");
          assignLabel.className = "mmxd-wardrobe-assign-label";
          assignLabel.textContent = "Assign to characters";
          card.appendChild(assignLabel);
          const assignments = document.createElement("div");
          assignments.className = "mmxd-wardrobe-assignments";
          for (let character = 1; character <= characterCount; character++) {
            const toggle = document.createElement("button");
            toggle.className = "mmxd-wardrobe-character" +
              (item.character_slots.includes(character) ? " assigned" : "");
            toggle.textContent = `@${character}`;
            toggle.title = `Assign item ${index + 1} to character ${character}`;
            toggle.addEventListener("click", (event) => {
              event.stopPropagation();
              if (item.character_slots.includes(character)) {
                item.character_slots = item.character_slots.filter((slot) => slot !== character);
              } else {
                item.character_slots.push(character);
              }
              renderItems(); save();
            });
            assignments.appendChild(toggle);
          }
          card.appendChild(assignments);
          itemsContainer.appendChild(card);
        }
      };

      const head = document.createElement("div");
      head.className = "mmxd-wardrobe-head";
      const title = document.createElement("span");
      title.className = "mmxd-wardrobe-title";
      title.textContent = "WARDROBE DIRECTOR";
      const help = document.createElement("span");
      help.className = "mmxd-wardrobe-help";
      help.textContent = "Assign clothing/accessories · connect ANALYZE SETTINGS for item analysis";
      head.appendChild(title); head.appendChild(help);
      const projectBar = document.createElement("div");
      projectBar.className = "mmxd-wardrobe-projects";
      const projectLabel = document.createElement("label");
      projectLabel.textContent = "Project";
      projectSelect = document.createElement("select");
      projectSelect.className = "mmxd-wardrobe-project-select";
      projectSelect.title = "Load a saved wardrobe project";
      projectSelect.addEventListener("change", loadSelectedProject);
      projectNameInput = document.createElement("input");
      projectNameInput.className = "mmxd-wardrobe-project-name";
      projectNameInput.placeholder = "New or existing project name";
      projectNameInput.value = selectedProject;
      projectNameInput.addEventListener("input", () => {
        selectedProject = projectNameInput.value.trim();
        node.properties = { ...(node.properties || {}), project_name: selectedProject };
      });
      const refreshProjectsButton = document.createElement("button");
      refreshProjectsButton.className = "mmxd-wardrobe-project-button";
      refreshProjectsButton.textContent = "REFRESH";
      refreshProjectsButton.addEventListener("click", () => { void refreshProjects(); });
      const saveProjectButton = document.createElement("button");
      saveProjectButton.className = "mmxd-wardrobe-project-button";
      saveProjectButton.textContent = "SAVE PROJECT";
      saveProjectButton.addEventListener("click", () => { void saveProjectSnapshot(); });
      projectBar.appendChild(projectLabel);
      projectBar.appendChild(projectSelect);
      projectBar.appendChild(projectNameInput);
      projectBar.appendChild(refreshProjectsButton);
      projectBar.appendChild(saveProjectButton);
      projectStatus = document.createElement("span");
      projectStatus.className = "mmxd-wardrobe-status";
      projectStatus.style.margin = "0 0 5px";
      const status = document.createElement("div");
      status.className = "mmxd-wardrobe-status";
      const itemsContainer = document.createElement("div");
      itemsContainer.className = "mmxd-wardrobe-items";
      const footer = document.createElement("div");
      footer.className = "mmxd-wardrobe-footer";
      footer.textContent = "Up to 18 item image slots. One wardrobe collage is generated per assigned character and sent to the Director's cast input.";
      container.appendChild(head); container.appendChild(projectBar); container.appendChild(projectStatus);
      container.appendChild(status); container.appendChild(itemsContainer); container.appendChild(footer);

      const refresh = () => {
        wardrobe = parseWardrobe(wardrobeWidget?.value || node._wardrobeData || "");
        renderItems();
        save();
      };
      node._wardrobeRefresh = refresh;
      refresh();
      renderProjectOptions();
      void refreshProjects();
      setTimeout(refresh, 0);
      setTimeout(refresh, 100);
    };

    const originalConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = originalConfigure?.apply(this, arguments);
      setTimeout(() => this._wardrobeRefresh?.(), 0);
      setTimeout(() => this._wardrobeRefresh?.(), 100);
      return result;
    };

    const originalSerialize = nodeType.prototype.onSerialize;
    nodeType.prototype.onSerialize = function (info) {
      const result = originalSerialize?.apply(this, arguments);
      const widget = this.widgets?.find((item) => item.name === "wardrobe_data");
      if (widget?.value) {
        this.properties = { ...(this.properties || {}), wardrobe_data: widget.value };
        info.properties = { ...(info.properties || {}), wardrobe_data: widget.value,
          cast_wardrobe_output: this.properties.cast_wardrobe_output || "",
          project_name: this.properties.project_name || "" };
      }
      return result;
    };
  },
});
