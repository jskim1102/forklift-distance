import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { isValidElement, type EffectCallback, type ReactElement, type ReactNode } from "react";
import CamerasPage, { type Cam } from "./CamerasPage";
import CameraFormModal from "../components/CameraFormModal";
import CameraGrid from "../components/CameraGrid";

// 응답 rtsp_url 은 마스킹(:***@)이라 비밀번호만 바꾸면 값이 그대로다. 그래서 셀 key 를 rtsp_url 로
// 만들면 remount 되지 않는다 — 저장 성공 시 올리는 epoch 가 셀 key 를 바꾸는지 DOM 없이 본다.
// epoch 는 updater 로 올리므로 이 mock 은 mount 테스트와 달리 updater 를 바로 적용한다.
const view = vi.hoisted(() => ({
  states: [] as unknown[],
  index: 0,
  effects: [] as EffectCallback[],
}));

vi.mock("react", async (importOriginal) => ({
  ...await importOriginal<typeof import("react")>(),
  useState: (initial: unknown) => {
    const index = view.index++;
    if (index >= view.states.length) {
      view.states.push(typeof initial === "function" ? initial() : initial);
    }
    return [view.states[index], (value: unknown) => {
      view.states[index] = typeof value === "function" ? value(view.states[index]) : value;
    }];
  },
  useEffect: (effect: EffectCallback) => view.effects.push(effect),
  useCallback: (callback: unknown) => callback,
  useRef: (current: unknown) => ({ current }),
}));

vi.mock("../hooks/useApi", () => ({ apiBase: () => "" }));

const CAM: Cam = {
  id: 1,
  name: "정문",
  rtsp_url: "rtsp://admin:***@10.0.0.5:554/s1",
  stream_key: "ipcam-a",
  created_at: "2026-11-20T00:00:00Z",
};
const cleanups: Array<() => void> = [];

function renderPage() {
  view.index = 0;
  return CamerasPage({ onCalibrate: vi.fn() });
}

function elements(node: ReactNode): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}

function cellKeys() {
  const grid = elements(renderPage()).find((node) => node.type === CameraGrid)!;
  const cells = elements(CameraGrid(grid.props as unknown as Parameters<typeof CameraGrid>[0]));
  return cells.filter((node) => node.props.cam != null).map((node) => node.key);
}

async function mountAndOpenEdit(putStatus: number) {
  vi.stubGlobal("window", {
    localStorage: { getItem: () => null, setItem: vi.fn(), removeItem: vi.fn() },
  });
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    if (options?.method === "PUT") return new Response(null, { status: putStatus });
    return url === "/api/ipcams" ? Response.json([CAM]) : new Response(null, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  renderPage();
  for (const effect of view.effects.splice(0)) {
    const cleanup = effect();
    if (typeof cleanup === "function") cleanups.push(cleanup);
  }
  await vi.waitFor(() => expect(cellKeys()).toHaveLength(1));
  // 버튼 내용은 글자만(cam-distance) 또는 아이콘 + 글자(forklift-distance) — 둘 다 찾는다.
  const edit = elements(renderPage()).find((node) => node.type === "button"
    && [node.props.children].flat().includes("RTSP 수정"))!;
  (edit.props.onClick as () => void)();
  return fetchMock;
}

beforeEach(() => {
  view.states.length = 0;
  view.effects.length = 0;
  vi.spyOn(globalThis, "setInterval").mockReturnValue(0 as unknown as ReturnType<typeof setInterval>);
});

afterEach(() => {
  for (const cleanup of cleanups.splice(0)) cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("RTSP 수정 저장 후 영상 셀 remount", () => {
  it.each([
    ["비밀번호만 변경", true, "rtsp://admin:new-pass@10.0.0.5:554/s1", 200],
    ["이름만 변경", false, CAM.rtsp_url, 200],
    ["저장 실패", false, "rtsp://admin:new-pass@10.0.0.5:554/s1", 400],
  ])("%s → 셀 remount %s", async (_label, remount, url, putStatus) => {
    const fetchMock = await mountAndOpenEdit(putStatus);
    const before = cellKeys();
    const modal = elements(renderPage()).find((node) => node.type === CameraFormModal)!;

    await (modal.props.onSave as (name: string, rtspUrl: string) => Promise<string | null>)("정문 입구", url);

    expect(fetchMock).toHaveBeenCalledWith("/api/ipcams/1", expect.objectContaining({ method: "PUT" }));
    expect(cellKeys()[0] !== before[0]).toBe(remount);
  });
});
