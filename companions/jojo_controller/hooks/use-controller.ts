import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, PermissionsAndroid, Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { activateKeepAwakeAsync, deactivateKeepAwake } from "expo-keep-awake";
import { sendMaskToNative } from "@/lib/controller-call";
import {
  ATTACKS,
  Attack,
  normalizeMask,
  validMapping,
  validToken,
} from "@/lib/controller-protocol";
import {
  BondedDevice,
  ConnectionMode,
  nativeController,
  nativeUnavailableMessage,
  StatusEvent,
} from "@/lib/controller-native";

export function useController() {
  const [mode, setMode] = useState<ConnectionMode>("usb");
  const [token, setToken] = useState("");
  const [devices, setDevices] = useState<BondedDevice[]>([]);
  const [device, setDevice] = useState("");
  const [status, setStatus] = useState<StatusEvent>({
    mode: "none",
    state: "disconnected",
    message: nativeController
      ? "Escolha uma conexão para começar."
      : nativeUnavailableMessage,
  });
  const [mapping, setMapping] = useState<Attack[]>([...ATTACKS]);
  const [mask, setMaskState] = useState(0);
  const [demo, setDemo] = useState(false);
  const latestMask = useRef(0);
  const connected = useRef(false);
  const mounted = useRef(true);
  const version = useRef(0);
  const [listing, setListing] = useState(false);
  const isConnected = status.state === "connected";
  const isBusy = status.state === "connecting" || status.state === "registered";

  useEffect(() => {
    if (isConnected)
      void activateKeepAwakeAsync("jojo-controller").catch(() => {});
    else void deactivateKeepAwake("jojo-controller");
    return () => {
      void deactivateKeepAwake("jojo-controller");
    };
  }, [isConnected]);

  useEffect(() => {
    mounted.current = true;
    void AsyncStorage.getItem("jojo.attack.mapping")
      .then((raw) => {
        if (!raw || !mounted.current) return;
        try {
          const saved = JSON.parse(raw);
          if (validMapping(saved)) setMapping(saved);
        } catch {
          /* Ignore corrupt optional preferences. */
        }
      })
      .catch(() => {});
    const listener = nativeController?.addListener("onStatus", (event) => {
      if (!mounted.current) return;
      connected.current = event.state === "connected";
      if (!connected.current) {
        latestMask.current = 0;
        setMaskState(0);
      }
      setStatus(event);
    });
    const timer = setInterval(() => {
      // Refresh the native watchdog only while JS and the real session are alive.
      if (connected.current && nativeController)
        void sendMaskToNative(nativeController, latestMask.current).catch(
          (e) => {
            connected.current = false;
            latestMask.current = 0;
            if (mounted.current) {
              setMaskState(0);
              setStatus({ mode: "none", state: "error", message: String(e) });
            }
            void nativeController?.disconnect().catch(() => {});
          },
        );
    }, 100);
    const appListener = AppState.addEventListener("change", (state) => {
      if (state === "active") return;
      version.current++;
      connected.current = false;
      latestMask.current = 0;
      setMaskState(0);
      setDemo(false);
      void nativeController?.disconnect().catch(() => {});
      setStatus({
        mode: "none",
        state: "disconnected",
        message: "Sessão encerrada ao sair do app. Reconecte para jogar.",
      });
    });
    return () => {
      mounted.current = false;
      version.current++;
      connected.current = false;
      latestMask.current = 0;
      clearInterval(timer);
      listener?.remove();
      appListener.remove();
      void nativeController?.disconnect().catch(() => {});
    };
  }, []);

  const setMask = useCallback((value: number) => {
    const safe = normalizeMask(value);
    latestMask.current = safe;
    setMaskState(safe);
    if (connected.current && nativeController)
      void sendMaskToNative(nativeController, safe).catch(() => {});
  }, []);
  const stop = useCallback(async () => {
    version.current++;
    connected.current = false;
    latestMask.current = 0;
    setMaskState(0);
    setDemo(false);
    try {
      await nativeController?.disconnect();
    } catch {
      /* Native cleanup is also enforced by lifecycle. */
    }
    if (mounted.current)
      setStatus({
        mode: "none",
        state: "disconnected",
        message: "Sessão encerrada. Todos os botões foram soltos.",
      });
  }, []);
  const permission = async () => {
    if (!nativeController) throw new Error(nativeUnavailableMessage);
    if (Platform.OS === "android" && Number(Platform.Version) >= 31) {
      const result = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
        {
          title: "Conectar seu controle",
          message:
            "O JoJo-OS precisa acessar dispositivos Bluetooth pareados para enviar os botões ao computador.",
          buttonPositive: "Permitir",
          buttonNegative: "Cancelar",
        },
      );
      if (result !== PermissionsAndroid.RESULTS.GRANTED)
        throw new Error(
          "Permissão Bluetooth negada. Nenhuma conexão foi iniciada.",
        );
    }
    const caps = await nativeController.capabilities();
    if (!caps.hidApiAvailable)
      throw new Error(
        "Bluetooth HID requer Android 9 ou superior e suporte do fabricante.",
      );
    if (!caps.bluetoothEnabled)
      throw new Error(
        "Ative o Bluetooth nos ajustes do Android e tente novamente.",
      );
  };
  const refreshDevices = async () => {
    setListing(true);
    try {
      await permission();
      const list = await nativeController!.listBondedDevices();
      if (mounted.current) {
        setDevices(list);
        if (list.length === 0)
          setStatus({
            mode: "bluetooth",
            state: "disconnected",
            message:
              "Nenhum aparelho pareado. Pareie seu PC nos ajustes Bluetooth e atualize a lista.",
          });
      }
    } catch (e) {
      setStatus({
        mode: "bluetooth",
        state: "error",
        message: e instanceof Error ? e.message : String(e),
      });
    } finally {
      if (mounted.current) setListing(false);
    }
  };
  const connect = async () => {
    if (isBusy) return;
    const attempt = ++version.current;
    setDemo(false);
    latestMask.current = 0;
    setMaskState(0);
    setStatus({ mode, state: "connecting", message: "Preparando a conexão…" });
    try {
      if (!nativeController) throw new Error(nativeUnavailableMessage);
      if (mode === "usb") {
        if (!validToken(token.trim()))
          throw new Error(
            "Cole o código de 32 caracteres exibido pelo receptor USB no PC.",
          );
        await nativeController.connectUsb(token.trim());
      } else {
        await permission();
        if (version.current !== attempt) return;
        if (!device)
          throw new Error("Selecione o computador pareado antes de conectar.");
        await nativeController.startBluetooth(device);
      }
      // Native events, not promise completion, decide whether the PC is connected.
    } catch (e) {
      if (mounted.current && version.current === attempt)
        setStatus({
          mode,
          state: "error",
          message: e instanceof Error ? e.message : String(e),
        });
    }
  };
  const swapMapping = (index: number) => {
    if (isConnected || isBusy) return;
    const next = [...mapping];
    const other = (index + 1) % 6;
    [next[index], next[other]] = [next[other], next[index]];
    setMapping(next);
    void AsyncStorage.setItem(
      "jojo.attack.mapping",
      JSON.stringify(next),
    ).catch(() => {});
  };
  const resetMapping = () => {
    if (isConnected || isBusy) return;
    setMapping([...ATTACKS]);
    void AsyncStorage.removeItem("jojo.attack.mapping").catch(() => {});
  };
  return {
    mode,
    setMode,
    token,
    setToken,
    devices,
    device,
    setDevice,
    status,
    mapping,
    mask,
    setMask,
    demo,
    setDemo,
    isConnected,
    isBusy,
    listing,
    refreshDevices,
    connect,
    stop,
    swapMapping,
    resetMapping,
    nativeAvailable: !!nativeController,
    openBluetoothSettings: async () => {
      try {
        await nativeController?.openBluetoothSettings();
      } catch (e) {
        setStatus({ mode: "bluetooth", state: "error", message: String(e) });
      }
    },
  };
}
