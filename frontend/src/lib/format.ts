export function agentLabel(agent: string): string {
  if (agent === "claude_code") return "Claude Code";
  if (agent === "codex") return "Codex";
  return agent;
}

export function formatTokens(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toLocaleString();
}

export function formatCost(value: number | null | undefined, partial = false): string {
  if (value == null) return "—";
  const text = value > 0 && value < 0.01 ? "<$0.01" : `$${value.toFixed(value < 1 ? 3 : 2)}`;
  return partial ? `${text} partial` : text;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${Math.round(value * 100)}%`;
}
