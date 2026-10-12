import { useEffect, useState } from "react";
import { useBlocker } from "react-router-dom";
import type { Note } from "../api/types";

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
    if (dirty && !window.confirm("Discard unsaved edits and clear the note?")) return;
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
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium">Session note</h3>
        <span className={`text-xs ${status === "error" ? "text-danger" : "text-muted"}`}>{statusText}</span>
      </div>
      <textarea
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          if (status === "error") setStatus("idle");
        }}
        rows={6}
        className="w-full rounded-md border border-line bg-[#10120c] px-3 py-2 text-sm text-ink"
        aria-label="Session note"
      />
      {error ? <p className="text-xs text-danger">{error}</p> : null}
      {blocker.state === "blocked" ? (
        <div role="dialog" aria-label="Unsaved note" className="space-y-2 rounded-md border border-line bg-surface2 p-3">
          <p className="text-sm">Discard unsaved note edits?</p>
          <div className="flex gap-2">
            <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm" onClick={() => blocker.proceed()}>
              Discard
            </button>
            <button type="button" className="rounded-md bg-accent px-3 py-1.5 text-sm text-[#1a1608]" onClick={() => blocker.reset()}>
              Stay
            </button>
          </div>
        </div>
      ) : null}
      <div className="flex gap-2">
        <button
          type="button"
          className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-[#1a1608] disabled:opacity-50"
          disabled={!dirty || status === "saving"}
          onClick={() => void save(text)}
        >
          Save
        </button>
        <button
          type="button"
          className="rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-50"
          disabled={status === "saving" || (!text && !savedText)}
          onClick={clear}
        >
          Clear
        </button>
      </div>
    </div>
  );
}
