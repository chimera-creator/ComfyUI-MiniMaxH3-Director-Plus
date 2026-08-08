// Authoring controls for MiniMax H3 Enhance Prompt Plus.
// Processing is intentionally an explicit action: the generated prompt is stored on the
// node and the Python execute path reuses it during the Director generation queue.

const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;

const ENHANCE_STYLES = `
  .mmxd-enhance-process { display:flex; align-items:center; gap:6px; flex-wrap:wrap; width:100%; box-sizing:border-box; padding:6px 8px; background:#181818; border:1px solid #3a3a3a; border-radius:6px; color:#d8d8d8; font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
  .mmxd-enhance-process button { height:24px; padding:2px 9px; background:#252525; color:#bdbdbd; border:1px solid #484848; border-radius:4px; font-size:8px; font-weight:700; cursor:pointer; }
  .mmxd-enhance-process button:hover { color:#fff; border-color:#777; }
  .mmxd-enhance-process button:disabled { color:#666; cursor:wait; }
  .mmxd-enhance-process-status { flex:1 1 180px; color:#777; font-size:9px; min-height:13px; }
  .mmxd-enhance-output-dialog { width:min(920px,90vw); height:min(720px,85vh); padding:0; color:#ddd; background:#181818; border:1px solid #555; border-radius:8px; }
  .mmxd-enhance-output-dialog::backdrop { background:rgba(0,0,0,.72); }
  .mmxd-enhance-output-dialog-header { display:flex; align-items:center; gap:8px; padding:9px 11px; border-bottom:1px solid #3a3a3a; font:600 11px ui-sans-serif,system-ui,sans-serif; }
  .mmxd-enhance-output-dialog-header span { flex:1; }
  .mmxd-enhance-output-dialog button { height:26px; padding:2px 10px; color:#ccc; background:#272727; border:1px solid #555; border-radius:4px; cursor:pointer; }
  .mmxd-enhance-output-dialog textarea { display:block; width:100%; height:calc(100% - 45px); resize:none; box-sizing:border-box; padding:12px; color:#ddd; background:#111; border:0; outline:0; font:11px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace; white-space:pre-wrap; }
`;

let styleEl = document.getElementById("minimax-h3-enhance-process-styles");
if (!styleEl) {
  styleEl = document.createElement("style");
  styleEl.id = "minimax-h3-enhance-process-styles";
  document.head.appendChild(styleEl);
}
styleEl.textContent = ENHANCE_STYLES;

function linkedNode(node, inputName) {
  const input = node.inputs?.find((item) => item.name === inputName);
  const link = input?.link != null ? app.graph?.links?.[input.link] : null;
  return link ? app.graph?.getNodeById(link.origin_id) : null;
}

function parseJson(value, fallback = null) {
  if (value && typeof value === "object") return value;
  try { return value ? JSON.parse(value) : fallback; } catch (_) { return fallback; }
}

function imageUrl(value) {
  if (!value) return "";
  if (typeof value === "object") {
    if (value.b64) return String(value.b64).includes(",") ? value.b64 : `data:image/jpeg;base64,${value.b64}`;
    value = value.name || value.filename || "";
  }
  const raw = String(value || "");
  if (raw.startsWith("data:")) return raw;
  if (/^https?:\/\//i.test(raw) || raw.startsWith("/view?")) return raw;
  const parts = raw.replaceAll("\\", "/").split("/");
  const filename = parts.pop();
  return filename ? api.apiURL(`/view?filename=${encodeURIComponent(filename)}&type=input&subfolder=${encodeURIComponent(parts.join("/"))}`) : "";
}

async function asDataUrl(value) {
  const src = imageUrl(value);
  if (!src) return null;
  if (src.startsWith("data:")) return src;
  try {
    const response = await fetch(src);
    if (!response.ok) return null;
    const blob = await response.blob();
    return await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(blob);
    });
  } catch (_) { return null; }
}

function sourceImageValue(source) {
  const direct = source?.properties?.image_b64 || source?.properties?.image_data || source?.imgData;
  if (direct) return direct;
  for (const widget of source?.widgets || []) {
    if (widget?.value && (widget.name === "image" || widget.name === "filename" || widget.name === "file")) {
      return widget.value;
    }
  }
  return source?.image || source?.imageData || source?.properties?.image || null;
}

