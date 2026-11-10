/**
 * Undo and redo over schema snapshots (FORMS-11). At most `HISTORY_LIMIT` steps are kept. Edits that
 * carry the same `group` (one input of one item) within `GROUP_MS` of the last one replace the
 * newest snapshot instead of adding a step, so typing a word is one undo step.
 */

export const HISTORY_LIMIT = 50;
export const GROUP_MS = 1000;

export interface History<T> {
  past: readonly T[];
  present: T;
  future: readonly T[];
  group: string | null;
  at: number;
}

export function createHistory<T>(present: T): History<T> {
  return { past: [], present, future: [], group: null, at: 0 };
}

export interface PushOptions {
  /** Edits with the same group within `GROUP_MS` merge into one step. */
  group?: string;
  now?: number;
}

export function push<T>(history: History<T>, next: T, options: PushOptions = {}): History<T> {
  if (Object.is(next, history.present)) return history;
  const now = options.now ?? Date.now();
  const group = options.group ?? null;
  if (group !== null && group === history.group && now - history.at < GROUP_MS) {
    return { ...history, present: next, future: [], at: now };
  }
  const past = [...history.past, history.present].slice(-HISTORY_LIMIT);
  return { past, present: next, future: [], group, at: now };
}

export function canUndo<T>(history: History<T>): boolean {
  return history.past.length > 0;
}

export function canRedo<T>(history: History<T>): boolean {
  return history.future.length > 0;
}

export function undo<T>(history: History<T>): History<T> {
  const previous = history.past[history.past.length - 1];
  if (previous === undefined) return history;
  return {
    past: history.past.slice(0, -1),
    present: previous,
    future: [history.present, ...history.future],
    group: null,
    at: 0,
  };
}

export function redo<T>(history: History<T>): History<T> {
  const [next, ...rest] = history.future;
  if (next === undefined) return history;
  return {
    past: [...history.past, history.present].slice(-HISTORY_LIMIT),
    present: next,
    future: rest,
    group: null,
    at: 0,
  };
}
