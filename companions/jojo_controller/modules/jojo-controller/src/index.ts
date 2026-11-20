import { requireNativeModule } from 'expo-modules-core';

export type JoJoControllerCapabilities = {
  androidApi: number;
  bluetoothEnabled: boolean;
  hidApiAvailable: boolean;
};

export type JoJoBondedDevice = {
  name: string;
  address: string;
};

export type JoJoControllerStatus = {
  mode: 'usb' | 'bluetooth' | 'none';
  state: 'connecting' | 'registered' | 'connected' | 'disconnected' | 'error';
  message: string;
  device?: string;
};

export type JoJoControllerEvents = {
  onStatus: (event: JoJoControllerStatus) => void;
};

export type JoJoControllerNativeModule = {
  capabilities(): Promise<JoJoControllerCapabilities>;
  listBondedDevices(): Promise<JoJoBondedDevice[]>;
  /** Resolves when the command is queued. Connection status arrives through onStatus. */
  startBluetooth(address: string): Promise<void>;
  /** Resolves only after TCP localhost:8765 accepts the version-1 handshake. */
  connectUsb(token: string): Promise<void>;
  /** Updates mask state synchronously; valid values are integers 0..2047. */
  setMask(mask: number): void;
  disconnect(): Promise<void>;
  openBluetoothSettings(): Promise<void>;
  addListener(
    eventName: 'onStatus',
    listener: (event: JoJoControllerStatus) => void
  ): { remove(): void };
};

const JoJoController = requireNativeModule<JoJoControllerNativeModule>('JoJoController');

export default JoJoController;
export { JoJoController };
