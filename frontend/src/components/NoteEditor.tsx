import { useEffect, useState } from "react";
import { useBlocker } from "react-router-dom";
import type { Note } from "../api/types";
import { cn } from "../lib/cn";
import { ConfirmDialog } from "./ConfirmDialog";
import { Button } from "./ui";

export function NoteEditor({
  initial,
  onSave,
}: {
  initial: Note;
  onSave: (text: string) => Promise<Note>;
}) {
  const [text, setText] = useState(initial.text);
  const [savedText, setSavedText] = useState(initial.text);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [error, setError] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const dirty = text !== savedText;

  useEffect(() => {
    setText(initial.text);
    setSavedText(initial.text);
    setStatus("idle");
  }, [initial.text, initial.updated_at]);

  useEffect(() => {
    if (!dirty) return;
    const onLeave = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, [dirty]);

  const blocker = useBlocker(dirty);

  async function save(next: string) {
    setStatus("saving");
    setError("");
    try {
      const saved = await onSave(next);
      setText(saved.text);
      setSavedText(saved.text);
      setStatus("saved");
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Could not save");
    }
  }

  function clear() {
    if (dirty) {
      setConfirmClear(true);
      return;
    }
    void save("");
  }

  const statusText =
    status === "saving"
      ? "Saving…"
      : status === "error"
        ? "Could not save. The note is still here."
        : dirty
          ? "Unsaved changes"
          : initial.updated_at || status === "saved"
            ? "Saved"
            : "No note yet";

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-2xs font-semibold uppercase tracking-[0.08em] text-subtle">Session note</h3>
        <span className={cn("flex items-center gap-1.5 text-2xs", status === "error" ? "text-danger" : "text-subtle")}>
          {dirty && status !== "error" ? <span aria-hidden="true" className="size-1.5 rounded-full bg-warn" /> : null}
          {statusText}
        </span>
      </div>
      <textarea
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          if (status === "error") setStatus("idle");
        }}
        rows={5}
        placeholder="Add context, findings, or follow-ups…"
        className="block w-full resize-y rounded-md border border-line bg-surface px-3 py-2 text-[13px] leading-relaxed text-ink shadow-card placeholder:text-subtle hover:border-line-strong focus:border-accent/60 focus:outline-none focus:ring-2 focus:ring-accent/20"
        aria-label="Session note"
      />
      {error ? <p className="text-xs text-danger">{error}</p> : null}
      {blocker.state === "blocked" ? (
        <div role="dialog" aria-label="Unsaved note" className="space-y-2.5 rounded-md border border-warn/30 bg-warn/[0.06] p-3">
          <p className="text-[13px]">Discard unsaved note edits?</p>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => blocker.proceed()}>
              Discard
            </Button>
            <Button size="sm" variant="primary" onClick={() => blocker.reset()}>
              Stay
            </Button>
          </div>
        </div>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" disabled={status === "saving" || (!text && !savedText)} onClick={clear}>
          Clear
        </Button>
        <Button size="sm" variant="primary" disabled={!dirty || status === "saving"} onClick={() => void save(text)}>
          Save
        </Button>
      </div>
      <ConfirmDialog
        open={confirmClear}
        title="Discard unsaved edits?"
        description="Clearing will discard your unsaved edits and empty the note."
        confirmLabel="Discard edits"
        tone="danger"
        onConfirm={() => {
          setConfirmClear(false);
          void save("");
        }}
        onCancel={() => setConfirmClear(false)}
      />
    </div>
  );
}
