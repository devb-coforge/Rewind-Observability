import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Link, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { NoteEditor } from "./NoteEditor";

function renderEditor(onSave: (text: string) => Promise<{ text: string; updated_at: string | null }>) {
  const router = createMemoryRouter([
    {
      path: "/",
      element: (
        <div>
          <Link to="/away">Leave</Link>
          <NoteEditor initial={{ text: "saved note", updated_at: "2026-01-01T00:00:00.000Z" }} onSave={onSave} />
        </div>
      ),
    },
    { path: "/away", element: <div>Away</div> },
  ]);
  render(<RouterProvider router={router} />);
  return router;
}

describe("NoteEditor", () => {
  it("saves edited text", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn(async (text: string) => ({ text, updated_at: "2026-01-02T00:00:00.000Z" }));
    renderEditor(onSave);
    const box = screen.getByRole("textbox", { name: "Session note" });
    await user.clear(box);
    await user.type(box, "updated");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).toHaveBeenCalledWith("updated");
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("keeps the draft when saving fails", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn(async () => {
      throw new Error("disk full");
    });
    renderEditor(onSave);
    const box = screen.getByRole("textbox", { name: "Session note" });
    await user.type(box, "!");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Could not save. The note is still here.")).toBeInTheDocument();
    expect(box).toHaveValue("saved note!");
  });

  it("asks before leaving with unsaved edits", async () => {
    const user = userEvent.setup();
    renderEditor(async (text) => ({ text, updated_at: null }));
    await user.type(screen.getByRole("textbox", { name: "Session note" }), " more");
    await user.click(screen.getByRole("link", { name: "Leave" }));
    expect(await screen.findByRole("dialog", { name: "Unsaved note" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stay" }));
    expect(screen.getByRole("textbox", { name: "Session note" })).toHaveValue("saved note more");
  });

  it("clears a saved note", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn(async (text: string) => ({ text, updated_at: null }));
    renderEditor(onSave);
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(onSave).toHaveBeenCalledWith("");
  });
});
