import { useState } from "react";
import {
  ScrollView,
  Text,
  View,
  Pressable,
  TextInput,
  StyleSheet,
  Linking,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { FightPad } from "@/components/fight-pad";
import { useController } from "@/hooks/use-controller";
import { activeNames } from "@/lib/controller-protocol";

type Page = "conectar" | "controle" | "ajustes" | "guia";
function Action({
  title,
  onPress,
  disabled = false,
  secondary = false,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  secondary?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        s.action,
        secondary && s.secondary,
        disabled && { opacity: 0.4 },
        pressed && { opacity: 0.75 },
      ]}
    >
      <Text style={[s.actionText, secondary && { color: "#eadcf3" }]}>
        {title}
      </Text>
    </Pressable>
  );
}
export default function HomeScreen() {
  const c = useController();
  const [page, setPage] = useState<Page>("conectar");
  const insets = useSafeAreaInsets();
  const changeMode = async (mode: "usb" | "bluetooth") => {
    await c.stop();
    c.setMode(mode);
  };
  const labels: Record<Page, string> = {
    conectar: "Conectar",
    controle: "Controle",
    ajustes: "Botões",
    guia: "Guia",
  };
  const icons: Record<Page, keyof typeof Ionicons.glyphMap> = {
    conectar: "link-outline",
    controle: "game-controller-outline",
    ajustes: "options-outline",
    guia: "help-circle-outline",
  };
  return (
    <View
      style={[
        s.root,
        {
          paddingTop: Math.max(insets.top, 18),
          paddingBottom: Math.max(insets.bottom, 12),
        },
      ]}
    >
      <View style={s.header}>
        <View style={s.mark}>
          <Ionicons name="game-controller" size={27} color="#ffcc00" />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={s.brand}>JOJO-OS</Text>
          <Text style={s.subtitle}>CONTROLLER // IKEMEN GO NO PC</Text>
        </View>
        <View
          style={[
            s.dot,
            { backgroundColor: c.isConnected ? "#5bdf93" : "#887294" },
          ]}
        />
      </View>
      <View style={s.nav}>
        {(Object.keys(labels) as Page[]).map((p) => (
          <Pressable
            key={p}
            accessibilityRole="tab"
            accessibilityState={{ selected: page === p }}
            onPress={() => {
              c.setMask(0);
              setPage(p);
            }}
            style={[s.navItem, page === p && s.navActive]}
          >
            <Ionicons
              name={icons[p]}
              size={19}
              color={page === p ? "#ffcc00" : "#b8a4c8"}
            />
            <Text style={[s.navText, page === p && { color: "#ffcc00" }]}>
              {labels[p]}
            </Text>
          </Pressable>
        ))}
      </View>
      <View style={s.status}>
        <View
          style={[
            s.dot,
            {
              backgroundColor: c.isConnected
                ? "#5bdf93"
                : c.status.state === "error"
                  ? "#f39898"
                  : "#887294",
            },
          ]}
        />
        <View style={{ flex: 1 }}>
          <Text style={s.statusLabel}>
            {c.isConnected
              ? `CONECTADO // ${c.status.mode.toUpperCase()}`
              : c.isBusy
                ? "AGUARDANDO CONEXÃO"
                : "SEM CONEXÃO"}
          </Text>
          <Text style={s.statusMessage}>{c.status.message}</Text>
          {c.status.device && <Text style={s.muted}>{c.status.device}</Text>}
        </View>
      </View>
      {page === "controle" ? (
        <View style={s.controlPage}>
          <View style={s.row}>
            <Text style={s.title}>Seu próximo combo.</Text>
            <Text style={s.chip}>
              {c.demo ? "DEMO LOCAL" : c.isConnected ? "AO VIVO" : "OFFLINE"}
            </Text>
          </View>
          <Text style={s.copy}>
            {c.demo
              ? "Teste de toques: nada é enviado ao computador."
              : "Mantenha o IKEMEN em primeiro plano no PC. Toque em direções e ataques ao mesmo tempo."}
          </Text>
          <FightPad
            mask={c.mask}
            mapping={c.mapping}
            enabled={c.isConnected || c.demo}
            onMask={c.setMask}
          />
          <Text style={s.activity}>
            {activeNames(c.mask).join(" + ") || "BOTÕES SOLTOS"}
          </Text>
          {c.isConnected || c.isBusy ? (
            <Action
              title="ENCERRAR SESSÃO"
              secondary
              onPress={() => void c.stop()}
            />
          ) : (
            <Action
              title="VOLTAR À CONEXÃO"
              onPress={() => {
                c.setDemo(false);
                setPage("conectar");
              }}
            />
          )}
          <Text style={s.foot}>
            Não existe macro, turbo ou envio de comandos fora da sessão.
          </Text>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={s.content}
          keyboardShouldPersistTaps="handled"
        >
          {page === "conectar" && (
            <>
              <Text style={s.eyebrow}>CELULAR → COMPUTADOR</Text>
              <Text style={s.headline}>Escolha sua conexão.</Text>
              <Text style={s.copy}>
                Um app companheiro próprio. O IKEMEN continua rodando no PC; o
                celular fica com os botões.
              </Text>
              <View style={s.modes}>
                {(["usb", "bluetooth"] as const).map((mode) => (
                  <Pressable
                    accessibilityRole="button"
                    key={mode}
                    onPress={() => void changeMode(mode)}
                    style={[s.modeCard, c.mode === mode && s.selected]}
                  >
                    <Ionicons
                      name={
                        mode === "usb" ? "hardware-chip-outline" : "bluetooth"
                      }
                      size={26}
                      color={c.mode === mode ? "#ffcc00" : "#bba8ca"}
                    />
                    <Text style={s.modeTitle}>
                      {mode === "usb" ? "USB" : "Bluetooth"}
                    </Text>
                    <Text style={s.muted}>
                      {mode === "usb"
                        ? "Cabo + receptor PC"
                        : "Gamepad HID sem fio"}
                    </Text>
                  </Pressable>
                ))}
              </View>
              <View style={s.card}>
                {c.mode === "usb" ? (
                  <>
                    <Text style={s.title}>Código da sessão USB</Text>
                    <Text style={s.copy}>
                      No JoJo-OS do PC, abra CONTROLE PELO CELULAR e inicie o
                      receptor USB. Conecte o cabo e autorize a Depuração USB.
                      Cole aqui o código exibido por ele.
                    </Text>
                    <TextInput
                      accessibilityLabel="Código da sessão USB"
                      value={c.token}
                      onChangeText={c.setToken}
                      editable={!c.isConnected && !c.isBusy}
                      autoCapitalize="none"
                      autoCorrect={false}
                      maxLength={32}
                      placeholder="32 caracteres do receptor PC"
                      placeholderTextColor="#9b83ad"
                      style={s.input}
                    />
                    <Text style={s.muted}>
                      Canal local via ADB • sem Wi-Fi • não usa DroidCast
                    </Text>
                  </>
                ) : (
                  <>
                    <Text style={s.title}>Seu computador pareado</Text>
                    <Text style={s.copy}>
                      Requer Android 9+, suporte HID do fabricante e Bluetooth
                      no PC. Pareie primeiro nos ajustes; depois selecione o
                      computador e conecte.
                    </Text>
                    <Action
                      secondary
                      title={
                        c.listing
                          ? "BUSCANDO PAREADOS…"
                          : "ATUALIZAR APARELHOS PAREADOS"
                      }
                      disabled={
                        !c.nativeAvailable ||
                        c.listing ||
                        c.isBusy ||
                        c.isConnected
                      }
                      onPress={() => void c.refreshDevices()}
                    />
                    {c.devices.map((d) => (
                      <Pressable
                        accessibilityRole="radio"
                        accessibilityState={{ checked: c.device === d.address }}
                        key={d.address}
                        disabled={c.isConnected || c.isBusy}
                        onPress={() => c.setDevice(d.address)}
                        style={[s.device, c.device === d.address && s.selected]}
                      >
                        <Ionicons
                          name="desktop-outline"
                          size={22}
                          color="#ffcc00"
                        />
                        <View style={{ flex: 1 }}>
                          <Text style={s.deviceName}>
                            {d.name || "Dispositivo pareado"}
                          </Text>
                          <Text style={s.muted}>{d.address}</Text>
                        </View>
                        <Ionicons
                          name={
                            c.device === d.address
                              ? "radio-button-on"
                              : "radio-button-off"
                          }
                          size={20}
                          color="#ffcc00"
                        />
                      </Pressable>
                    ))}
                    <Action
                      secondary
                      title="ABRIR AJUSTES BLUETOOTH"
                      disabled={!c.nativeAvailable}
                      onPress={() => void c.openBluetoothSettings()}
                    />
                  </>
                )}
              </View>
              {c.isConnected || c.isBusy ? (
                <>
                  <Action
                    title="IR PARA O CONTROLE"
                    disabled={!c.isConnected}
                    onPress={() => setPage("controle")}
                  />
                  <Action
                    secondary
                    title="ENCERRAR SESSÃO"
                    onPress={() => void c.stop()}
                  />
                </>
              ) : (
                <Action
                  title={
                    c.status.state === "error"
                      ? "TENTAR CONECTAR NOVAMENTE"
                      : "CONECTAR AO PC"
                  }
                  disabled={!c.nativeAvailable}
                  onPress={() => void c.connect()}
                />
              )}
              {!c.nativeAvailable && (
                <View style={s.notice}>
                  <Ionicons
                    name="information-circle-outline"
                    color="#ffcc00"
                    size={23}
                  />
                  <Text style={[s.copy, { flex: 1, marginBottom: 0 }]}>
                    Esta é a interface de demonstração. USB e Bluetooth precisam
                    do build Android com módulo nativo; não funcionam no Preview
                    ou no Expo Go.
                  </Text>
                </View>
              )}
              <Action
                secondary
                title="TESTAR LAYOUT SEM CONECTAR"
                disabled={c.isConnected || c.isBusy}
                onPress={() => {
                  c.setDemo(true);
                  setPage("controle");
                }}
              />
            </>
          )}
          {page === "ajustes" && (
            <>
              <Text style={s.eyebrow}>LAYOUT DE SEIS BOTÕES</Text>
              <Text style={s.headline}>Do seu jeito.</Text>
              <Text style={s.copy}>
                Toque em uma posição para trocar seu ataque com a posição
                seguinte. O mapa sempre preserva seis ataques distintos. Encerre
                a conexão antes de editar.
              </Text>
              <View style={s.card}>
                <View style={s.mapping}>
                  {c.mapping.map((name, i) => (
                    <Pressable
                      key={i}
                      accessibilityRole="button"
                      disabled={c.isConnected || c.isBusy}
                      onPress={() => c.swapMapping(i)}
                      style={s.mapButton}
                    >
                      <Text style={s.eyebrow}>POSIÇÃO {i + 1}</Text>
                      <Text style={s.mapLetter}>{name}</Text>
                    </Pressable>
                  ))}
                </View>
                <Action
                  secondary
                  title="RESTAURAR LAYOUT PADRÃO"
                  disabled={c.isConnected || c.isBusy}
                  onPress={c.resetMapping}
                />
              </View>
              <View style={s.card}>
                <Text style={s.title}>USB: teclas no receptor PC</Text>
                <Text style={s.copy}>
                  Padrão inicial: setas, A=Z, B=X, C=C, X=A, Y=S, Z=D e
                  Start=Enter. Configure as teclas na janela do receptor e
                  confira o mapeamento em Input Settings do IKEMEN. Não
                  alteramos o arquivo de controles do jogo automaticamente.
                </Text>
                <Text style={s.title}>Bluetooth: configuração de joystick</Text>
                <Text style={s.copy}>
                  A/B/C/X/Y/Z são os botões HID 1–6 e Start é o botão 7.
                  Configure o direcional e esses botões em Options → Input
                  Settings → Joystick Config.
                </Text>
              </View>
            </>
          )}
          {page === "guia" && (
            <>
              <Text style={s.eyebrow}>PRIMEIRA PARTIDA</Text>
              <Text style={s.headline}>Conectar sem adivinhar.</Text>
              <View style={s.card}>
                <Text style={s.title}>USB no Windows</Text>
                <Text style={s.copy}>
                  1. Abra o JoJo-OS atualizado no PC e clique em CONTROLE PELO
                  CELULAR. Tenha o ADB oficial disponível; a janela permite
                  escolher adb.exe.
                  {"\n"}2. Use cabo de dados. Ative Depuração USB no Android e
                  autorize apenas seu computador.
                  {"\n"}3. Inicie o receptor; copie o código da sessão para este
                  app e conecte.
                  {"\n"}4. Abra o IKEMEN e coloque o jogo em primeiro plano.
                  Configure suas teclas se forem diferentes do padrão.
                  {"\n"}5. Encerre a sessão no app e no receptor ao terminar.
                  Pode desligar a Depuração USB depois.
                </Text>
                <Action
                  secondary
                  title="PLATFORM TOOLS OFICIAL"
                  onPress={() =>
                    void Linking.openURL(
                      "https://developer.android.com/tools/releases/platform-tools",
                    )
                  }
                />
              </View>
              <View style={s.card}>
                <Text style={s.title}>Bluetooth no Windows</Text>
                <Text style={s.copy}>
                  1. Ative Bluetooth no telefone e PC e pareie os dois nos
                  ajustes.
                  {"\n"}2. No app, escolha Bluetooth, permita acesso aos
                  aparelhos próximos e atualize os pareados.
                  {"\n"}3. Selecione seu computador e conecte. Espere o status
                  real CONECTADO.
                  {"\n"}4. Configure o JoJo-OS Controller como joystick no
                  IKEMEN. O receptor USB não é necessário neste modo.
                  {"\n"}5. Mantenha o app aberto. Ao sair, a sessão HID é
                  encerrada; volte e conecte novamente.
                </Text>
              </View>
              <View style={s.notice}>
                <Ionicons name="warning-outline" color="#ffcc00" size={23} />
                <Text style={[s.copy, { flex: 1, marginBottom: 0 }]}>
                  O suporte HID varia por fabricante. Se o pareamento funcionar
                  mas o jogo não detectar o controle, confira o joystick no
                  Windows e o mapeamento SDL do IKEMEN. Teste em hardware real
                  ainda é necessário; não prometemos latência nem
                  compatibilidade universal.
                </Text>
              </View>
              <Text style={s.foot}>
                Este app não contém personagens, o motor IKEMEN nem um APK
                DroidCast modificado.
              </Text>
            </>
          )}
        </ScrollView>
      )}
    </View>
  );
}
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#1e102b" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingHorizontal: 22,
    paddingBottom: 19,
  },
  mark: {
    height: 45,
    width: 45,
    borderRadius: 14,
    backgroundColor: "#402b50",
    alignItems: "center",
    justifyContent: "center",
  },
  brand: {
    color: "#ffcc00",
    fontSize: 22,
    fontWeight: "900",
    letterSpacing: 2,
  },
  subtitle: { color: "#bda6cf", fontSize: 9, letterSpacing: 1.2, marginTop: 3 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  nav: {
    marginHorizontal: 18,
    flexDirection: "row",
    backgroundColor: "#291837",
    borderRadius: 15,
    padding: 5,
  },
  navItem: {
    flex: 1,
    alignItems: "center",
    gap: 5,
    paddingVertical: 10,
    borderRadius: 11,
  },
  navActive: { backgroundColor: "#493158" },
  navText: { color: "#b8a4c8", fontSize: 11, fontWeight: "600" },
  status: {
    margin: 18,
    padding: 13,
    borderRadius: 12,
    backgroundColor: "#30203d",
    flexDirection: "row",
    gap: 10,
    alignItems: "flex-start",
  },
  statusLabel: {
    color: "#eadef2",
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1,
  },
  statusMessage: {
    color: "#baa4ca",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 4,
  },
  content: { paddingHorizontal: 22, paddingBottom: 25, gap: 15 },
  eyebrow: {
    color: "#ad90c0",
    fontSize: 9,
    letterSpacing: 1.4,
    fontWeight: "700",
  },
  headline: {
    color: "#fff3fb",
    fontSize: 30,
    lineHeight: 35,
    fontWeight: "800",
  },
  copy: { color: "#cebcd9", fontSize: 13, lineHeight: 21, marginBottom: 6 },
  modes: { flexDirection: "row", gap: 12 },
  modeCard: {
    flex: 1,
    padding: 16,
    borderRadius: 17,
    borderWidth: 1,
    borderColor: "#573966",
    backgroundColor: "#30203d",
    gap: 8,
  },
  selected: { borderColor: "#ffcc00", backgroundColor: "#493356" },
  modeTitle: { color: "#f8eafd", fontWeight: "700", fontSize: 17 },
  muted: { color: "#ad96bd", fontSize: 10, lineHeight: 17 },
  card: {
    backgroundColor: "#30203d",
    borderRadius: 17,
    padding: 17,
    gap: 12,
    borderWidth: 1,
    borderColor: "#4f345f",
  },
  title: { color: "#f1e4f9", fontSize: 17, fontWeight: "700" },
  input: {
    backgroundColor: "#21102e",
    borderColor: "#72558a",
    borderWidth: 1,
    borderRadius: 11,
    padding: 13,
    fontSize: 13,
    color: "#fff2a6",
    minHeight: 49,
  },
  action: {
    backgroundColor: "#ffcc00",
    borderRadius: 12,
    minHeight: 49,
    padding: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  secondary: {
    backgroundColor: "#483058",
    borderWidth: 1,
    borderColor: "#674979",
  },
  actionText: {
    color: "#28142c",
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 1,
  },
  notice: {
    flexDirection: "row",
    gap: 12,
    padding: 16,
    borderRadius: 14,
    backgroundColor: "#3b2847",
  },
  device: {
    padding: 12,
    borderRadius: 12,
    flexDirection: "row",
    gap: 10,
    borderWidth: 1,
    borderColor: "#715287",
    alignItems: "center",
  },
  deviceName: { color: "#f4e7fb", fontSize: 13, fontWeight: "600" },
  controlPage: { flex: 1, paddingHorizontal: 18, gap: 12 },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 8,
  },
  chip: {
    fontSize: 8,
    fontWeight: "800",
    letterSpacing: 1,
    color: "#ffcc00",
    backgroundColor: "#3a234a",
    padding: 8,
    borderRadius: 8,
  },
  activity: {
    textAlign: "center",
    color: "#ffcc00",
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1,
    minHeight: 23,
  },
  foot: { color: "#997fab", fontSize: 10, lineHeight: 17, textAlign: "center" },
  mapping: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  mapButton: {
    width: "30%",
    padding: 10,
    borderRadius: 12,
    backgroundColor: "#513867",
    alignItems: "center",
    gap: 8,
  },
  mapLetter: { color: "#ffcc00", fontSize: 24, fontWeight: "800" },
});
