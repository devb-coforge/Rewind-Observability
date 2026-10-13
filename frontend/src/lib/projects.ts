import type { Project } from "../api/types";

export function projectFilters(selection: string) {
  return {
    project: selection.startsWith("id:") ? selection.slice(3) : "",
    project_cwd: selection.startsWith("path:") ? selection.slice(5) : "",
  };
}

// Paths are normalized by the backend. Missing paths must not merge unrelated workspaces.
export function projectGroupKey(cwd: string | null, projectId: string): string {
  return cwd ? `path:${cwd}` : `id:${projectId}`;
}

export function groupProjectsByPath(projects: Project[]) {
  const groups = new Map<string, { key: string; name: string; cwd: string | null; projects: Project[] }>();
  for (const project of projects) {
    const cwd = project.group_cwd || project.cwd;
    const key = projectGroupKey(cwd, project.project_id);
    const group = groups.get(key);
    if (group) {
      group.projects.push(project);
      // A subdirectory checkout keeps the name recorded at the worktree root.
      if (project.cwd && project.cwd === cwd) group.name = project.name;
    } else {
      groups.set(key, { key, name: project.name, cwd, projects: [project] });
    }
  }
  return [...groups.values()];
}
