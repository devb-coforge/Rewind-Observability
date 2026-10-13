import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Database, FlaskConical, List, RefreshCw, Search } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../api/client";
import { cn } from "../lib/cn";
import { Button } from "./ui";

const links = [
  { to: "/", label: "Sessions", end: true, icon: List },
  { to: "/analytics", label: "Analytics", end: false, icon: BarChart3 },
  { to: "/search", label: "Search", end: false, icon: Search },
  { to: "/evals", label: "Evals", end: false, icon: FlaskConical },
  { to: "/sources", label: "Sources", end: false, icon: Database },
];

export function Layout() {
  const { pathname } = useLocation();
  const queryClient = useQueryClient();
  const rescan = useMutation({
    mutationFn: () => api.reindex(false),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  return (
    <div className="flex h-screen flex-col md:flex-row">
      <aside className="flex shrink-0 flex-col border-b border-line bg-surface/60 md:w-56 md:border-b-0 md:border-r">
        <div className="flex h-14 items-center justify-between gap-3 px-4 md:h-auto md:px-4 md:pb-4 md:pt-5">
          <div className="flex items-center gap-2.5">
            <img src="/favicon.svg" alt="" aria-hidden="true" className="size-7 rounded-md shadow-card" />
            <div className="leading-tight">
              <div className="text-[13px] font-semibold tracking-tight">Rewind</div>
              <div className="text-2xs text-subtle">Agent transcripts</div>
            </div>
          </div>
          <Button size="sm" className="md:hidden" disabled={rescan.isPending} onClick={() => rescan.mutate()}>
            <RefreshCw aria-hidden="true" className={cn("size-3.5", rescan.isPending && "animate-spin")} />
            {rescan.isPending ? "Scanning…" : "Rescan"}
          </Button>
        </div>
        <nav className="flex gap-0.5 overflow-x-auto px-2 pb-2 md:flex-1 md:flex-col md:px-3 md:pb-0">
          {links.map(({ to, label, end, icon: Icon }) => {
            const inSession = to === "/" && pathname.startsWith("/sessions/");
            return (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    "group flex h-8 shrink-0 items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium transition-colors",
                    isActive || inSession ? "bg-surface3 text-ink shadow-card" : "text-muted hover:bg-surface2 hover:text-ink",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon aria-hidden="true" className={cn("size-4", isActive || inSession ? "text-ink" : "text-subtle group-hover:text-muted")} />
                    {label}
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>
        <div className="hidden border-t border-line p-3 md:block">
          <Button className="w-full" disabled={rescan.isPending} onClick={() => rescan.mutate()}>
            <RefreshCw aria-hidden="true" className={cn("size-3.5", rescan.isPending && "animate-spin")} />
            {rescan.isPending ? "Scanning…" : "Rescan"}
          </Button>
          {rescan.isError ? <p className="mt-2 text-2xs text-danger">{(rescan.error as Error).message}</p> : null}
        </div>
      </aside>
      <main className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