function sourceImageValues(source) {
  if (!source) return [];
  const type = String(source.comfyClass || source.type || "").toLowerCase();
  const values = [];
  const addCastImages = (cast) => {
    (cast?.characters || []).filter((character) => character?.hired !== false).forEach((character) => {
      (character.images || []).forEach((image) => values.push(image));
    });
  };
  if (type.includes("location")) {
    const wardrobeSource = linkedNode(source, "cast_wardrobe");
    const wardrobePayload = parseJson(wardrobeSource?.properties?.cast_wardrobe_output, null);
    addCastImages(wardrobePayload);
    (wardrobePayload?.wardrobe_collages || []).forEach((item) => (item.images || []).slice(0, 1).forEach((image) => values.push(image)));
    const sets = parseJson(source.properties?.sets_data, {});
    (sets?.items || []).forEach((item) => (item.images || []).slice(0, 1).forEach((image) => values.push(image)));
    return values;
  }
  if (type.includes("wardrobe")) {
    const payload = parseJson(source.properties?.cast_wardrobe_output, null);
    addCastImages(payload);
    (payload?.wardrobe_collages || []).forEach((item) => (item.images || []).slice(0, 1).forEach((image) => values.push(image)));
    return values;
  }
  if (type.includes("casting")) {
    addCastImages(parseJson(source.properties?.cast_data, null));
    return values;
  }
  const value = sourceImageValue(source);
  return value ? [value] : [];
}

function sourceForImageInput(node, index) {
  const input = node.inputs?.find((item) => item.name === `image${index}` || item.name === `image_${index}`);
  const link = input?.link != null ? app.graph?.links?.[input.link] : null;
  return link ? app.graph?.getNodeById(link.origin_id) : null;
}

function mergeDescription(character) {
  const appearance = String(character?.appearance || "").trim();
  const wardrobe = String(character?.wardrobe || "").trim();
  return [appearance, wardrobe].filter(Boolean).join(" ") || String(character?.description || "").trim();
}

function castContext(cast, startImage = 0) {
  const characters = Array.isArray(cast?.characters) ? cast.characters : [];
  let imageNumber = startImage;
  const lines = [];
  characters.filter((character) => character?.hired !== false).forEach((character, index) => {
    const description = mergeDescription(character);
    const images = Array.isArray(character?.images) ? character.images : [];
    if (images.length) {
      images.forEach(() => { imageNumber += 1; lines.push(`<image ${imageNumber}> cast character ${index + 1}: ${description}`); });
    } else if (description) {
      lines.push(`Cast character ${index + 1}: ${description}`);
    }
  });
  return { lines, nextImage: imageNumber };
}

function contextFromSource(source, startImage = 0, seen = new Set()) {
  if (!source || seen.has(source.id)) return { lines: [], nextImage: startImage };
  seen.add(source.id);
  const direct = String(source.properties?.context_output || "").trim();
  if (direct) return { lines: direct.split("\n"), nextImage: startImage };

  const type = String(source.comfyClass || source.type || "").toLowerCase();
  let result = { lines: [], nextImage: startImage };
  if (type.includes("location")) {
    result = contextFromSource(linkedNode(source, "cast_wardrobe"), startImage, seen);
    const sets = parseJson(source.properties?.sets_data, {});
    (sets?.items || []).forEach((item, index) => {
      const imageCount = Array.isArray(item?.images) ? item.images.length : 0;
      if (!imageCount && !String(item?.description || "").trim()) return;
      for (let offset = 0; offset < imageCount; offset++) {
        result.nextImage += 1;
        result.lines.push(`<image ${result.nextImage}> location/set ${index + 1}: ${String(item.description || "").trim()}`);
      }
      if (!imageCount && item.description) result.lines.push(`Location/set ${index + 1}: ${item.description}`);
    });
    return result;
  }
  if (type.includes("wardrobe")) {
    result = contextFromSource(linkedNode(source, "cast_wardrobe"), startImage, seen);
    const wardrobe = parseJson(source.properties?.cast_wardrobe_output, {});
    (wardrobe?.wardrobe_collages || []).forEach((item, index) => {
      const description = [item?.description, item?.anatomy_description].filter(Boolean).join(" ").trim();
      if (!description) return;
      const count = Array.isArray(item?.images) ? item.images.length : 1;
      for (let offset = 0; offset < count; offset++) {
        result.nextImage += 1;
        result.lines.push(`<image ${result.nextImage}> wardrobe for character ${item?.character_slot || index + 1}: ${description}`);
      }
    });
    return result;
  }
  const cast = parseJson(source.properties?.cast_data || source.properties?.cast_wardrobe_output, null);
  if (cast) return castContext(cast, startImage);
  return result;
}

