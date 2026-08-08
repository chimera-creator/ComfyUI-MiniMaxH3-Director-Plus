// MiniMax H3 Director Project Plus
// Selects the root folder that contains named project folders and broadcasts the
// selected project configuration to connected authoring nodes.

const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;

const PROJECT_STYLES = `
  .mmxd-project-wrapper { width:100%; box-sizing:border-box; color:#d8d8d8; font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
  .mmxd-project-row { display:flex; align-items:center; gap:5px; flex-wrap:wrap; }
  .mmxd-project-label { color:#888; font-size:9px; font-weight:700; letter-spacing:.5px; }
  .mmxd-project-select, .mmxd-project-name, .mmxd-project-path { min-width:0; height:24px; box-sizing:border-box; background:#111; color:#ddd; border:1px solid #3a3a3a; border-radius:4px; padding:2px 5px; font-size:10px; font-family:inherit; outline:none; }
  .mmxd-project-select { flex:1 1 150px; }
  .mmxd-project-name { flex:1 1 150px; }
  .mmxd-project-path { flex:1 1 280px; color:#aaa; }
  .mmxd-project-button { height:24px; padding:2px 8px; background:#252525; color:#bdbdbd; border:1px solid #444; border-radius:4px; font-size:8px; font-weight:700; cursor:pointer; }
  .mmxd-project-button:hover { color:#fff; border-color:#777; }
  .mmxd-project-status { color:#666; font-size:9px; min-height:13px; width:100%; margin-top:4px; }
  .mmxd-project-help { color:#777; font-size:9px; line-height:1.3; width:100%; margin-top:3px; }
`;

let styleEl = document.getElementById("minimax-h3-project-plus-styles");
if (!styleEl) {
  styleEl = document.createElement("style");
  styleEl.id = "minimax-h3-project-plus-styles";
  document.head.appendChild(styleEl);
}
styleEl.textContent = PROJECT_STYLES;

async function fetchProjects(projectsPath = "") {
  const query = projectsPath ? `?projects_path=${encodeURIComponent(projectsPath)}` : "";
  const response = await api.fetchApi(`/minimax_director/projects${query}`);
  const result = await response.json();
  if (result.status !== "success") throw new Error(result.message || "Could not list projects");
  return Array.isArray(result.projects) ? result.projects : [];
}

async function loadProject(project, projectsPath = "") {
  const query = `name=${encodeURIComponent(project)}&projects_path=${encodeURIComponent(projectsPath || "")}`;
  const response = await api.fetchApi(`/minimax_director/projects/load?${query}`);
  const result = await response.json();
  if (result.status !== "success") throw new Error(result.message || "Could not load project");
  return result.project || {};
}

