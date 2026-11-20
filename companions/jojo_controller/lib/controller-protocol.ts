export const BUTTONS = [
  "Up",
  "Down",
  "Left",
  "Right",
  "A",
  "B",
  "C",
  "X",
  "Y",
  "Z",
  "Start",
] as const;
export type ButtonName = (typeof BUTTONS)[number];
export type Attack = "A" | "B" | "C" | "X" | "Y" | "Z";
export const ATTACKS: Attack[] = ["X", "Y", "Z", "A", "B", "C"];
export const MAX_MASK = 2047;
export const USB_PORT = 8765;
export const bit = (name: ButtonName) => 1 << BUTTONS.indexOf(name);
export function normalizeMask(mask: number): number {
  if (!Number.isInteger(mask) || mask < 0 || mask > MAX_MASK)
    throw new Error("Estado de botões inválido.");
  if ((mask & 3) === 3) mask &= ~3;
  if ((mask & 12) === 12) mask &= ~12;
  return mask;
}
export function activeNames(mask: number): ButtonName[] {
  const normalized = normalizeMask(mask);
  return BUTTONS.filter((name) => (normalized & bit(name)) !== 0);
}
export function validToken(token: string): boolean {
  return /^[a-f0-9]{32}$/.test(token);
}
export function validMapping(value: unknown): value is Attack[] {
  return (
    Array.isArray(value) &&
    value.length === 6 &&
    new Set(value).size === 6 &&
    value.every((name) => ATTACKS.includes(name))
  );
}
// HID report ID 1: 7 buttons + reserved bit, eight-way hat (8 is neutral).
export function hidReport(mask: number): number[] {
  mask = normalizeMask(mask);
  let buttons = 0;
  (["A", "B", "C", "X", "Y", "Z", "Start"] as ButtonName[]).forEach(
    (name, index) => {
      if (mask & bit(name)) buttons |= 1 << index;
    },
  );
  const x = (mask & bit("Right") ? 1 : 0) - (mask & bit("Left") ? 1 : 0);
  const y = (mask & bit("Down") ? 1 : 0) - (mask & bit("Up") ? 1 : 0);
  const hats: Record<string, number> = {
    "0,-1": 0,
    "1,-1": 1,
    "1,0": 2,
    "1,1": 3,
    "0,1": 4,
    "-1,1": 5,
    "-1,0": 6,
    "-1,-1": 7,
    "0,0": 8,
  };
  return [buttons, hats[`${x},${y}`]];
}
export type Point = { x: number; y: number };
export function padGeometry(width: number, height: number) {
  const radius = Math.min(width * 0.17, 76);
  return {
    dpad: { x: width * 0.23, y: height * 0.55, radius },
    attacks: ATTACKS.map((name, i) => ({
      name,
      x: width * (0.6 + (i % 3) * 0.15),
      y: height * (i < 3 ? 0.44 : 0.7),
      radius: Math.min(width * 0.061, 32),
    })),
    start: { x: width * 0.75, y: height * 0.16, w: 92, h: 34 },
  };
}
export function touchesMask(
  points: Point[],
  width: number,
  height: number,
  mapping: Attack[] = ATTACKS,
): number {
  if (width <= 0 || height <= 0 || !validMapping(mapping)) return 0;
  const layout = padGeometry(width, height);
  let mask = 0;
  for (const p of points) {
    const dx = (p.x - layout.dpad.x) / layout.dpad.radius;
    const dy = (p.y - layout.dpad.y) / layout.dpad.radius;
    if (Math.abs(dx) <= 1.1 && Math.abs(dy) <= 1.1) {
      if (dy < -0.25) mask |= bit("Up");
      if (dy > 0.25) mask |= bit("Down");
      if (dx < -0.25) mask |= bit("Left");
      if (dx > 0.25) mask |= bit("Right");
    }
    layout.attacks.forEach((button, i) => {
      if (Math.hypot(p.x - button.x, p.y - button.y) <= button.radius * 1.25)
        mask |= bit(mapping[i]);
    });
    const s = layout.start;
    if (Math.abs(p.x - s.x) <= s.w / 2 && Math.abs(p.y - s.y) <= s.h / 2)
      mask |= bit("Start");
  }
  return normalizeMask(mask);
}
