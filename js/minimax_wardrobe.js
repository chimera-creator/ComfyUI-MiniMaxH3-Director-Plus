// MiniMax H3 Wardrobe Director Plus
// Assign clothing and accessory reference images to the characters from a Casting Director.

const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;

const MAX_WARDROBE_ITEMS = 9;
const MAX_CHARACTERS = 9;

const emptyItem = () => ({ images: [], description: "", character_slots: [] });

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
  .mmxd-wardrobe-status { color:#666; font-size:9px; margin:0 0 7px; }
  .mmxd-wardrobe-items { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; width:100%; }
  .mmxd-wardrobe-item { min-width:0; height:220px; box-sizing:border-box; background:#1e1e1e;
    border:1.5px dashed #444; border-radius:7px; padding:5px; position:relative; overflow:hidden; }
  .mmxd-wardrobe-item:hover { border-color:#666; background:#252525; }
  .mmxd-wardrobe-item.drag-over { border-color:#4fff8f; background:rgba(79,255,143,.05); }
  .mmxd-wardrobe-item-head { display:flex; align-items:center; justify-content:space-between; height:16px; }
  .mmxd-wardrobe-item-label { color:#888; font-size:9px; font-weight:700; letter-spacing:.4px; }
  .mmxd-wardrobe-remove { background:#252525; color:#b66; border:1px solid #533; border-radius:3px;
    padding:1px 5px; font-size:8px; font-weight:700; cursor:pointer; }
  .mmxd-wardrobe-remove:hover { background:#4a2020; color:#ff9999; border-color:#a55; }
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
      const wardrobeWidget = node.widgets?.find((widget) => widget.name === "wardrobe_data");
      if (castInput) {
        castInput.hidden = true;
        castInput.options = { ...(castInput.options || {}), hidden: true };
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
        return [Math.max(10, width || node.size?.[0] || 760), 790];
      };

      let wardrobe = parseWardrobe(wardrobeWidget?.value || "");

      const buildOutput = () => {
        const cast = sourceCastFor(node) || { version: 2, characters: [] };
        const characters = (cast.characters || []).filter((character) => character?.hired !== false)
          .map((character) => ({ ...character, hired: true }));
        const items = wardrobe.items.map((item) => ({
          images: (item.images || []).slice(0, 1),
          description: String(item.description || "").trim(),
          character_slots: Array.from(new Set((item.character_slots || [])
            .map((slot) => Number(slot))
            .filter((slot) => Number.isInteger(slot) && slot >= 1 && slot <= characters.length))),
        }));
        return JSON.stringify({ version: 2, characters, wardrobe_items: items });
      };

      const save = () => {
        const serialized = JSON.stringify(wardrobe);
        if (wardrobeWidget) {
          wardrobeWidget.value = serialized;
          if (wardrobeWidget.element) wardrobeWidget.element.value = serialized;
        }
        const output = buildOutput();
        node.properties = {
          ...(node.properties || {}),
          wardrobe_data: serialized,
          cast_wardrobe_output: output,
        };
        node._wardrobeData = serialized;
        node._wardrobeOutput = output;
        node._widgetSlotsDirty = true;
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
        const characterCount = Math.min(MAX_CHARACTERS, cast?.characters?.length || 0);
        status.textContent = cast
          ? `Connected cast: ${characterCount} active character${characterCount === 1 ? "" : "s"}. Assign each item to one or more characters.`
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
            if (event.target.closest("button, textarea")) return;
            inputFileForImage((file) => uploadImage(file, index));
          });

          const cardHead = document.createElement("div");
          cardHead.className = "mmxd-wardrobe-item-head";
          const label = document.createElement("span");
          label.className = "mmxd-wardrobe-item-label";
          label.textContent = `ITEM ${index + 1}`;
          cardHead.appendChild(label);
          if (item.images.length || String(item.description || "").trim() || item.character_slots.length) {
            const remove = document.createElement("button");
            remove.className = "mmxd-wardrobe-remove";
            remove.textContent = "REMOVE";
            remove.addEventListener("click", (event) => {
              event.stopPropagation(); wardrobe.items[index] = emptyItem(); renderItems(); save();
            });
            cardHead.appendChild(remove);
          }
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
      help.textContent = "Assign clothing and accessories to cast members";
      head.appendChild(title); head.appendChild(help);
      const status = document.createElement("div");
      status.className = "mmxd-wardrobe-status";
      const itemsContainer = document.createElement("div");
      itemsContainer.className = "mmxd-wardrobe-items";
      const footer = document.createElement("div");
      footer.className = "mmxd-wardrobe-footer";
      footer.textContent = "Up to 9 item image slots. Connect CAST + WARDROBE to the Director's cast input.";
      container.appendChild(head); container.appendChild(status); container.appendChild(itemsContainer); container.appendChild(footer);

      const refresh = () => {
        wardrobe = parseWardrobe(wardrobeWidget?.value || node._wardrobeData || "");
        renderItems();
        save();
      };
      node._wardrobeRefresh = refresh;
      refresh();
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
          cast_wardrobe_output: this.properties.cast_wardrobe_output || "" };
      }
      return result;
    };
  },
});
