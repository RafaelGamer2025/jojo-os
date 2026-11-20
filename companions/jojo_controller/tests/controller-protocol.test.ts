import { describe, expect, it } from "vitest";
import {
  activeNames,
  ATTACKS,
  bit,
  hidReport,
  normalizeMask,
  padGeometry,
  touchesMask,
  validMapping,
  validToken,
} from "../lib/controller-protocol";
describe("JoJo Controller protocol", () => {
  it("rejects malformed state and token", () => {
    [-1, 2048, NaN, 1.2].forEach((m) =>
      expect(() => normalizeMask(m)).toThrow(),
    );
    expect(validToken("a".repeat(32))).toBe(true);
    expect(validToken("A".repeat(32))).toBe(false);
    expect(validToken("a".repeat(31))).toBe(false);
  });
  it("neutralizes opposing directions without losing attacks", () => {
    expect(normalizeMask(15 | bit("A"))).toBe(bit("A"));
    expect(activeNames(bit("Right") | bit("Start"))).toEqual([
      "Right",
      "Start",
    ]);
  });
  it("encodes all nine hat positions", () => {
    const masks = [
      bit("Up"),
      bit("Up") | bit("Right"),
      bit("Right"),
      bit("Right") | bit("Down"),
      bit("Down"),
      bit("Down") | bit("Left"),
      bit("Left"),
      bit("Left") | bit("Up"),
      0,
    ];
    masks.forEach((mask, hat) => expect(hidReport(mask)).toEqual([0, hat]));
    expect(hidReport(2047)).toEqual([127, 8]);
  });
  it("tracks multiple fingers and release", () => {
    const g = padGeometry(400, 300);
    const d = {
      x: g.dpad.x - g.dpad.radius * 0.6,
      y: g.dpad.y - g.dpad.radius * 0.6,
    };
    expect(touchesMask([d, g.attacks[0], g.attacks[3]], 400, 300)).toBe(
      bit("Up") | bit("Left") | bit("X") | bit("A"),
    );
    expect(touchesMask([], 400, 300)).toBe(0);
    expect(touchesMask([{ x: -900, y: -900 }], 400, 300)).toBe(0);
  });
  it("maps attack positions as a bijection", () => {
    expect(validMapping(ATTACKS)).toBe(true);
    expect(validMapping(["A", "A", "C", "X", "Y", "Z"])).toBe(false);
    expect(validMapping(null)).toBe(false);
    const g = padGeometry(340, 300);
    const custom = [...ATTACKS];
    [custom[0], custom[3]] = [custom[3], custom[0]];
    expect(touchesMask([g.attacks[0]], 340, 300, custom)).toBe(bit("A"));
  });
});
