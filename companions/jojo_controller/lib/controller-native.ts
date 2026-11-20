import { Platform } from "react-native";
import { requireOptionalNativeModule } from "expo-modules-core";
import type {
  JoJoControllerNativeModule,
  JoJoControllerStatus,
  JoJoBondedDevice,
} from "../modules/jojo-controller/src";

export type ConnectionMode = "usb" | "bluetooth";
export type StatusEvent = JoJoControllerStatus;
export type BondedDevice = JoJoBondedDevice;
export type ControllerModule = JoJoControllerNativeModule;

// Type-only imports above do not load the module's required-native entry on Web.
export const nativeController =
  Platform.OS === "android"
    ? requireOptionalNativeModule<ControllerModule>("JoJoController")
    : null;
export const nativeUnavailableMessage =
  Platform.OS === "web"
    ? "Preview de interface: USB e Bluetooth só funcionam no app Android compilado."
    : "Este ambiente não contém o módulo do controle. Gere o build Android no Dashboard; o Expo Go não inclui Bluetooth HID nem a ponte USB.";
