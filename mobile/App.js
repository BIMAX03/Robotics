import React from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from "react-native";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";

const DEFAULT_API_BASE = process.env.EXPO_PUBLIC_API_BASE || "http://192.168.2.109:8000";

const CONTROL_GROUPS = [
  {
    title: "Base / Shoulder",
    controls: [
      { key: "S1", direction: 1, label: "Shoulder", icon: "chevron-up", slot: "north" },
      { key: "S0", direction: -1, label: "Base", icon: "chevron-back", slot: "west" },
      { key: "S0", direction: 1, label: "Base", icon: "chevron-forward", slot: "east" },
      { key: "S1", direction: -1, label: "Shoulder", icon: "chevron-down", slot: "south" },
    ],
  },
  {
    title: "Elbow / Wrist",
    controls: [
      { key: "S2", direction: 1, label: "Elbow", icon: "chevron-up", slot: "north" },
      { key: "S3", direction: -1, label: "Pitch", icon: "chevron-back", slot: "west" },
      { key: "S3", direction: 1, label: "Pitch", icon: "chevron-forward", slot: "east" },
      { key: "S2", direction: -1, label: "Elbow", icon: "chevron-down", slot: "south" },
    ],
  },
];

export default function App() {
  const { width, height } = useWindowDimensions();
  const isLandscape = width > height;
  const compact = isLandscape && height < 560;

  const [apiBase, setApiBase] = React.useState(DEFAULT_API_BASE);
  const [config, setConfig] = React.useState([]);
  const [joints, setJoints] = React.useState({});
  const [state, setState] = React.useState({ connected: false, mock: false });
  const [error, setError] = React.useState("");
  const [loading, setLoading] = React.useState(false);

  const activeControls = React.useRef(new Set());
  const configRef = React.useRef([]);
  const jointsRef = React.useRef({});
  const sendTimer = React.useRef(null);
  const lastInputTick = React.useRef(Date.now());

  React.useEffect(() => {
    configRef.current = config;
  }, [config]);

  React.useEffect(() => {
    jointsRef.current = joints;
  }, [joints]);

  React.useEffect(() => {
    loadInitialState();
    const stateTimer = setInterval(loadState, 1400);
    const inputTimer = setInterval(applyContinuousInput, 20);

    return () => {
      clearInterval(stateTimer);
      clearInterval(inputTimer);
      clearTimeout(sendTimer.current);
    };
  }, [apiBase]);

  async function request(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, {
      headers: { "Content-Type": "application/json", ...options.headers },
      ...options,
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Request failed");
    }

    return data;
  }

  async function loadInitialState() {
    setLoading(true);
    try {
      const [configData, stateData] = await Promise.all([
        request("/api/config"),
        request("/api/state"),
      ]);
      setConfig(configData.joints);
      setJoints(stateData.joints);
      setState(stateData);
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadState() {
    try {
      const data = await request("/api/state");
      setState(data);
      setError("");
    } catch (err) {
      setState((current) => ({ ...current, connected: false }));
      setError(err.message);
    }
  }

  function scheduleSend(nextJoints) {
    clearTimeout(sendTimer.current);
    sendTimer.current = setTimeout(() => {
      request("/api/joints", {
        method: "POST",
        body: JSON.stringify({ joints: nextJoints }),
      }).catch((err) => setError(err.message));
    }, 25);
  }

  function setJointValue(key, value) {
    const joint = getConfig(configRef.current, key);
    if (!joint) return;

    const nextValue = clamp(Math.round(value), joint.min, joint.max);
    const nextJoints = { ...jointsRef.current, [key]: nextValue };
    setJoints(nextJoints);
    scheduleSend(nextJoints);
  }

  function setControlActive(id, active) {
    if (active) {
      activeControls.current.add(id);
    } else {
      activeControls.current.delete(id);
    }
  }

  function applyContinuousInput() {
    const now = Date.now();
    const elapsed = Math.min((now - lastInputTick.current) / 1000, 0.08);
    lastInputTick.current = now;

    if (!activeControls.current.size) return;

    const axes = {};
    for (const id of activeControls.current) {
      const [key, direction] = id.split(":");
      axes[key] = (axes[key] || 0) + Number(direction);
    }

    let changed = false;
    const nextJoints = { ...jointsRef.current };

    for (const joint of configRef.current) {
      const axis = clamp(axes[joint.key] || 0, -1, 1);
      if (!axis) continue;

      const speed = joint.key === "S5" ? 35 : joint.max > 200 ? 120 : 92;
      const current = nextJoints[joint.key] ?? joint.home;
      const next = clamp(Math.round(current + axis * speed * elapsed), joint.min, joint.max);

      if (next !== current) {
        nextJoints[joint.key] = next;
        changed = true;
      }
    }

    if (changed) {
      setJoints(nextJoints);
      scheduleSend(nextJoints);
    }
  }

  async function goHome() {
    try {
      activeControls.current.clear();
      clearTimeout(sendTimer.current);
      const data = await request("/api/home", { method: "POST" });
      setJoints(data.joints);
      setError("");
      loadState();
    } catch (err) {
      Alert.alert("Home failed", err.message);
    }
  }

  async function sortItem(color) {
    try {
      activeControls.current.clear();
      clearTimeout(sendTimer.current);
      await request("/api/sort", {
        method: "POST",
        body: JSON.stringify({ color }),
      });
      setError("");
      loadState();
    } catch (err) {
      Alert.alert("Sort failed", err.message);
    }
  }

  async function emergencyStop() {
    try {
      activeControls.current.clear();
      clearTimeout(sendTimer.current);
      const data = await request("/api/emergency-stop", { method: "POST" });
      setState(data.state);
      setJoints(data.state.joints);
      setError("");
    } catch (err) {
      Alert.alert("Stop failed", err.message);
    }
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" />
      <View style={[styles.appShell, compact && styles.appShellCompact]}>
        <View style={styles.topBar}>
          <View style={styles.brandBlock}>
            <Text style={styles.eyebrow}>Manual Control</Text>
            <Text style={styles.title}>Robot Arm</Text>
          </View>

          <View style={styles.statusGroup}>
            <StatusPill connected={state.connected} mock={state.mock} />
            <Pressable style={styles.iconButton} onPress={loadInitialState}>
              {loading ? (
                <ActivityIndicator color="#f2f5f7" size="small" />
              ) : (
                <Ionicons name="refresh" size={18} color="#f2f5f7" />
              )}
            </Pressable>
            <Pressable style={styles.stopButton} onPress={emergencyStop}>
              <Ionicons name="stop-circle-outline" size={18} color="#ffffff" />
              <Text style={styles.stopButtonText}>Stop</Text>
            </Pressable>
            <Pressable style={styles.homeButton} onPress={goHome}>
              <Ionicons name="home-outline" size={18} color="#101820" />
              <Text style={styles.homeButtonText}>Home</Text>
            </Pressable>
          </View>
        </View>

        {!!error && <Text style={styles.errorBanner}>{error}</Text>}

        <View style={styles.apiRow}>
          <Text style={styles.apiLabel}>API</Text>
          <TextInput
            value={apiBase}
            onChangeText={setApiBase}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            style={styles.apiInput}
            placeholder="http://your-laptop-ip:8000"
            placeholderTextColor="#7d8d98"
          />
        </View>

        <ScrollView
          contentContainerStyle={[
            styles.gameSurface,
            isLandscape && styles.gameSurfaceLandscape,
            compact && styles.gameSurfaceCompact,
          ]}
          scrollEnabled={!compact}
        >
          <ControlDeck
            group={CONTROL_GROUPS[0]}
            config={config}
            joints={joints}
            setControlActive={setControlActive}
            compact={compact}
          />

          <CenterConsole
            config={config}
            joints={joints}
            state={state}
            setJointValue={setJointValue}
            setControlActive={setControlActive}
            sortItem={sortItem}
            compact={compact}
          />

          <ControlDeck
            group={CONTROL_GROUPS[1]}
            config={config}
            joints={joints}
            setControlActive={setControlActive}
            compact={compact}
          />
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

function ControlDeck({ group, config, joints, setControlActive, compact }) {
  return (
    <View style={[styles.panel, styles.controlDeck, compact && styles.controlDeckCompact]}>
      <View style={styles.deckHeader}>
        <Ionicons name="radio-button-on" size={17} color="#d7e0e6" />
        <Text style={styles.deckHeaderText}>{group.title}</Text>
      </View>

      <View style={[styles.dpad, compact && styles.dpadCompact]}>
        {group.controls.map((control) => (
          <HoldButton
            key={`${control.key}:${control.direction}`}
            control={control}
            range={getConfig(config, control.key)}
            value={joints[control.key] ?? getConfig(config, control.key)?.home ?? 0}
            setControlActive={setControlActive}
          />
        ))}
        <View style={styles.dpadCenter}>
          <Text style={styles.dpadCenterText}>{group.title.includes("Base") ? "S0/S1" : "S2/S3"}</Text>
        </View>
      </View>
    </View>
  );
}

function CenterConsole({ config, joints, state, setJointValue, setControlActive, sortItem, compact }) {
  const wristRoll = getConfig(config, "S4");
  const gripper = getConfig(config, "S5");

  return (
    <View style={[styles.panel, styles.centerConsole, compact && styles.centerConsoleCompact]}>
      <View style={styles.readoutPanel}>
        <View style={styles.deckHeader}>
          <Ionicons name="pulse-outline" size={17} color="#d7e0e6" />
          <Text style={styles.deckHeaderText}>Frame</Text>
        </View>
        <Text style={styles.frameText}>{state.frame || "180,90,135,75,90,40"}</Text>

        <View style={styles.miniGrid}>
          {config.map((joint) => (
            <View key={joint.key} style={styles.miniCell}>
              <Text style={styles.miniKey}>{joint.key}</Text>
              <Text style={styles.miniValue}>{joints[joint.key] ?? joint.home}°</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={styles.triggerRow}>
        <HoldButton
          control={{ key: "S4", direction: -1, label: "Roll", icon: "refresh", slot: "trigger" }}
          value={joints.S4 ?? wristRoll?.home ?? 90}
          range={wristRoll}
          setControlActive={setControlActive}
        />
        <HoldButton
          control={{ key: "S4", direction: 1, label: "Roll", icon: "refresh", slot: "trigger" }}
          value={joints.S4 ?? wristRoll?.home ?? 90}
          range={wristRoll}
          setControlActive={setControlActive}
        />
      </View>

      <View style={styles.gripperPanel}>
        <View>
          <Text style={styles.jointKey}>S5</Text>
          <Text style={styles.gripperTitle}>Gripper</Text>
        </View>
        <View style={styles.gripperButtons}>
          <HoldButton
            control={{ key: "S5", direction: -1, label: "Close", icon: "hand-right-outline", slot: "grip" }}
            value={joints.S5 ?? gripper?.home ?? 40}
            range={gripper}
            setControlActive={setControlActive}
            material
          />
          <HoldButton
            control={{ key: "S5", direction: 1, label: "Open", icon: "plus", slot: "gripOpen" }}
            value={joints.S5 ?? gripper?.home ?? 40}
            range={gripper}
            setControlActive={setControlActive}
          />
        </View>
      </View>

      <View style={styles.sortPanel}>
        <Pressable
          style={[styles.sortButton, styles.blueSortButton, state.busy && styles.disabledButton]}
          onPress={() => sortItem("blue")}
          disabled={state.busy}
        >
          <Text style={styles.sortButtonText}>Blue</Text>
        </Pressable>
        <Pressable
          style={[styles.sortButton, styles.redSortButton, state.busy && styles.disabledButton]}
          onPress={() => sortItem("red")}
          disabled={state.busy}
        >
          <Text style={styles.sortButtonText}>Red</Text>
        </Pressable>
      </View>

      {!compact && (
        <View style={styles.trimGrid}>
          {config.map((joint) => (
            <TrimSlider
              key={joint.key}
              joint={joint}
              value={joints[joint.key] ?? joint.home}
              onChange={(value) => setJointValue(joint.key, value)}
            />
          ))}
        </View>
      )}
    </View>
  );
}

function HoldButton({ control, range, value, setControlActive, material = false }) {
  const id = `${control.key}:${control.direction}`;
  const atLimit =
    range &&
    ((control.direction < 0 && value <= range.min) || (control.direction > 0 && value >= range.max));

  const buttonStyles = [
    styles.holdButton,
    control.slot === "north" && styles.north,
    control.slot === "west" && styles.west,
    control.slot === "east" && styles.east,
    control.slot === "south" && styles.south,
    control.slot === "trigger" && styles.triggerButton,
    control.slot === "grip" && styles.gripButton,
    control.slot === "gripOpen" && styles.gripOpenButton,
    atLimit && styles.atLimit,
  ];

  const IconSet = material ? MaterialCommunityIcons : Ionicons;

  return (
    <Pressable
      style={({ pressed }) => [buttonStyles, pressed && styles.holdButtonPressed]}
      onPressIn={() => setControlActive(id, true)}
      onPressOut={() => setControlActive(id, false)}
    >
      <IconSet name={control.icon} size={25} color="#f8fbfc" />
      <Text style={styles.holdLabel}>{control.label}</Text>
      <Text style={styles.holdValue}>{value}°</Text>
    </Pressable>
  );
}

function TrimSlider({ joint, value, onChange }) {
  const percent = (value - joint.min) / (joint.max - joint.min);

  return (
    <View style={styles.trimSlider}>
      <Text style={styles.trimKey}>{joint.key}</Text>
      <View style={styles.trimTrack}>
        <View style={[styles.trimFill, { flex: percent }]} />
        <View style={{ flex: 1 - percent }} />
      </View>
      <View style={styles.trimActions}>
        <Pressable style={styles.trimButton} onPress={() => onChange(value - 1)}>
          <Ionicons name="remove" size={15} color="#f2f5f7" />
        </Pressable>
        <Pressable style={styles.trimButton} onPress={() => onChange(value + 1)}>
          <Ionicons name="add" size={15} color="#f2f5f7" />
        </Pressable>
      </View>
    </View>
  );
}

function StatusPill({ connected, mock }) {
  return (
    <View style={[styles.statusPill, connected ? styles.statusOnline : styles.statusOffline]}>
      <Ionicons name={connected ? "wifi" : "wifi-outline"} size={16} color={connected ? "#9df3c1" : "#ffc1bd"} />
      <Text style={[styles.statusText, connected ? styles.statusOnlineText : styles.statusOfflineText]}>
        {mock ? "Mock" : connected ? "Connected" : "Offline"}
      </Text>
    </View>
  );
}

function getConfig(config, key) {
  return config.find((joint) => joint.key === key);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#10161b",
  },
  appShell: {
    flex: 1,
    paddingHorizontal: 12,
    paddingTop: 10,
  },
  appShellCompact: {
    paddingHorizontal: 8,
    paddingTop: 6,
  },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    marginBottom: 8,
  },
  brandBlock: {
    flexShrink: 1,
  },
  eyebrow: {
    color: "#9eb1bd",
    fontSize: 11,
    fontWeight: "900",
    textTransform: "uppercase",
  },
  title: {
    color: "#ffffff",
    fontSize: 30,
    fontWeight: "900",
    lineHeight: 34,
  },
  statusGroup: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  statusPill: {
    minHeight: 38,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderRadius: 8,
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
  },
  statusOnline: {
    borderColor: "rgba(54, 211, 153, 0.5)",
    backgroundColor: "rgba(20, 120, 63, 0.22)",
  },
  statusOffline: {
    borderColor: "rgba(255, 138, 128, 0.42)",
    backgroundColor: "rgba(153, 52, 46, 0.22)",
  },
  statusText: {
    fontWeight: "900",
  },
  statusOnlineText: {
    color: "#9df3c1",
  },
  statusOfflineText: {
    color: "#ffc1bd",
  },
  iconButton: {
    width: 38,
    height: 38,
    borderWidth: 1,
    borderColor: "#344650",
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.08)",
  },
  homeButton: {
    height: 38,
    paddingHorizontal: 13,
    borderRadius: 8,
    backgroundColor: "#f1f5f7",
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
  },
  homeButtonText: {
    color: "#101820",
    fontWeight: "900",
  },
  stopButton: {
    height: 38,
    paddingHorizontal: 13,
    borderRadius: 8,
    backgroundColor: "#b42318",
    borderWidth: 1,
    borderColor: "rgba(255, 138, 128, 0.52)",
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
  },
  stopButtonText: {
    color: "#ffffff",
    fontWeight: "900",
  },
  errorBanner: {
    marginBottom: 8,
    padding: 10,
    borderWidth: 1,
    borderColor: "rgba(255, 138, 128, 0.45)",
    borderRadius: 8,
    color: "#ffd3d0",
    backgroundColor: "rgba(153, 52, 46, 0.22)",
    fontWeight: "800",
  },
  apiRow: {
    minHeight: 42,
    marginBottom: 8,
    paddingHorizontal: 10,
    borderRadius: 8,
    backgroundColor: "rgba(255,255,255,0.07)",
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  apiLabel: {
    color: "#9eb1bd",
    fontWeight: "900",
  },
  apiInput: {
    flex: 1,
    color: "#f8fbfc",
    fontWeight: "700",
  },
  gameSurface: {
    gap: 10,
    paddingBottom: 16,
  },
  gameSurfaceLandscape: {
    flexDirection: "row",
    alignItems: "stretch",
  },
  gameSurfaceCompact: {
    flex: 1,
    paddingBottom: 0,
  },
  panel: {
    borderWidth: 1,
    borderColor: "rgba(174, 189, 198, 0.22)",
    borderRadius: 8,
    backgroundColor: "rgba(17, 25, 31, 0.92)",
  },
  controlDeck: {
    flex: 1,
    minHeight: 390,
    padding: 12,
  },
  controlDeckCompact: {
    minHeight: 0,
  },
  deckHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
  },
  deckHeaderText: {
    color: "#d7e0e6",
    fontWeight: "900",
  },
  dpad: {
    flex: 1,
    minHeight: 330,
    marginTop: 10,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  dpadCompact: {
    minHeight: 0,
  },
  dpadCenter: {
    position: "absolute",
    left: "34%",
    top: "34%",
    width: "32%",
    height: "32%",
    borderWidth: 1,
    borderColor: "rgba(174, 189, 198, 0.16)",
    borderRadius: 8,
    backgroundColor: "rgba(255,255,255,0.06)",
    alignItems: "center",
    justifyContent: "center",
  },
  dpadCenterText: {
    color: "#9eb1bd",
    fontWeight: "900",
  },
  holdButton: {
    width: "31.5%",
    minHeight: 104,
    borderWidth: 1,
    borderColor: "rgba(174, 189, 198, 0.2)",
    borderRadius: 8,
    backgroundColor: "#1c2930",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
  },
  north: {
    marginLeft: "34%",
    backgroundColor: "#1b2c31",
  },
  west: {
    backgroundColor: "#1b2c31",
  },
  east: {
    marginLeft: "34%",
    backgroundColor: "#2b2524",
  },
  south: {
    marginLeft: "34%",
    backgroundColor: "#2b2524",
  },
  holdButtonPressed: {
    borderColor: "rgba(255, 202, 87, 0.8)",
    backgroundColor: "#293844",
    transform: [{ scale: 0.98 }],
  },
  atLimit: {
    opacity: 0.55,
  },
  holdLabel: {
    color: "#dce5ea",
    fontSize: 12,
    fontWeight: "900",
    textAlign: "center",
  },
  holdValue: {
    color: "#88ead9",
    fontSize: 13,
    fontWeight: "900",
  },
  centerConsole: {
    flex: 0.92,
    gap: 9,
    minHeight: 390,
    padding: 10,
  },
  centerConsoleCompact: {
    minHeight: 0,
  },
  readoutPanel: {
    borderRadius: 8,
    padding: 10,
    backgroundColor: "rgba(255,255,255,0.05)",
  },
  frameText: {
    marginTop: 8,
    padding: 10,
    borderRadius: 8,
    backgroundColor: "#080d11",
    color: "#9ef0cf",
    fontFamily: "monospace",
    fontSize: 12,
  },
  miniGrid: {
    marginTop: 8,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
  },
  miniCell: {
    width: "31.5%",
    padding: 7,
    borderRadius: 8,
    backgroundColor: "rgba(255,255,255,0.07)",
  },
  miniKey: {
    color: "#9eb1bd",
    fontSize: 10,
    fontWeight: "900",
  },
  miniValue: {
    color: "#ffffff",
    fontSize: 14,
    fontWeight: "900",
  },
  triggerRow: {
    flexDirection: "row",
    gap: 8,
  },
  triggerButton: {
    flex: 1,
    width: "auto",
    minHeight: 76,
    backgroundColor: "#2b2a22",
  },
  gripperPanel: {
    borderRadius: 8,
    padding: 10,
    backgroundColor: "rgba(255,255,255,0.05)",
    gap: 8,
  },
  jointKey: {
    color: "#9eb1bd",
    fontSize: 11,
    fontWeight: "900",
  },
  gripperTitle: {
    color: "#ffffff",
    fontSize: 16,
    fontWeight: "900",
  },
  gripperButtons: {
    flexDirection: "row",
    gap: 8,
  },
  gripButton: {
    flex: 1,
    width: "auto",
    minHeight: 72,
    backgroundColor: "#2d2524",
  },
  gripOpenButton: {
    flex: 1,
    width: "auto",
    minHeight: 72,
    backgroundColor: "#1b2c31",
  },
  sortPanel: {
    flexDirection: "row",
    gap: 8,
  },
  sortButton: {
    flex: 1,
    minHeight: 54,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(174, 189, 198, 0.24)",
  },
  blueSortButton: {
    backgroundColor: "#1d4ed8",
  },
  redSortButton: {
    backgroundColor: "#b42318",
  },
  sortButtonText: {
    color: "#ffffff",
    fontWeight: "900",
  },
  disabledButton: {
    opacity: 0.48,
  },
  trimGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 7,
  },
  trimSlider: {
    width: "48.5%",
    padding: 8,
    borderRadius: 8,
    backgroundColor: "rgba(255,255,255,0.06)",
    gap: 6,
  },
  trimKey: {
    color: "#dce5ea",
    fontSize: 11,
    fontWeight: "900",
  },
  trimTrack: {
    height: 7,
    borderRadius: 999,
    flexDirection: "row",
    overflow: "hidden",
    backgroundColor: "rgba(174,189,198,0.25)",
  },
  trimFill: {
    backgroundColor: "#0f766e",
  },
  trimActions: {
    flexDirection: "row",
    gap: 6,
  },
  trimButton: {
    flex: 1,
    minHeight: 28,
    borderRadius: 8,
    backgroundColor: "rgba(255,255,255,0.08)",
    alignItems: "center",
    justifyContent: "center",
  },
});
