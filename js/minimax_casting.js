// MiniMax H3 Casting Director Plus
// A standalone version of the Director's nine reusable character slots.

const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;

const CASTING_DEFAULTS = {
  analyzeProvider: "ollama",
  analyzeBaseUrl: "",
  analyzeModel: "",
  analyzeApiKey: "",
};
const MAX_CAST_IMAGES = 9;
const MAX_CHARACTERS = 9;

const emptyCharacter = () => ({
  images: [], appearance: "", wardrobe: "", description: "", hired: false,
});

const isHired = (character) => character?.hired === undefined || character.hired !== false;

const mergeCharacterDescription = (character) => {
  const appearance = String(character?.appearance || "").trim();
  const wardrobe = String(character?.wardrobe || "").trim();
  if (appearance || wardrobe) return [appearance, wardrobe].filter(Boolean).join(" ");
  return String(character?.description || "").trim();
};

function emptyCast() {
  return {
    version: 1,
    characters: Array.from({ length: MAX_CHARACTERS }, emptyCharacter),
    ...CASTING_DEFAULTS,
  };
}

function parseCast(value) {
  let parsed = null;
  try { parsed = typeof value === "string" ? JSON.parse(value) : value; } catch (_) { }
  const cast = emptyCast();
  if (!parsed || typeof parsed !== "object") return cast;

  if (Array.isArray(parsed.characters)) {
    cast.characters = parsed.characters.slice(0, MAX_CHARACTERS).map((item) => {
      const legacyDescription = String(item?.description || "").trim();
      const appearance = String(item?.appearance || "").trim();
      const wardrobe = String(item?.wardrobe || "").trim();
      // Show an old one-piece description in the new Appearance field until the user
      // edits or re-runs analysis, while preserving its Director-facing meaning.
      const hasSplit = !!(appearance || wardrobe);
      const character = {
        images: Array.isArray(item?.images) ? item.images : [],
        appearance: hasSplit ? appearance : legacyDescription,
        wardrobe: hasSplit ? wardrobe : "",
        description: legacyDescription,
        // Casts saved before the hire toggle existed remain active.
        hired: isHired(item),
      };
      character.description = mergeCharacterDescription(character);
      return character;
    });
    while (cast.characters.length < MAX_CHARACTERS) cast.characters.push(emptyCharacter());
  }
  for (const key of ["analyzeProvider", "analyzeBaseUrl", "analyzeModel", "analyzeApiKey"]) {
    if (parsed[key] !== undefined) cast[key] = String(parsed[key] || "");
  }
  return cast;
}

