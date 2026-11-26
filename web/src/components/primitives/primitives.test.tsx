import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";
import { Dialog } from "./Dialog";
import { Menu } from "./Menu";
import { Popover } from "./Popover";
import { Tabs } from "./Tabs";
import { Tooltip } from "./Tooltip";

describe("Dialog", () => {
  it.each(["close button", "Escape"])("closes with %s and returns focus", async (method) => {
    const user = userEvent.setup();
    function Example() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Open details</button>
          <Dialog open={open} title={"Details\u061c\u202e\t\u009f"} onClose={() => setOpen(false)}>
            <label>Filter <input /></label>
          </Dialog>
        </>
      );
    }
    render(<Example />);
    const trigger = screen.getByRole("button", { name: "Open details" });
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Details\\u061c\\u202e\\u0009\\u009f" });
    const input = within(dialog).getByRole("textbox", { name: "Filter" });
    const close = within(dialog).getByRole("button", { name: "Закрыть" });
    await waitFor(() => expect(document.activeElement).toBe(input));
    await user.tab();
    expect(document.activeElement).toBe(close);
    await user.tab();
    await waitFor(() => expect(document.activeElement).toBe(input));

    if (method === "Escape") await user.keyboard("{Escape}");
    else await user.click(close);
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });
});

describe("ConfirmDialog", () => {
  it.each(["Cancel", "Escape"])("starts on Cancel for destructive actions and closes with %s", async (method) => {
    const user = userEvent.setup();
    const confirm = vi.fn();
    function Example() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Archive</button>
          <ConfirmDialog open={open} title="Archive workspace" destructive requireReason
            onClose={() => setOpen(false)} onConfirm={confirm} />
        </>
      );
    }
    render(<Example />);
    const trigger = screen.getByRole("button", { name: "Archive" });
    expect(screen.queryByRole("alertdialog")).toBeNull();
    await user.click(trigger);
    const dialog = screen.getByRole("alertdialog", { name: "Archive workspace" });
    const cancel = within(dialog).getByRole("button", { name: "Отмена" });
    await waitFor(() => expect(document.activeElement).toBe(cancel));

    if (method === "Escape") await user.keyboard("{Escape}");
    else await user.click(cancel);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(trigger));
    expect(confirm).not.toHaveBeenCalled();
  });

  it("escapes the supplied labels and rejects empty and whitespace-only reasons", async () => {
    const user = userEvent.setup();
    const confirm = vi.fn();
    render(
      <ConfirmDialog
        open
        title={"Archive\u202e"}
        description={"This is permanent\t"}
        confirmLabel={"Confirm\u2066"}
        requireReason
        onClose={vi.fn()}
        onConfirm={confirm}
      />,
    );
    const dialog = screen.getByRole("alertdialog", {
      name: "Archive\\u202e",
      description: "This is permanent\\u0009",
    });
    const submit = within(dialog).getByRole("button", { name: "Confirm\\u2066" });
    const reason = within(dialog).getByRole("textbox", { name: "Причина" });
    await user.click(submit);
    await user.type(reason, "   ");
    await user.click(submit);
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog")).toBe(dialog);

    await user.type(reason, "No longer in use  ");
    await user.click(submit);
    expect(confirm).toHaveBeenCalledExactlyOnceWith("No longer in use");
  });
});

describe("Tabs", () => {
  it("escapes accessible labels and selects the focused panel with arrow keys", async () => {
    const user = userEvent.setup();
    const tabs = [
      { id: "summary", label: "Summary\u202e", content: "Summary panel" },
      { id: "details", label: "Details\t", content: "Details panel" },
    ];
    function Example() {
      const [active, setActive] = useState("summary");
      return <Tabs label={"Run\u2066"} tabs={tabs} active={active} onSelect={setActive} />;
    }
    render(<Example />);
    const tablist = screen.getByRole("tablist", { name: "Run\\u2066" });
    const summary = within(tablist).getByRole("tab", { name: "Summary\\u202e", selected: true });
    const details = within(tablist).getByRole("tab", { name: "Details\\u0009", selected: false });
    expect(screen.getByRole("tabpanel", { name: "Summary\\u202e" }).textContent).toBe("Summary panel");
    await user.tab();
    expect(document.activeElement).toBe(summary);

    await user.keyboard("{ArrowRight}");
    expect(document.activeElement).toBe(details);
    expect(details.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tabpanel", { name: "Details\\u0009" }).textContent).toBe("Details panel");
    expect(screen.queryByText("Summary panel")).toBeNull();

    await user.keyboard("{ArrowRight}");
    expect(document.activeElement).toBe(summary);
    expect(summary.getAttribute("aria-selected")).toBe("true");
  });
});

describe("Menu", () => {
  it("opens from the keyboard, escapes labels, and invokes the selected action", async () => {
    const user = userEvent.setup();
    const copy = vi.fn();
    const archive = vi.fn();
    render(<Menu label={"Actions\u202e"} items={[
      { id: "copy", label: "Copy", onSelect: copy },
      { id: "archive", label: "Archive\t", onSelect: archive },
    ]} />);
    const trigger = screen.getByRole("button", { name: "Actions\\u202e" });
    expect(screen.queryByRole("menu")).toBeNull();
    await user.tab();
    await user.keyboard("{ArrowDown}");
    const menu = screen.getByRole("menu", { name: "Actions\\u202e" });
    await waitFor(() => expect(document.activeElement).toBe(within(menu).getByRole("menuitem", { name: "Copy" })));
    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(within(menu).getByRole("menuitem", { name: "Archive\\u0009" }));
    await user.keyboard("{Enter}");
    expect(archive).toHaveBeenCalledTimes(1);
    expect(copy).not.toHaveBeenCalled();
    expect(screen.queryByRole("menu")).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });
});

describe("Popover", () => {
  it("opens from its escaped trigger label and returns focus on Escape", async () => {
    const user = userEvent.setup();
    render(
      <Popover label={"Filters\u202e"}>
        <label>Search <input /></label>
      </Popover>,
    );
    const trigger = screen.getByRole("button", { name: "Filters\\u202e" });
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(trigger);
    const popup = screen.getByRole("dialog", { name: "Filters\\u202e" });
    const search = within(popup).getByRole("textbox", { name: "Search" });
    await waitFor(() => expect(document.activeElement).toBe(search));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });
});

describe("Tooltip", () => {
  it("labels the trigger with escaped text and dismisses the visual hint on Escape", async () => {
    const user = userEvent.setup();
    render(
      <Tooltip label={"Copy identifier\u202e"}>
        <button type="button"><span aria-hidden="true">⧉</span></button>
      </Tooltip>,
    );
    const name = "Copy identifier\\u202e";
    const trigger = screen.getByRole("button", { name });
    expect(screen.queryByText(name)).toBeNull();
    await user.tab();
    expect(await screen.findByText(name)).toBeTruthy();

    await user.keyboard("{Escape}");
    expect(screen.queryByText(name)).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});
