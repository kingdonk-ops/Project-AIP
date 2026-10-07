import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom gaps that Radix (floating-ui, pointer capture, scroll) relies on.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
// Node-environment tests (tokens, lint, exports) share this setup file but have no DOM.
if (typeof Element !== "undefined") {
  globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
  Element.prototype.scrollIntoView ??= function scrollIntoView() {};
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};

  afterEach(() => {
    cleanup();
  });
}
