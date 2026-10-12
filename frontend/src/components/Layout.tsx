import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../api/client";

const links = [
  { to: "/", label: "Sessions", end: true },
  { to: "/analytics", label: "Analytics", end: false },
  { to: "/search", label: "Search", end: false },
  { to: "/benchmark", label: "Benchmark", end: false },
  { to: "/sources", label: "Sources", end: false },
];

export function Layout() {
  const queryClient = useQueryClient();
  const rescan = useMutation({
    mutationFn: () => api.reindex(false),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  return (
    <div className="flex h-screen flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-line px-4">
        <div>
          <div className="text-sm font-semibold tracking-wide">Obs</div>
          <div className="text-xs text-muted">Local agent transcripts</div>
        </div>
        <button
          type="button"
          className="rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-50"
          disabled={rescan.isPending}
          onClick={() => rescan.mutate()}
        >
          {rescan.isPending ? "Scanning…" : "Rescan"}
        </button>
      </header>
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <nav className="flex shrink-0 gap-1 overflow-x-auto border-b border-line px-2 py-2 md:w-44 md:flex-col md:border-b-0 md:border-r md:px-3 md:py-4">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm ${isActive ? "bg-surface2 text-accent" : "text-muted hover:text-ink"}`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <main className="min-h-0 min-w-0 flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
