import { useRef, useState } from "react";
import { View, Text, StyleSheet, GestureResponderEvent } from "react-native";
import {
  Attack,
  bit,
  padGeometry,
  touchesMask,
} from "@/lib/controller-protocol";

type Props = {
  mask: number;
  mapping: Attack[];
  enabled: boolean;
  onMask: (mask: number) => void;
};
export function FightPad({ mask, mapping, enabled, onMask }: Props) {
  const surface = useRef<View>(null);
  const origin = useRef({ x: 0, y: 0 });
  const [size, setSize] = useState({ w: 340, h: 300 });
  const layout = padGeometry(size.w, size.h);
  const measure = () =>
    surface.current?.measureInWindow((x, y) => {
      origin.current = { x, y };
    });
  const handle = (event: GestureResponderEvent) => {
    if (!enabled) {
      onMask(0);
      return;
    }
    const touches = event.nativeEvent.touches;
    // Whole-surface responder preserves all fingers, including direction + several attacks.
    onMask(
      touchesMask(
        touches.map((t) => ({
          x: t.pageX - origin.current.x,
          y: t.pageY - origin.current.y,
        })),
        size.w,
        size.h,
        mapping,
      ),
    );
  };
  const cell = layout.dpad.radius * 0.62;
  const directions = [
    { label: "↑", name: "Up" as const, x: 0, y: -1 },
    { label: "↓", name: "Down" as const, x: 0, y: 1 },
    { label: "←", name: "Left" as const, x: -1, y: 0 },
    { label: "→", name: "Right" as const, x: 1, y: 0 },
  ];
  return (
    <View
      ref={surface}
      style={[styles.surface, !enabled && { opacity: 0.45 }]}
      onLayout={(e) => {
        setSize({
          w: e.nativeEvent.layout.width,
          h: e.nativeEvent.layout.height,
        });
        measure();
      }}
      onStartShouldSetResponder={() => true}
      onMoveShouldSetResponder={() => true}
      onResponderGrant={(e) => {
        measure();
        handle(e);
      }}
      onResponderStart={handle}
      onResponderMove={handle}
      onResponderEnd={handle}
      onResponderRelease={() => onMask(0)}
      onResponderTerminate={() => onMask(0)}
      onResponderTerminationRequest={() => false}
      accessibilityLabel="Área multitouch do controle. Direcional à esquerda e seis ataques à direita."
    >
      <View
        pointerEvents="none"
        style={[
          styles.center,
          {
            width: cell,
            height: cell,
            left: layout.dpad.x - cell / 2,
            top: layout.dpad.y - cell / 2,
          },
        ]}
      />
      {directions.map((d) => (
        <View
          pointerEvents="none"
          key={d.name}
          style={[
            styles.direction,
            {
              width: cell,
              height: cell,
              left: layout.dpad.x + d.x * cell - cell / 2,
              top: layout.dpad.y + d.y * cell - cell / 2,
            },
            !!(mask & bit(d.name)) && styles.down,
          ]}
        >
          <Text style={styles.arrow}>{d.label}</Text>
        </View>
      ))}
      {layout.attacks.map((b, i) => (
        <View
          pointerEvents="none"
          key={i}
          style={[
            styles.attack,
            {
              left: b.x - b.radius,
              top: b.y - b.radius,
              width: b.radius * 2,
              height: b.radius * 2,
              borderRadius: b.radius,
            },
            !!(mask & bit(mapping[i])) && styles.down,
          ]}
        >
          <Text style={styles.letter}>{mapping[i]}</Text>
        </View>
      ))}
      <View
        pointerEvents="none"
        style={[
          styles.start,
          { left: layout.start.x - 46, top: layout.start.y - 17 },
          !!(mask & bit("Start")) && styles.down,
        ]}
      >
        <Text style={styles.startText}>START</Text>
      </View>
      <Text pointerEvents="none" style={styles.caption}>
        DIRECIONAL + ATAQUES SIMULTÂNEOS
      </Text>
    </View>
  );
}
const styles = StyleSheet.create({
  surface: {
    height: 300,
    width: "100%",
    backgroundColor: "#251433",
    borderRadius: 22,
    borderWidth: 1,
    borderColor: "#513363",
    overflow: "hidden",
  },
  direction: {
    position: "absolute",
    backgroundColor: "#503563",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 9,
    borderBottomWidth: 4,
    borderBottomColor: "#140a1e",
  },
  center: { position: "absolute", backgroundColor: "#503563" },
  arrow: { color: "#f5e9ff", fontSize: 23, fontWeight: "700" },
  attack: {
    position: "absolute",
    backgroundColor: "#654280",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: "#9671b0",
    borderBottomWidth: 5,
    borderBottomColor: "#140a1e",
  },
  letter: { color: "#fff2a6", fontSize: 19, fontWeight: "900" },
  down: { backgroundColor: "#dfb929", borderColor: "#ffe59c" },
  start: {
    position: "absolute",
    width: 92,
    height: 34,
    borderRadius: 17,
    backgroundColor: "#503563",
    alignItems: "center",
    justifyContent: "center",
  },
  startText: {
    color: "#fff2a6",
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 2,
  },
  caption: {
    position: "absolute",
    bottom: 15,
    width: "100%",
    textAlign: "center",
    fontSize: 9,
    letterSpacing: 1.2,
    color: "#b9a3ca",
  },
});