function contextDataFromSource(source) {
  if (!source) return null;
  const type = String(source.comfyClass || source.type || "").toLowerCase();
  const refs = [];
  const project = {
    name: String(source.properties?.project_name || ""),
    path: String(source.properties?.project_path || ""),
    asset_roots: [], resources: [],
  };
  const add = (image, sourceName, characterSlot = null, description = "", locationIndex = null) => {
    if (!image) return;
    const index = refs.length + 1;
    refs.push({ index, picture: `<Picture ${index}>`, h3_reference: `<Picture ${index}>`,
      source: sourceName, character_slot: characterSlot, location_index: locationIndex,
      image, description: String(description || "") });
  };
  const addCast = (payload) => {
    (payload?.characters || []).filter((character) => character?.hired !== false).forEach((character, index) => {
      const description = mergeDescription(character);
      (character.images || []).forEach((image) => add(image, "char", index + 1, description));
    });
  };
  let payload = null;
  if (type.includes("location")) {
    const wardrobeSource = linkedNode(source, "cast_wardrobe");
    payload = parseJson(wardrobeSource?.properties?.cast_wardrobe_output, null) ||
      parseJson(wardrobeSource?.widgets?.find((widget) => widget.name === "cast_wardrobe")?.value, {});
    addCast(payload);
    (payload?.wardrobe_collages || []).forEach((item) =>
      (item.images || []).slice(0, 1).forEach((image) =>
        add(image, "wardrobe", item.character_slot, item.description)));
    const sets = parseJson(source.properties?.sets_data, {});
    (sets?.items || []).forEach((item, index) =>
      (item.images || []).slice(0, 1).forEach((image) =>
        add(image, "location", null, item.description, index)));
    payload = { ...(payload || {}), location_references: (sets?.items || []).map((item, index) => ({
      images: item.images || [], description: item.description || "", location_index: index,
    })) };
  } else if (type.includes("wardrobe")) {
    payload = parseJson(source.properties?.cast_wardrobe_output, null) || {};
    addCast(payload);
    (payload?.wardrobe_collages || []).forEach((item) =>
      (item.images || []).slice(0, 1).forEach((image) =>
        add(image, "wardrobe", item.character_slot, item.description)));
  } else if (type.includes("casting")) {
    payload = parseJson(source.properties?.cast_data, null) || {};
    addCast(payload);
  }
  const context = contextFromSource(source);
  return {
    version: 1,
    prompt_context: context.lines.join("\n"),
    images: refs.map((item) => item.image),
    references: refs,
    project,
    project_name: project.name,
    project_path: project.path,
    sources: payload ? { cast_wardrobe_sets: payload } : {},
  };
}

function widgetValue(node, name, fallback = "") {
  const widget = node.widgets?.find((item) => item.name === name);
  return widget?.value ?? fallback;
}