const CASTING_STYLES = `
  .mmxd-casting-wrapper {
    width: 100%; box-sizing: border-box; color: #d8d8d8;
    font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .mmxd-casting-head { display:flex; align-items:center; gap:8px; margin:0 0 6px; }
  .mmxd-casting-title { color:#888; font-size:10px; font-weight:700; letter-spacing:.7px; }
  .mmxd-casting-help { color:#666; font-size:9px; flex:1; }
  .mmxd-casting-settings-btn { background:#252525; color:#aaa; border:1px solid #444; border-radius:4px; padding:3px 7px; font-size:10px; cursor:pointer; }
  .mmxd-casting-settings-btn:hover { color:#fff; border-color:#777; }
  .mmxd-casting-settings { display:none; background:#191919; border:1px solid #333; border-radius:5px; padding:6px; margin:0 0 7px; }
  .mmxd-casting-settings.open { display:block; }
  .mmxd-casting-setting-row { display:flex; align-items:center; gap:6px; min-height:25px; }
  .mmxd-casting-setting-label { width:108px; color:#888; font-size:10px; }
  .mmxd-casting-setting-input, .mmxd-casting-setting-select { flex:1; min-width:0; height:22px; box-sizing:border-box; background:#242424; color:#ddd; border:1px solid #444; border-radius:3px; padding:2px 5px; font-size:10px; }
  .mmxd-casting-setting-note { color:#666; font-size:9px; line-height:1.3; padding:4px 0 0 114px; }
  .mmxd-casting-slots { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px; width:100%; box-sizing:border-box; }
  .mmxd-casting-slot { min-width:0; height:180px; box-sizing:border-box; background:#1e1e1e; border:1.5px dashed #444; border-radius:7px; padding:4px; position:relative; cursor:pointer; overflow:hidden; }
  .mmxd-casting-hire-toggle { position:absolute; top:4px; right:4px; z-index:8; background:#252525; color:#888; border:1px solid #444; border-radius:3px; padding:2px 6px; font-size:9px; font-weight:700; cursor:pointer; }
  .mmxd-casting-hire-toggle:hover { color:#fff; border-color:#777; }
  .mmxd-casting-hire-toggle.hired { background:#1a3a2a; color:#4fff8f; border-color:#4fff8f; }
  .mmxd-casting-remove { position:absolute; left:4px; bottom:4px; z-index:8; background:#252525; color:#b66; border:1px solid #533; border-radius:3px; padding:2px 6px; font-size:9px; font-weight:700; cursor:pointer; }
  .mmxd-casting-remove:hover { background:#4a2020; color:#ff9999; border-color:#a55; }
  .mmxd-casting-slot:hover { border-color:#666; background:#252525; }
  .mmxd-casting-slot.drag-over { border-color:#4fff8f; background:rgba(79,255,143,.05); }
  .mmxd-casting-label { font-size:10px; font-weight:700; color:#888; text-align:center; margin-bottom:2px; pointer-events:none; }
  .mmxd-casting-placeholder { font-size:9px; color:#666; text-align:center; line-height:1.5; margin-top:26px; pointer-events:none; }
  .mmxd-casting-preview-row { display:flex; width:100%; height:52px; gap:4px; position:relative; }
  .mmxd-casting-preview-wrap { flex:1; height:100%; min-width:0; position:relative; overflow:hidden; border-radius:3px; background:#111; }
  .mmxd-casting-preview { width:100%; height:100%; object-fit:cover; pointer-events:none; }
  .mmxd-casting-delete { position:absolute; top:2px; right:2px; width:15px; height:15px; padding:0; border:0; border-radius:50%; background:rgba(0,0,0,.85); color:#ff5555; cursor:pointer; z-index:3; }
  .mmxd-casting-delete:hover { background:#ff4444; color:#fff; }
  .mmxd-casting-analyze { position:absolute; bottom:-8px; left:50%; transform:translateX(-50%); background:rgba(0,0,0,.88); color:#ddd; border:1px solid #444; border-radius:3px; padding:2px 7px; font-size:9px; font-weight:700; cursor:pointer; z-index:5; white-space:nowrap; }
  .mmxd-casting-analyze:hover { background:#4fff8f; color:#000; border-color:#4fff8f; }
  .mmxd-casting-analyze.loading { background:#333; color:#888; cursor:wait; pointer-events:none; }
  .mmxd-casting-field { width:100%; margin-top:5px; }
  .mmxd-casting-field-label { display:block; color:#777; font-size:8px; line-height:10px; text-transform:uppercase; letter-spacing:.35px; }
  .mmxd-casting-description { width:100%; height:28px; box-sizing:border-box; padding:2px 4px; resize:none; outline:none; background:#111; color:#e0e0e0; border:1px solid #333; border-radius:4px; font-family:inherit; font-size:9px; }
  .mmxd-casting-description:focus { border-color:#4fff8f; }
  .mmxd-casting-footer { color:#666; font-size:9px; margin-top:5px; }
`;

let styleEl = document.getElementById("minimax-h3-casting-plus-styles");
if (!styleEl) {
  styleEl = document.createElement("style");
  styleEl.id = "minimax-h3-casting-plus-styles";
  document.head.appendChild(styleEl);
}
styleEl.textContent = CASTING_STYLES;

