// MiniMax H3 Director Project Plus
// Central project selector/creator for Casting, Wardrobe, Location, and Director nodes.

const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;

const PROJECT_STYLES = `
  .mmxd-project-wrapper { width:100%; box-sizing:border-box; color:#d8d8d8; font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
  .mmxd-project-row { display:flex; align-items:center; gap:5px; flex-wrap:wrap; }
  .mmxd-project-label { color:#888; font-size:9px; font-weight:700; letter-spacing:.5px; }
  .mmxd-project-select, .mmxd-project-name, .mmxd-project-path { min-width:0; height:24px; box-sizing:border-box; background:#111; color:#ddd; border:1px solid #3a3a3a; border-radius:4px; padding:2px 5px; font-size:10px; font-family:inherit; outline:none; }
  .mmxd-project-select { flex:1 1 150px; }
  .mmxd-project-name { flex:1 1 150px; }
  .mmxd-project-path { flex:1 1 260px; color:#aaa; }
  .mmxd-project-button { height:24px; padding:2px 8px; background:#252525; color:#bdbdbd; border:1px solid #444; border-radius:4px; font-size:8px; font-weight:700; cursor:pointer; }
  .mmxd-project-button:hover { color:#fff; border-color:#777; }
  .mmxd-project-status { color:#666; font-size:9px; min-height:13px; width:100%; margin-top:4px; }
`;

let styleEl = document.getElementById("minimax-h3-project-plus-styles");
if (!styleEl) {
  styleEl = document.createElement("style");
  styleEl.id = "minimax-h3-project-plus-styles";
  document.head.appendChild(styleEl);
}
styleEl.textContent = PROJECT_STYLES;

async function fetchProjects() {
  const response = await api.fetchApi("/minimax_director/projects");
  const result = await response.json();
  if (result.status !== "success") throw new Error(result.message || "Could not list projects");
  return Array.isArray(result.projects) ? result.projects : [];
}

async function createProject(project, path) {
  const response = await api.fetchApi("/minimax_director/projects/create", {
    method: "POST", body: JSON.stringify({ project, path }),
  });
  const result = await response.json();
  if (result.status !== "success") throw new Error(result.message || "Could not create project");
  return result.project || {};
}

