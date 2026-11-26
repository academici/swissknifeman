// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import "../../../tests/setup";
import { ExportAction } from "./ExportAction";

const request = vi.hoisted(() => vi.fn());
const transport = { request };
const scope = { workspaceId: "workspace", projectId: "project" };
vi.mock("../../app/providers/ScopeProvider", () => ({ useScope: () => ({ scope }) }));
vi.mock("../../app/providers/AuthProvider", () => ({ useAuth: () => ({ transport }) }));

function objectUrls() {
  const createObjectURL = vi.fn(() => "blob:run");
  const revokeObjectURL = vi.fn();
  vi.stubGlobal("URL", class extends URL {
    static override createObjectURL = createObjectURL;
    static override revokeObjectURL = revokeObjectURL;
  });
  return { createObjectURL, revokeObjectURL };
}

const action = () => screen.getByRole("button", { name: "Export Markdown" });

it("downloads the returned Markdown blob and releases its URL", async () => {
  const urls = objectUrls();
  const data = new Blob(["# Отчёт\n"], { type: "text/markdown; charset=utf-8" });
  request.mockResolvedValue({ data, etag: '"sha256:example"' });
  let filename = "";
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    filename = this.download;
    expect(this.href).toBe("blob:run");
  });
  render(<ExportAction runId="run-a" />);
  fireEvent.click(action());
  await waitFor(() => expect(urls.revokeObjectURL).toHaveBeenCalledWith("blob:run"));
  expect(request).toHaveBeenCalledWith("GET", "/api/v1/runs/run-a/report.md", {
    responseType: "blob", signal: expect.any(AbortSignal),
  });
  expect(urls.createObjectURL).toHaveBeenCalledWith(data);
  expect(filename).toBe("run-run-a.md");
});

it("discards a late response after navigation and hides server error contents", async () => {
  const urls = objectUrls();
  let finish!: (value: unknown) => void;
  request.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const view = render(<ExportAction runId="old" />);
  fireEvent.click(action());
  view.rerender(<ExportAction runId="new" />);
  await act(async () => finish({ data: new Blob(["previous"], { type: "text/markdown" }) }));
  request.mockRejectedValueOnce(new Error("private server details"));
  fireEvent.click(action());
  expect((await screen.findByRole("alert")).textContent).toBe("Не удалось скачать отчёт.");
  expect(urls.createObjectURL).not.toHaveBeenCalled();
});

it("discards an in-flight download when the selected project changes", async () => {
  const urls = objectUrls();
  let finish!: (value: unknown) => void;
  request.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const view = render(<ExportAction runId="same-run" />);
  fireEvent.click(action());
  scope.projectId = "next-project";
  view.rerender(<ExportAction runId="same-run" />);
  await act(async () => finish({ data: new Blob(["old report"], { type: "text/markdown" }) }));
  expect(urls.createObjectURL).not.toHaveBeenCalled();
});

it("releases the URL when the browser fails to start the download", async () => {
  const urls = objectUrls();
  request.mockResolvedValueOnce({ data: new Blob(["# A"], { type: "text/markdown" }) });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => { throw new Error("failed"); });
  render(<ExportAction runId="run-b" />);
  fireEvent.click(action());
  expect(await screen.findByRole("alert")).toBeTruthy();
  await waitFor(() => expect(urls.revokeObjectURL).toHaveBeenCalledWith("blob:run"));
});