function inputFileForImages(onFiles) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.multiple = true;
  input.addEventListener("change", (event) => {
    if (event.target.files) onFiles(Array.from(event.target.files));
  });
  input.click();
}

app.registerExtension({
  name: "MiniMaxH3CastingDirectorPlusCS",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "MiniMaxH3CastingDirectorPlusCS") return;

    const originalCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      originalCreated?.apply(this, arguments);
      const node = this;
      const castWidget = node.widgets?.find((widget) => widget.name === "cast_data");

      if (castWidget) {
        castWidget.hidden = true;
        castWidget.options = { ...(castWidget.options || {}), hidden: true };
        castWidget.computeSize = () => [0, -4];
      }

      const container = document.createElement("div");
      container.className = "mmxd-casting-wrapper";
      let settingsOpen = false;
      const uiWidget = node.addDOMWidget("casting_ui", "casting_ui", container, {
        getValue: () => "",
        setValue: () => {},
      });
      uiWidget.serialize = false;
      uiWidget.computeSize = function (width) {
        return [Math.max(10, width || node.size?.[0] || 760), settingsOpen ? 738 : 618];
      };

      let cast = parseCast(castWidget?.value || "");

      const save = () => {
        const serialized = JSON.stringify(cast);
        if (castWidget) {
          castWidget.value = serialized;
          if (castWidget.element) castWidget.element.value = serialized;
        }
        node.properties = { ...(node.properties || {}), cast_data: serialized };
        node._castingData = serialized;
        node._widgetSlotsDirty = true;
        node.setDirtyCanvas?.(true, true);
        app.graph?.setDirtyCanvas?.(true, true);
        for (const other of app.graph?._nodes || []) {
          const castInput = other.inputs?.find((input) => input.name === "cast");
          const wardrobeInput = other.inputs?.find((input) => input.name === "cast_wardrobe");
          const castLink = castInput?.link != null ? app.graph.links?.[castInput.link] : null;
          const wardrobeLink = wardrobeInput?.link != null ? app.graph.links?.[wardrobeInput.link] : null;
          if (castLink?.origin_id === node.id) {
            other._mmxRefreshCharacterSlots?.();
            other._mmxRefreshPrompt?.();
            other._mmxRefreshReferenceCounter?.();
          }
          if (wardrobeLink?.origin_id === node.id) {
            other._wardrobeRefresh?.();
          }
        }
      };

      const refImageSrc = (image) => {
        if (!image) return "";
        if (image.b64) return image.b64;
        if (image.name) {
          const parts = image.name.split("/");
          const filename = parts.pop();
          return api.apiURL(`/view?filename=${encodeURIComponent(filename)}&type=input&subfolder=${encodeURIComponent(parts.join("/"))}`);
        }
        return "";
      };

      const refImageToB64 = async (image) => {
        if (!image) return null;
        if (image.b64) return image.b64;
        const src = refImageSrc(image);
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
              const base = (file.name || "ref").replace(/\.[^.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_");
              const uploadName = `mmxcast_${base}_${Date.now()}.jpg`;
              const body = new FormData();
              body.append("image", new File([blob], uploadName, { type: "image/jpeg" }));
              body.append("subfolder", "whatdreamscost");
              const response = await api.fetchApi("/upload/image", { method: "POST", body });
              if (response.status === 200) {
                const data = await response.json();
                stored = { name: data.subfolder ? `${data.subfolder}/${data.name}` : data.name };
              }
            } catch (error) {
              console.warn("[MiniMaxCastingDirector] reference upload failed", error);
            }
            if (!stored) stored = { b64: canvas.toDataURL("image/jpeg", 0.95), name: file.name };

            const images = cast.characters[index].images || (cast.characters[index].images = []);
            const totalImages = cast.characters.reduce((sum, character) =>
              sum + (character.images || []).length, 0);
            if (totalImages >= MAX_CAST_IMAGES) {
              alert(`Casting Director supports up to ${MAX_CAST_IMAGES} character images total.`);
              return;
            }
            images.push(stored);
            renderSlots();
            save();
          };
          source.src = event.target.result;
        };
        reader.readAsDataURL(file);
      };

      const runAnalysis = async (index, button) => {
        if (button.classList.contains("loading")) return;
        button.classList.add("loading");
        button.textContent = "Analyzing...";
        const images = (await Promise.all((cast.characters[index].images || []).map(refImageToB64))).filter(Boolean);
        const body = {
          clip_name: "",
          image_b64: images,
          char_index: index,
          provider: cast.analyzeProvider || "ollama",
          base_url: cast.analyzeBaseUrl || "",
          model: cast.analyzeModel || "",
        };
        const apiKey = String(cast.analyzeApiKey || "").trim();
        if (apiKey && (body.provider === "lmstudio" || body.provider === "custom")) body.api_key = apiKey;

        try {
          const response = await api.fetchApi("/minimax_director/analyze_character", {
            method: "POST", body: JSON.stringify(body),
          });
          const result = await response.json();
          if (result.status !== "success") throw new Error(result.message || "Analysis failed");
          cast.characters[index].appearance = result.appearance || result.description || "";
          cast.characters[index].wardrobe = result.wardrobe || "";
          cast.characters[index].description = mergeCharacterDescription(cast.characters[index]);
          save();
          renderSlots();
        } catch (error) {
          alert("Analysis Error: " + (error.message || error));
          button.classList.remove("loading");
          button.textContent = "Analyze";
        }
      };

      const settingRow = (label, control) => {
        const row = document.createElement("div");
        row.className = "mmxd-casting-setting-row";
        const caption = document.createElement("span");
        caption.className = "mmxd-casting-setting-label";
        caption.textContent = label;
        row.appendChild(caption);
        row.appendChild(control);
        return row;
      };

      const settings = document.createElement("div");
      settings.className = "mmxd-casting-settings";
      const provider = document.createElement("select");
      provider.className = "mmxd-casting-setting-select";
      [["off", "Off / Manual"], ["ollama", "Ollama"], ["lmstudio", "LM Studio"], ["custom", "Custom (OpenAI-compatible)"]]
        .forEach(([value, label]) => {
          const option = document.createElement("option");
          option.value = value; option.textContent = label; provider.appendChild(option);
        });
      const url = document.createElement("input");
      url.className = "mmxd-casting-setting-input"; url.type = "text";
      const model = document.createElement("input");
      model.className = "mmxd-casting-setting-input"; model.type = "text";
      const apiKey = document.createElement("input");
      apiKey.className = "mmxd-casting-setting-input"; apiKey.type = "password"; apiKey.autocomplete = "off";

      const refreshSettings = () => {
        const current = cast.analyzeProvider || "ollama";
        provider.value = current;
        url.value = cast.analyzeBaseUrl || "";
        model.value = cast.analyzeModel || "";
        apiKey.value = cast.analyzeApiKey || "";
        const off = current === "off";
        url.parentElement.style.display = off ? "none" : "";
        model.parentElement.style.display = off ? "none" : "";
        apiKey.parentElement.style.display = (current === "lmstudio" || current === "custom") ? "" : "none";
        url.placeholder = current === "ollama" ? "http://127.0.0.1:11434" : "http://your-server:port";
        model.placeholder = current === "ollama" ? "qwen2.5vl:7b" : "your-loaded-model-name";
      };
      provider.addEventListener("change", () => {
        cast.analyzeProvider = provider.value;
        cast.analyzeBaseUrl = "";
        cast.analyzeModel = "";
        refreshSettings(); save(); renderSlots();
      });
      url.addEventListener("change", () => { cast.analyzeBaseUrl = url.value.trim(); save(); });
      model.addEventListener("change", () => { cast.analyzeModel = model.value.trim(); save(); });
      apiKey.addEventListener("change", () => { cast.analyzeApiKey = apiKey.value.trim(); save(); });
      settings.appendChild(settingRow("Provider", provider));
      settings.appendChild(settingRow("Base URL", url));
      settings.appendChild(settingRow("Model", model));
      settings.appendChild(settingRow("API Key (optional)", apiKey));
      const note = document.createElement("div");
      note.className = "mmxd-casting-setting-note";
      note.textContent = "Off uses manual descriptions. API keys are only sent to LM Studio or Custom providers when present.";
      settings.appendChild(note);

      const renderSlots = () => {
        slots.innerHTML = "";
        for (let index = 0; index < MAX_CHARACTERS; index++) {
          const slot = document.createElement("div");
          slot.className = "mmxd-casting-slot";
          slot.dataset.index = index;
          slot.addEventListener("dragover", (event) => { event.preventDefault(); slot.classList.add("drag-over"); });
          slot.addEventListener("dragleave", () => slot.classList.remove("drag-over"));
          slot.addEventListener("drop", (event) => {
            event.preventDefault(); slot.classList.remove("drag-over");
            Array.from(event.dataTransfer?.files || []).forEach((file) => uploadImage(file, index));
          });
          slot.addEventListener("click", (event) => {
            if (event.target.closest("button, textarea")) return;
            inputFileForImages((files) => files.forEach((file) => uploadImage(file, index)));
          });

          const character = cast.characters[index] || emptyCharacter();
          const hireToggle = document.createElement("button");
          hireToggle.className = "mmxd-casting-hire-toggle" + (isHired(character) ? " hired" : "");
          hireToggle.textContent = isHired(character) ? "HIRED" : "HIRE";
          hireToggle.title = isHired(character)
            ? "Pass this character through to the Director"
            : "Activate this character for Director passthrough";
          hireToggle.addEventListener("click", (event) => {
            event.stopPropagation();
            character.hired = !isHired(character);
            renderSlots();
            save();
          });
          slot.appendChild(hireToggle);

          const hasMember = character.images.length > 0 || !!String(character.appearance || "").trim() ||
            !!String(character.wardrobe || "").trim() || !!String(character.description || "").trim();
          if (hasMember) {
            const removeMember = document.createElement("button");
            removeMember.className = "mmxd-casting-remove";
            removeMember.textContent = "REMOVE";
            removeMember.title = "Remove this cast member";
            removeMember.addEventListener("click", (event) => {
              event.stopPropagation();
              cast.characters[index] = emptyCharacter();
              renderSlots();
              save();
            });
            slot.appendChild(removeMember);
          }

          if (character.images.length) {
            const previews = document.createElement("div");
            previews.className = "mmxd-casting-preview-row";
            character.images.forEach((image, imageIndex) => {
              const wrapper = document.createElement("div");
              wrapper.className = "mmxd-casting-preview-wrap";
              const preview = document.createElement("img");
              preview.className = "mmxd-casting-preview"; preview.src = refImageSrc(image);
              wrapper.appendChild(preview);
              const remove = document.createElement("button");
              remove.className = "mmxd-casting-delete"; remove.textContent = "×"; remove.title = "Delete image";
              remove.addEventListener("click", (event) => {
                event.stopPropagation(); character.images.splice(imageIndex, 1); renderSlots(); save();
              });
              wrapper.appendChild(remove); previews.appendChild(wrapper);
            });
            if ((cast.analyzeProvider || "ollama") !== "off") {
              const analyze = document.createElement("button");
              analyze.className = "mmxd-casting-analyze";
              analyze.textContent = mergeCharacterDescription(character) ? "Re-Analyze" : "Analyze";
              analyze.title = "Analyze this character reference";
              analyze.addEventListener("click", (event) => { event.stopPropagation(); runAnalysis(index, analyze); });
              previews.appendChild(analyze);
            }
            slot.appendChild(previews);
            const addDescriptionField = (labelText, key, placeholder) => {
              const field = document.createElement("div");
              field.className = "mmxd-casting-field";
              const label = document.createElement("label");
              label.className = "mmxd-casting-field-label";
              label.textContent = labelText;
              const input = document.createElement("textarea");
              input.className = "mmxd-casting-description";
              input.value = character[key] || "";
              input.placeholder = placeholder;
              input.addEventListener("click", (event) => event.stopPropagation());
              input.addEventListener("input", () => {
                character[key] = input.value;
                character.description = mergeCharacterDescription(character);
                save();
              });
              field.appendChild(label);
              field.appendChild(input);
              slot.appendChild(field);
            };
            addDescriptionField("Appearance", "appearance", "face, hair, eyes, build — no clothing...");
            addDescriptionField("Wardrobe", "wardrobe", "clothing and accessories...");
          } else {
            const label = document.createElement("div");
            label.className = "mmxd-casting-label"; label.textContent = `@char${index + 1}`;
            const placeholder = document.createElement("div");
            placeholder.className = "mmxd-casting-placeholder"; placeholder.innerHTML = "⇧<br>Drop Sheet";
            slot.appendChild(label); slot.appendChild(placeholder);
          }
          slots.appendChild(slot);
        }
      };

      const head = document.createElement("div");
      head.className = "mmxd-casting-head";
      const title = document.createElement("span");
      title.className = "mmxd-casting-title"; title.textContent = "CASTING DIRECTOR";
      const help = document.createElement("span");
      help.className = "mmxd-casting-help"; help.textContent = "Connect CAST to the Director's cast input";
      const settingsButton = document.createElement("button");
      settingsButton.className = "mmxd-casting-settings-btn"; settingsButton.textContent = "Analyze Settings";
      settingsButton.addEventListener("click", (event) => {
        event.stopPropagation(); settingsOpen = !settingsOpen; settings.classList.toggle("open", settingsOpen);
        node._widgetSlotsDirty = true;
        const required = node.computeSize?.()?.[1] || 0;
        if (required > (node.size?.[1] || 0)) node.setSize?.([node.size[0], required]);
        node.setDirtyCanvas?.(true, true);
      });
      head.appendChild(title); head.appendChild(help); head.appendChild(settingsButton);
      const slots = document.createElement("div");
      slots.className = "mmxd-casting-slots";
      const footer = document.createElement("div");
      footer.className = "mmxd-casting-footer";
      footer.textContent = "Hire selected characters to pass them through. Appearance excludes clothing; Wardrobe covers clothing and accessories. Up to 9 characters and 9 reference images total.";
      container.appendChild(head); container.appendChild(settings); container.appendChild(slots); container.appendChild(footer);

      const refresh = () => {
        cast = parseCast(castWidget?.value || node._castingData || "");
        refreshSettings();
        renderSlots();
        const required = node.computeSize?.()?.[1] || 0;
        if (required > (node.size?.[1] || 0)) node.setSize?.([node.size[0], required]);
      };
      node._castingRefresh = refresh;
      refresh();
      save();
      setTimeout(refresh, 0);
      setTimeout(refresh, 100);
    };

    const originalConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = originalConfigure?.apply(this, arguments);
      setTimeout(() => this._castingRefresh?.(), 0);
      setTimeout(() => this._castingRefresh?.(), 100);
      return result;
    };

    const originalSerialize = nodeType.prototype.onSerialize;
    nodeType.prototype.onSerialize = function (info) {
      const result = originalSerialize?.apply(this, arguments);
      const widget = this.widgets?.find((item) => item.name === "cast_data");
      if (widget?.value) {
        this.properties = { ...(this.properties || {}), cast_data: widget.value };
        info.properties = { ...(info.properties || {}), cast_data: widget.value };
      }
      return result;
    };
  },
});
