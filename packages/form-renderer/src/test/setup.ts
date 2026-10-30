import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom gaps that Radix (floating-ui, pointer capture, scroll) relies on (same as packages/ui).
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
if (typeof Element !== "undefined") {
  globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
  Element.prototype.scrollIntoView ??= function scrollIntoView() {};
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};

  afterEach(() => {
    cleanup();
  });
}