app.registerExtension({
  name: "MiniMaxH3DirectorProjectPlusCS",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "MiniMaxH3DirectorProjectPlusCS") return;

    const originalCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      originalCreated?.apply(this, arguments);
      const node = this;
      const projectWidget = node.widgets?.find((widget) => widget.name === "project_name");
      if (projectWidget) {
        projectWidget.hidden = true;
        projectWidget.options = { ...(projectWidget.options || {}), hidden: true };
        projectWidget.computeSize = () => [0, -4];
      }

      const container = document.createElement("div");
      container.className = "mmxd-project-wrapper";
      const uiWidget = node.addDOMWidget("project_ui", "project_ui", container, {
        getValue: () => "", setValue: () => {},
      });
      uiWidget.serialize = false;
      uiWidget.computeSize = (width) => [Math.max(10, width || node.size?.[0] || 520), 86];

      let projects = [];
      let selectedProject = String(node.properties?.project_name || projectWidget?.value || "");
      const projectPathWidget = node.widgets?.find((widget) => widget.name === "project_path");
      if (projectPathWidget) {
        projectPathWidget.hidden = true;
        projectPathWidget.options = { ...(projectPathWidget.options || {}), hidden: true };
        projectPathWidget.computeSize = () => [0, -4];
      }
      let selectedPath = String(node.properties?.project_path || projectPathWidget?.value || "");
      const row = document.createElement("div"); row.className = "mmxd-project-row";
      const label = document.createElement("span"); label.className = "mmxd-project-label"; label.textContent = "PROJECT";
      const select = document.createElement("select"); select.className = "mmxd-project-select";
      const nameInput = document.createElement("input"); nameInput.className = "mmxd-project-name"; nameInput.placeholder = "New project name";
      const pathRow = document.createElement("div"); pathRow.className = "mmxd-project-row";
      const pathLabel = document.createElement("span"); pathLabel.className = "mmxd-project-label"; pathLabel.textContent = "FOLDER";
      const pathInput = document.createElement("input"); pathInput.className = "mmxd-project-path"; pathInput.placeholder = "Optional project folder path (default: node Projects folder)";
      const browse = document.createElement("button"); browse.className = "mmxd-project-button"; browse.textContent = "BROWSE";
      const refresh = document.createElement("button"); refresh.className = "mmxd-project-button"; refresh.textContent = "REFRESH";
      const create = document.createElement("button"); create.className = "mmxd-project-button"; create.textContent = "CREATE";
      const status = document.createElement("div"); status.className = "mmxd-project-status";

      const setStatus = (message, error = false) => {
        status.textContent = message || "";
        status.style.color = error ? "#d86f6f" : "#666";
      };
      const setProject = (value) => {
        selectedProject = String(value || "").trim();
        nameInput.value = selectedProject;
        if (projectWidget) {
          projectWidget.value = selectedProject;
          if (projectWidget.element) projectWidget.element.value = selectedProject;
        }
        if (projectPathWidget) {
          projectPathWidget.value = selectedPath;
          if (projectPathWidget.element) projectPathWidget.element.value = selectedPath;
        }
        node.properties = { ...(node.properties || {}), project_name: selectedProject, project_path: selectedPath };
        node.setDirtyCanvas?.(true, true);
        app.graph?.setDirtyCanvas?.(true, true);
        // The project socket carries the JSON at queue time. Refresh the connected
        // authoring panels immediately as well, so selecting a project is visible
        // before anything is queued.
        for (const other of app.graph?._nodes || []) {
          const input = other.inputs?.find((item) => item.name === "project");
          const link = input?.link != null ? app.graph.links?.[input.link] : null;
          if (link?.origin_id === node.id) other._mmxProjectRefresh?.(selectedProject, selectedPath);
        }
      };
      const setPath = (value) => {
        selectedPath = String(value || "").trim();
        pathInput.value = selectedPath;
        if (projectPathWidget) {
          projectPathWidget.value = selectedPath;
          if (projectPathWidget.element) projectPathWidget.element.value = selectedPath;
        }
        node.properties = { ...(node.properties || {}), project_path: selectedPath };
        node.setDirtyCanvas?.(true, true);
        app.graph?.setDirtyCanvas?.(true, true);
      };
      const renderOptions = () => {
        select.innerHTML = "";
        const blank = document.createElement("option"); blank.value = ""; blank.textContent = "Select project..."; select.appendChild(blank);
        projects.forEach((project) => {
          const option = document.createElement("option"); option.value = project.name; option.textContent = project.name; select.appendChild(option);
        });
        if (selectedProject && !projects.some((project) => project.name === selectedProject)) {
          const option = document.createElement("option"); option.value = selectedProject; option.textContent = selectedProject; select.appendChild(option);
        }
        select.value = selectedProject;
        nameInput.value = selectedProject;
        pathInput.value = selectedPath;
      };
      const refreshProjects = async () => {
        try { projects = await fetchProjects(); renderOptions(); }
        catch (error) { setStatus(error.message || String(error), true); }
      };
      const loadBrowsedProject = async () => {
        const path = String(selectedPath || "").trim();
        if (!path) return false;
        try {
          const response = await api.fetchApi(`/minimax_director/projects/load?path=${encodeURIComponent(path)}`);
          const result = await response.json();
          if (result.status !== "success" || !result.project) return false;
          const document = result.project;
          setPath(document.project_path || path);
          setProject(document.project_name || selectedProject);
          projects = await fetchProjects();
          renderOptions();
          setStatus(`Loaded ${document.project_name || selectedProject}.`);
          return true;
        } catch (_) { return false; }
      };
      select.addEventListener("change", () => { setProject(select.value); setStatus(selectedProject ? `Selected ${selectedProject}.` : ""); });
      nameInput.addEventListener("input", () => setProject(nameInput.value));
      pathInput.addEventListener("input", () => setPath(pathInput.value));
      browse.addEventListener("click", async () => {
        browse.disabled = true;
        try {
          const response = await api.fetchApi("/minimax_director/projects/browse");
          const result = await response.json();
          if (result.status !== "success") throw new Error(result.message || "Could not browse for a folder");
          if (!result.path) return;
          setPath(result.path);
          if (!(await loadBrowsedProject())) setStatus("Folder selected. Enter a name and press CREATE to save here.");
        } catch (error) { setStatus(error.message || String(error), true); }
        finally { browse.disabled = false; }
      });
      refresh.addEventListener("click", () => { void refreshProjects(); });
      create.addEventListener("click", async () => {
        const project = String(nameInput.value || selectedProject || "").trim();
        if (!project) { setStatus("Enter a project name first.", true); nameInput.focus(); return; }
        create.disabled = true;
        try {
          const document = await createProject(project, selectedPath);
          setPath(document.project_path || selectedPath);
          setProject(document.project_name || project);
          projects = await fetchProjects(); renderOptions(); setStatus(`Created ${document.project_name || project}.`);
        } catch (error) { setStatus(error.message || String(error), true); }
        finally { create.disabled = false; }
      });

      row.appendChild(label); row.appendChild(select); row.appendChild(nameInput); row.appendChild(refresh); row.appendChild(create);
      pathRow.appendChild(pathLabel); pathRow.appendChild(pathInput); pathRow.appendChild(browse);
      container.appendChild(row); container.appendChild(pathRow); container.appendChild(status);
      renderOptions(); void refreshProjects();
    };
  },
});
