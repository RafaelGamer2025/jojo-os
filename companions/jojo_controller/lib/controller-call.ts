import { normalizeMask } from "./controller-protocol";
/** The Expo Kotlin Function setMask returns void, not a Promise. */
export async function sendMaskToNative(
  transport: { setMask(mask: number): void },
  mask: number,
): Promise<void> {
  // An async boundary safely converts both synchronous success and throws.
  transport.setMask(normalizeMask(mask));
}