async function createProject(project, projectsPath) {
  const response = await api.fetchApi("/minimax_director/projects/create", {
    method: "POST", body: JSON.stringify({ project, projects_path: projectsPath }),
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
      const projectsPathWidget = node.widgets?.find((widget) => widget.name === "projects_path");
      const legacyPathWidget = node.widgets?.find((widget) => widget.name === "project_path");
      for (const widget of [projectWidget, projectsPathWidget, legacyPathWidget]) {
        if (!widget) continue;
        widget.hidden = true;
        widget.options = { ...(widget.options || {}), hidden: true };
        widget.computeSize = () => [0, -4];
      }

      const container = document.createElement("div");
      container.className = "mmxd-project-wrapper";
      const uiWidget = node.addDOMWidget("project_ui", "project_ui", container, {
        getValue: () => "", setValue: () => {},
      });
      uiWidget.serialize = false;
      uiWidget.computeSize = (width) => [Math.max(10, width || node.size?.[0] || 520), 92];

      let projects = [];
      let selectedProject = String(node.properties?.project_name || projectWidget?.value || "");
      let selectedRoot = String(node.properties?.projects_path || projectsPathWidget?.value || "");
      let selectedProjectPath = String(node.properties?.project_path || "");

      const row = document.createElement("div"); row.className = "mmxd-project-row";
      const label = document.createElement("span"); label.className = "mmxd-project-label"; label.textContent = "PROJECT";
      const select = document.createElement("select"); select.className = "mmxd-project-select";
      const nameInput = document.createElement("input"); nameInput.className = "mmxd-project-name"; nameInput.placeholder = "New or existing project name";
      const rootRow = document.createElement("div"); rootRow.className = "mmxd-project-row";
      const rootLabel = document.createElement("span"); rootLabel.className = "mmxd-project-label"; rootLabel.textContent = "PROJECTS FOLDER";
      const rootInput = document.createElement("input"); rootInput.className = "mmxd-project-path"; rootInput.placeholder = "Folder that stores named project folders";
      const browse = document.createElement("button"); browse.className = "mmxd-project-button"; browse.textContent = "BROWSE";
      const refresh = document.createElement("button"); refresh.className = "mmxd-project-button"; refresh.textContent = "REFRESH";
      const create = document.createElement("button"); create.className = "mmxd-project-button"; create.textContent = "CREATE / LOAD";
      const status = document.createElement("div"); status.className = "mmxd-project-status";
      const help = document.createElement("div"); help.className = "mmxd-project-help";
      help.textContent = "Each project is stored as <Projects folder>/<project name>/Cast, Wardrobe, and Sets. Connect PROJECT DATA to authoring nodes to inherit it.";

      const setStatus = (message, error = false) => {
        status.textContent = message || "";
        status.style.color = error ? "#d86f6f" : "#666";
      };
      const broadcast = (document) => {
        const project = String(document?.project_name || selectedProject || "").trim();
        const projectPath = String(document?.project_path || selectedProjectPath || "").trim();
        const root = String(document?.projects_path || selectedRoot || "").trim();
        for (const other of app.graph?._nodes || []) {
          const input = other.inputs?.find((item) => item.name === "project");
          const link = input?.link != null ? app.graph.links?.[input.link] : null;
          if (link?.origin_id === node.id) {
            other._mmxProjectRefresh?.(project, projectPath, root, document);
          }
        }
      };
      const setConfig = (document) => {
        selectedProject = String(document?.project_name || selectedProject || "").trim();
        selectedProjectPath = String(document?.project_path || selectedProjectPath || "").trim();
        selectedRoot = String(document?.projects_path || selectedRoot || "").trim();
        nameInput.value = selectedProject;
        rootInput.value = selectedRoot;
        if (projectWidget) projectWidget.value = selectedProject;
        if (projectsPathWidget) projectsPathWidget.value = selectedRoot;
        if (legacyPathWidget) legacyPathWidget.value = "";
        node.properties = { ...(node.properties || {}),
          project_name: selectedProject, project_path: selectedProjectPath,
          projects_path: selectedRoot, project_root: selectedRoot };
        renderOptions();
        node.setDirtyCanvas?.(true, true);
        app.graph?.setDirtyCanvas?.(true, true);
        broadcast(document || { project_name: selectedProject, project_path: selectedProjectPath, projects_path: selectedRoot });
      };
      const renderOptions = () => {
        select.innerHTML = "";
        const blank = document.createElement("option"); blank.value = ""; blank.textContent = "Select project..."; select.appendChild(blank);
        for (const project of projects || []) {
          const option = document.createElement("option"); option.value = project.name; option.textContent = project.name; select.appendChild(option);
        }
        if (selectedProject && !projects.some((project) => project.name === selectedProject)) {
          const option = document.createElement("option"); option.value = selectedProject; option.textContent = selectedProject; select.appendChild(option);
        }
        select.value = selectedProject;
      };
      const refreshProjects = async () => {
        try {
          projects = await fetchProjects(selectedRoot);
          renderOptions();
          if (selectedProject) setStatus(`Project: ${selectedProject}`);
        } catch (error) { setStatus(error.message || String(error), true); }
      };
      const loadSelectedProject = async () => {
        const project = String(select.value || nameInput.value || "").trim();
        if (!project) return;
        try {
          const document = await loadProject(project, selectedRoot);
          setConfig(document);
          setStatus(`Loaded ${project}.`);
        } catch (error) { setStatus(error.message || String(error), true); }
      };

      select.addEventListener("change", () => { void loadSelectedProject(); });
      nameInput.addEventListener("input", () => {
        selectedProject = nameInput.value.trim();
        if (projectWidget) projectWidget.value = selectedProject;
        node.properties = { ...(node.properties || {}), project_name: selectedProject };
      });
      rootInput.addEventListener("change", () => {
        selectedRoot = rootInput.value.trim();
        if (projectsPathWidget) projectsPathWidget.value = selectedRoot;
        node.properties = { ...(node.properties || {}), projects_path: selectedRoot, project_root: selectedRoot };
        void refreshProjects();
      });
      browse.addEventListener("click", async () => {
        browse.disabled = true;
        try {
          const response = await api.fetchApi("/minimax_director/projects/browse");
          const result = await response.json();
          if (result.status !== "success") throw new Error(result.message || "Could not browse for a folder");
          if (result.path) {
            selectedRoot = String(result.path);
            rootInput.value = selectedRoot;
            if (projectsPathWidget) projectsPathWidget.value = selectedRoot;
            node.properties = { ...(node.properties || {}), projects_path: selectedRoot, project_root: selectedRoot };
            await refreshProjects();
            setStatus("Projects folder selected. Choose or create a project.");
          }
        } catch (error) { setStatus(error.message || String(error), true); }
        finally { browse.disabled = false; }
      });
      refresh.addEventListener("click", () => { void refreshProjects(); });
      create.addEventListener("click", async () => {
        const project = String(nameInput.value || selectedProject || "").trim();
        if (!project) { setStatus("Enter a project name first.", true); nameInput.focus(); return; }
        if (!selectedRoot) { setStatus("Browse for the Projects folder first.", true); rootInput.focus(); return; }
        create.disabled = true;
        try {
          const document = await createProject(project, selectedRoot);
          setConfig(document);
          projects = await fetchProjects(selectedRoot);
          renderOptions();
          setStatus(`Ready: ${document.project_name}.`);
        } catch (error) { setStatus(error.message || String(error), true); }
        finally { create.disabled = false; }
      });

      row.appendChild(label); row.appendChild(select); row.appendChild(nameInput); row.appendChild(refresh); row.appendChild(create);
      rootRow.appendChild(rootLabel); rootRow.appendChild(rootInput); rootRow.appendChild(browse);
      container.appendChild(row); container.appendChild(rootRow); container.appendChild(help); container.appendChild(status);
      rootInput.value = selectedRoot; nameInput.value = selectedProject;
      renderOptions(); void refreshProjects();
    };
  },
});
