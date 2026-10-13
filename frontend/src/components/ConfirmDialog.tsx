import { TriangleAlert } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "../lib/cn";
import { Button } from "./ui";

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  tone = "default",
  icon,
  pending = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
  icon?: ReactNode;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const danger = tone === "danger";

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onCancel();
      }
    };
    document.addEventListener("keydown", onKey, true);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onCancel]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-bg/70 p-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !pending) onCancel();
      }}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        className="w-full max-w-sm rounded-lg border border-line bg-surface p-5 shadow-pop"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className={cn(
              "grid size-8 shrink-0 place-items-center rounded-md border",
              danger
                ? "border-danger/25 bg-danger/10 text-danger"
                : "border-line-strong bg-surface2 text-muted",
            )}
          >
            {icon ?? (danger ? <TriangleAlert className="size-4" /> : null)}
          </span>
          <div className="min-w-0">
            <h2 id={titleId} className="text-sm font-semibold tracking-tight">
              {title}
            </h2>
            {description ? (
              <p id={descriptionId} className="mt-1 text-[13px] leading-relaxed text-muted">
                {description}
              </p>
            ) : null}
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button ref={cancelRef} disabled={pending} onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            variant="primary"
            autoFocus={!danger}
            disabled={pending}
            onClick={onConfirm}
            className={cn(danger && "bg-danger text-bg hover:bg-danger/90")}
          >
            {pending ? "Working…" : confirmLabel}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
