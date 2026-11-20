import { describe, expect, it, vi } from "vitest";
import { sendMaskToNative } from "../lib/controller-call";

describe("native synchronous setMask adapter", () => {
  it("accepts native void return and normalizes direction opposites", async () => {
    const setMask = vi.fn((_mask: number): void => {});
    await expect(sendMaskToNative({ setMask }, 31)).resolves.toBeUndefined();
    expect(setMask).toHaveBeenCalledWith(16);
  });
  it("captures synchronous native failure as a rejection", async () => {
    await expect(
      sendMaskToNative(
        {
          setMask: () => {
            throw new Error("session closed");
          },
        },
        0,
      ),
    ).rejects.toThrow("session closed");
  });
  it("rejects unsafe state before native is called", async () => {
    const setMask = vi.fn();
    await expect(sendMaskToNative({ setMask }, -1)).rejects.toThrow();
    expect(setMask).not.toHaveBeenCalled();
  });
});