app.registerExtension({
  name: "MiniMaxH3EnhancePromptPlusCSProcess",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "MiniMaxH3EnhancePromptPlusCS") return;

    const originalCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      originalCreated?.apply(this, arguments);
      const node = this;
      const processedWidget = node.widgets?.find((widget) => widget.name === "processed_prompt");
      const processedDirectorWidget = node.widgets?.find((widget) => widget.name === "processed_director_json");
      if (processedWidget) {
        processedWidget.hidden = true;
        processedWidget.options = { ...(processedWidget.options || {}), hidden: true };
        processedWidget.computeSize = () => [0, -4];
      }
      if (processedDirectorWidget) {
        processedDirectorWidget.hidden = true;
        processedDirectorWidget.options = { ...(processedDirectorWidget.options || {}), hidden: true };
        processedDirectorWidget.computeSize = () => [0, -4];
      }

      const container = document.createElement("div");
      container.className = "mmxd-enhance-process";
      const processButton = document.createElement("button");
      processButton.textContent = "PROCESS PROMPT";
      const clearButton = document.createElement("button");
      clearButton.textContent = "CLEAR CACHE";
      const viewButton = document.createElement("button");
      viewButton.textContent = "VIEW OUTPUT";
      viewButton.disabled = true;
      const status = document.createElement("span");
      status.className = "mmxd-enhance-process-status";
      const outputDialog = document.createElement("dialog");
      outputDialog.className = "mmxd-enhance-output-dialog";
      const outputHeader = document.createElement("div");
      outputHeader.className = "mmxd-enhance-output-dialog-header";
      const outputTitle = document.createElement("span");
      outputTitle.textContent = "Processed Enhance prompt and Director JSON";
      const copyOutputButton = document.createElement("button");
      copyOutputButton.textContent = "COPY ALL";
      const closeOutputButton = document.createElement("button");
      closeOutputButton.textContent = "CLOSE";
      const outputText = document.createElement("textarea");
      outputText.readOnly = true;
      outputText.spellcheck = false;
      outputHeader.appendChild(outputTitle);
      outputHeader.appendChild(copyOutputButton);
      outputHeader.appendChild(closeOutputButton);
      outputDialog.appendChild(outputHeader);
      outputDialog.appendChild(outputText);
      document.body.appendChild(outputDialog);
      const previousRemoved = node.onRemoved;
      node.onRemoved = function () {
        outputDialog.remove();
        return previousRemoved?.apply(this, arguments);
      };
      const setStatus = (message, error = false) => {
        status.textContent = message || "";
        status.style.color = error ? "#d86f6f" : "#777";
      };
      const refreshOutputText = () => {
        const prompt = String(processedWidget?.value || node.properties?.processed_prompt || "");
        const rawJson = String(processedDirectorWidget?.value
          || node.properties?.processed_director_json || "");
        let directorJson = rawJson;
        try { directorJson = rawJson ? JSON.stringify(JSON.parse(rawJson), null, 2) : ""; } catch (_) {}
        outputText.value = [prompt ? `PROMPT:\n${prompt}` : "",
          directorJson ? `DIRECTOR_JSON:\n${directorJson}` : ""].filter(Boolean).join("\n\n");
        viewButton.disabled = !outputText.value;
      };
      node._mmxRefreshEnhanceOutput = refreshOutputText;
      const setCachedPrompt = (prompt) => {
        const value = String(prompt || "");
        if (processedWidget) {
          processedWidget.value = value;
          if (processedWidget.element) processedWidget.element.value = value;
        }
        node.properties = { ...(node.properties || {}), processed_prompt: value };
        refreshOutputText();
        node.setDirtyCanvas?.(true, true);
        app.graph?.setDirtyCanvas?.(true, true);
      };
      const setCachedDirectorJson = (value) => {
        const json = String(value || "");
        if (processedDirectorWidget) {
          processedDirectorWidget.value = json;
          if (processedDirectorWidget.element) processedDirectorWidget.element.value = json;
        }
        node.properties = { ...(node.properties || {}),
          processed_director_json: json, director_json: json };
        refreshOutputText();
      };
      const invalidate = () => {
        if (processedWidget?.value || node.properties?.processed_prompt ||
            processedDirectorWidget?.value || node.properties?.processed_director_json) {
          setCachedPrompt("");
          setCachedDirectorJson("");
          setStatus("Inputs changed — press Process Prompt again.");
        }
      };

      const process = async () => {
        if (processButton.disabled) return;
        processButton.disabled = true;
        clearButton.disabled = true;
        setStatus("Processing references and prompt…");
        try {
          const imageValues = [];
          const seenImageSources = new Set();
          const contextDataSource = linkedNode(node, "context_data");
          if (contextDataSource && !seenImageSources.has(contextDataSource.id)) {
            seenImageSources.add(contextDataSource.id);
            for (const value of sourceImageValues(contextDataSource)) {
              const dataUrl = await asDataUrl(value);
              if (dataUrl) imageValues.push(dataUrl);
            }
          }
          for (let index = 0; index < 9; index++) {
            const source = sourceForImageInput(node, index);
            if (!source || seenImageSources.has(source.id)) continue;
            seenImageSources.add(source.id);
            for (const value of sourceImageValues(source)) {
              const dataUrl = await asDataUrl(value);
              if (dataUrl) imageValues.push(dataUrl);
            }
          }
          const contextInput = node.inputs?.find((input) => input.name === "context");
          const contextSource = contextDataSource || linkedNode(node, "context");
          const sourceContext = contextFromSource(contextSource);
          const context = sourceContext.lines.join("\n") || String(contextInput?.value || widgetValue(node, "context", "") || "");
          const contextData = contextDataFromSource(contextSource);
          const response = await api.fetchApi("/minimax_director/enhance/process", {
            method: "POST",
            body: JSON.stringify({
              images: imageValues,
              idea: widgetValue(node, "idea", ""),
              context,
              preset: widgetValue(node, "preset", "Full H3 Prompt to Director"),
              system_prompt: widgetValue(node, "system_prompt", ""),
              duration_seconds: widgetValue(node, "duration_seconds", 5),
              provider: widgetValue(node, "provider", "ollama"),
              base_url: widgetValue(node, "base_url", ""),
              model: widgetValue(node, "model", ""),
              api_key: widgetValue(node, "api_key", ""),
              use_spicy_model: !!widgetValue(node, "use_spicy_model", false),
              spicy_model: widgetValue(node, "spicy_model", ""),
              spicy_system_prompt: widgetValue(node, "spicy_system_prompt", ""),
              seed: widgetValue(node, "seed", 0),
              max_image_size: widgetValue(node, "max_image_size", 768),
              max_words: widgetValue(node, "max_words", 500),
              unload_after: !!widgetValue(node, "unload_after", true),
              on_error: widgetValue(node, "on_error", "passthrough"),
              context_data: contextData,
            }),
          });
          const result = await response.json();
          if (!response.ok || result.status !== "success") throw new Error(result.message || "Process failed");
          setCachedPrompt(result.prompt || "");
          setCachedDirectorJson(result.director_json || "");
          const parsed = parseJson(result.director_json, {});
          const shotCount = Array.isArray(parsed?.shots) ? parsed.shots.length : 0;
          setStatus(`Processed ${imageValues.length} reference image${imageValues.length === 1 ? "" : "s"}`
            + ` and ${shotCount} timeline shot${shotCount === 1 ? "" : "s"}. Generation will reuse this prompt.`);
        } catch (error) {
          setStatus(error.message || String(error), true);
        } finally {
          processButton.disabled = false;
          clearButton.disabled = false;
        }
      };

      clearButton.addEventListener("click", () => {
        setCachedPrompt(""); setCachedDirectorJson(""); setStatus("Prompt cache cleared.");
      });
      viewButton.addEventListener("click", () => {
        refreshOutputText();
        if (outputText.value && typeof outputDialog.showModal === "function") outputDialog.showModal();
      });
      copyOutputButton.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(outputText.value);
          copyOutputButton.textContent = "COPIED";
          setTimeout(() => { copyOutputButton.textContent = "COPY ALL"; }, 1200);
        } catch (_) {
          outputText.focus();
          outputText.select();
        }
      });
      closeOutputButton.addEventListener("click", () => outputDialog.close());
      processButton.addEventListener("click", () => { void process(); });
      container.appendChild(processButton);
      container.appendChild(clearButton);
      container.appendChild(viewButton);
      container.appendChild(status);
      const uiWidget = node.addDOMWidget("enhance_process_ui", "enhance_process_ui", container, {
        getValue: () => "", setValue: () => {},
      });
      uiWidget.serialize = false;
      uiWidget.computeSize = (width) => [Math.max(10, width || node.size?.[0] || 520), 42];

      const watched = ["idea", "context", "preset", "system_prompt", "duration_seconds", "provider",
        "base_url", "model", "api_key", "use_spicy_model", "spicy_model", "spicy_system_prompt",
        "max_image_size", "max_words", "unload_after", "on_error"];
      for (const name of watched) {
        const widget = node.widgets?.find((item) => item.name === name);
        if (widget && typeof widget.callback === "function") {
          const callback = widget.callback;
          widget.callback = function () { invalidate(); return callback.apply(this, arguments); };
        }
      }
      if (node.properties?.processed_prompt && processedWidget && !processedWidget.value) {
        processedWidget.value = node.properties.processed_prompt;
      }
      if (node.properties?.processed_director_json && processedDirectorWidget && !processedDirectorWidget.value) {
        processedDirectorWidget.value = node.properties.processed_director_json;
      }
      refreshOutputText();
      if (processedWidget?.value) setStatus("Processed prompt cached — generation will reuse it.");
    };
    const originalConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = originalConfigure?.apply(this, arguments);
      const widget = this.widgets?.find((item) => item.name === "processed_prompt");
      if (widget && (widget.value || this.properties?.processed_prompt)) {
        widget.value = widget.value || this.properties.processed_prompt;
      }
      const directorWidget = this.widgets?.find((item) => item.name === "processed_director_json");
      if (directorWidget && (directorWidget.value || this.properties?.processed_director_json)) {
        directorWidget.value = directorWidget.value || this.properties.processed_director_json;
      }
      this._mmxRefreshEnhanceOutput?.();
      return result;
    };
    const originalConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function () {
      const result = originalConnectionsChange?.apply(this, arguments);
      const widget = this.widgets?.find((item) => item.name === "processed_prompt");
      if (widget && (widget.value || this.properties?.processed_prompt)) {
        widget.value = "";
        this.properties = { ...(this.properties || {}), processed_prompt: "" };
      }
      const directorWidget = this.widgets?.find((item) => item.name === "processed_director_json");
      if (directorWidget && (directorWidget.value || this.properties?.processed_director_json)) {
        directorWidget.value = "";
        this.properties = { ...(this.properties || {}),
          processed_director_json: "", director_json: "" };
      }
      return result;
    };
  },
});
