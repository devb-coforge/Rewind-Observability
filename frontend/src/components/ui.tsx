import { ChevronDown, Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, Ref, SelectHTMLAttributes } from "react";
import { AgentIcon } from "./AgentIcon";
import { agentLabel } from "../lib/format";
import { cn } from "../lib/cn";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

const buttonVariants: Record<ButtonVariant, string> = {
  primary: "bg-ink text-bg hover:bg-ink/90 shadow-card",
  secondary: "border border-line-strong bg-surface2 text-ink hover:bg-surface3 shadow-card",
  ghost: "text-muted hover:bg-surface2 hover:text-ink",
  danger: "text-danger hover:bg-danger/10",
};

const buttonSizes: Record<ButtonSize, string> = {
  sm: "h-7 gap-1.5 px-2.5 text-xs",
  md: "h-8 gap-2 px-3 text-[13px]",
};

export function Button({
  variant = "secondary",
  size = "md",
  className,
  type = "button",
  ref,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  ref?: Ref<HTMLButtonElement>;
}) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-md font-medium transition-colors disabled:pointer-events-none disabled:opacity-50",
        buttonVariants[variant],
        buttonSizes[size],
        className,
      )}
      {...props}
    />
  );
}

const fieldBase =
  "h-8 rounded-md border border-line bg-surface text-[13px] text-ink shadow-card transition-colors placeholder:text-subtle hover:border-line-strong focus:border-accent/60 focus:outline-none focus:ring-2 focus:ring-accent/20";

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className={cn("relative", className)}>
      <select className={cn(fieldBase, "w-full cursor-pointer appearance-none truncate pl-2.5 pr-8")} {...props}>
        {children}
      </select>
      <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-subtle" />
    </div>
  );
}

export function AgentOptions() {
  return (
    <>
      <option value="">All agents</option>
      <option value="claude_code">Claude Code</option>
      <option value="codex">Codex</option>
      <option value="cursor">Cursor</option>
    </>
  );
}

export function Input({ className, icon, ...props }: InputHTMLAttributes<HTMLInputElement> & { icon?: ReactNode }) {
  if (!icon) return <input className={cn(fieldBase, "px-2.5", className)} {...props} />;
  return (
    <div className={cn("relative", className)}>
      <span aria-hidden="true" className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-subtle">
        {icon}
      </span>
      <input className={cn(fieldBase, "w-full pl-8 pr-2.5")} {...props} />
    </div>
  );
}

export function Checkbox({ label, className, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className={cn("inline-flex cursor-pointer select-none items-center gap-2 text-[13px] text-muted hover:text-ink", className)}>
      <input type="checkbox" className="size-3.5 cursor-pointer rounded accent-[rgb(var(--accent))]" {...props} />
      {label}
    </label>
  );
}

type Tone = "neutral" | "accent" | "danger" | "warn" | "ok";

const badgeTones: Record<Tone, string> = {
  neutral: "border-line-strong bg-surface2 text-muted",
  accent: "border-accent/25 bg-accent/10 text-accent",
  danger: "border-danger/25 bg-danger/10 text-danger",
  warn: "border-warn/25 bg-warn/10 text-warn",
  ok: "border-ok/25 bg-ok/10 text-ok",
};

export function Badge({ tone = "neutral", className, children }: { tone?: Tone; className?: string; children: ReactNode }) {
  return (
    <span className={cn("inline-flex h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded border px-1.5 text-2xs font-medium", badgeTones[tone], className)}>
      {children}
    </span>
  );
}

export function AgentBadge({ agent }: { agent: string }) {
  return (
    <span title={agentLabel(agent)} className="inline-flex h-5 shrink-0 items-center justify-center rounded border border-line-strong bg-surface2 px-1.5 text-2xs font-medium text-muted">
      <AgentIcon agent={agent} className="size-3" />
      <span className="sr-only">{agentLabel(agent)}</span>
    </span>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("rounded-lg border border-line bg-surface shadow-card", className)}>{children}</div>;
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 pb-5">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        {description ? <p className="mt-1 text-[13px] text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className="h-full overflow-auto">
      <div className={cn("mx-auto w-full max-w-7xl px-5 py-6 md:px-8 md:py-8", className)}>{children}</div>
    </div>
  );
}

export function Toolbar({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mb-5 flex flex-wrap items-center gap-2", className)}>{children}</div>;
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-2.5 flex items-center justify-between gap-2">
      <h2 className="text-2xs font-semibold uppercase tracking-[0.08em] text-subtle">{children}</h2>
      {aside}
    </div>
  );
}

export function EmptyState({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-line px-6 py-12 text-center">
      {icon ? <div className="mb-3 text-subtle">{icon}</div> : null}
      <p className="text-[13px] font-medium text-ink">{title}</p>
      {description ? <p className="mt-1 max-w-sm text-[13px] text-muted">{description}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-[13px] text-muted">
      <Loader2 aria-hidden="true" className="size-4 animate-spin" />
      {label}
    </div>
  );
}

export function ErrorText({ children }: { children: ReactNode }) {
  return (
    <p className="mb-4 rounded-md border border-danger/25 bg-danger/10 px-3 py-2 text-[13px] text-danger">{children}</p>
  );
}

export const th = "h-9 whitespace-nowrap px-3 text-left text-2xs font-medium uppercase tracking-[0.06em] text-subtle first:pl-4 last:pr-4";
export const td = "h-11 px-3 first:pl-4 last:pr-4";
