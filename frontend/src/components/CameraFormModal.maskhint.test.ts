import { beforeEach, describe, expect, it, vi } from "vitest";
import { isValidElement, type ReactElement, type ReactNode } from "react";
import type { Cam } from "../pages/CamerasPage";
import CameraFormModal from "./CameraFormModal";

// 백엔드(_guard_masked_credential_exfil)는 *** 인 채 주소를 바꾸면 400 으로 거부한다.
// 안내 문구가 "주소는 그대로 수정하면 반영" 이라고 잘못 알리던 회귀를 막는다.
const view = vi.hoisted(() => ({ states: [] as unknown[], index: 0 }));
vi.mock("react", async (importOriginal) => ({
  ...await importOriginal<typeof import("react")>(),
  useState: () => {
    const index = view.index++;
    return [view.states[index], (value: unknown) => { view.states[index] = value; }];
  },
  useEffect: () => {},
}));

const CAM: Cam = {
  id: 1,
  name: "정문",
  rtsp_url: "rtsp://admin:***@10.0.0.5:554/s1",
  stream_key: "ipcam-a",
  created_at: "2026-11-20T00:00:00Z",
};

beforeEach(() => {
  // useState 순서 — name, rtspUrl, error, submitting.
  view.states = [CAM.name, CAM.rtsp_url, "", false];
  view.index = 0;
});

function elements(node: ReactNode): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}

function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return text(node.props.children);
  return typeof node === "string" ? node : "";
}

describe("카메라 수정 *** 안내", () => {
  it("*** 는 이름만 수정할 때만 유효하고 주소를 바꾸려면 실제 비밀번호를 다시 입력하라고 안내한다", () => {
    const tree = CameraFormModal({ open: true, editCam: CAM, onClose: vi.fn(), onSave: vi.fn() });
    const hint = elements(tree).find((node) => node.props.className === "hint" && text(node).includes("***"));

    expect(text(hint)).toBe(
      "⚠️ *** = 기존 비밀번호 유지 — RTSP 주소를 바꾸지 않고 이름만 수정할 때만 유효합니다. "
        + "주소·포트·경로 또는 비밀번호를 변경하려면 *** 를 지우고 실제 비밀번호를 다시 입력하세요.",
    );
  });
});
