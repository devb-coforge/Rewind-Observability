import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("confirms and cancels, and closes on Escape", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const { rerender } = render(
      <ConfirmDialog
        open
        title="Rebuild the index?"
        description="Takes a while."
        confirmLabel="Rebuild index"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    expect(screen.getByRole("alertdialog", { name: "Rebuild the index?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rebuild index" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);

    rerender(
      <ConfirmDialog
        open
        title="Rebuild the index?"
        confirmLabel="Rebuild index"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it("renders nothing when closed", () => {
    render(
      <ConfirmDialog open={false} title="Hidden?" confirmLabel="OK" onConfirm={() => {}} onCancel={() => {}} />,
    );
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });
});
