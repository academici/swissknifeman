import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

// Node 26's fetch builds Response.blob() results from the global Blob, which jsdom replaces with a Blob that
// has no promise readers. Browsers have them, so the tests give jsdom's Blob the same methods.
function readBlob(blob: Blob): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error ?? new Error("Blob read failed"));
    reader.readAsArrayBuffer(blob);
  });
}

if (typeof Blob.prototype.arrayBuffer !== "function") {
  Blob.prototype.arrayBuffer = function arrayBuffer(this: Blob) {
    return readBlob(this);
  };
}
if (typeof Blob.prototype.bytes !== "function") {
  Blob.prototype.bytes = async function bytes(this: Blob) {
    return new Uint8Array(await readBlob(this));
  };
}
if (typeof Blob.prototype.text !== "function") {
  Blob.prototype.text = async function text(this: Blob) {
    return new TextDecoder().decode(await readBlob(this));
  };
}

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  sessionStorage.clear();
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
