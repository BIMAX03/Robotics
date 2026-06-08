import React from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleStop,
  CircleDot,
  Grab,
  Home,
  Minus,
  Plus,
  RotateCcw,
  RotateCw,
  Wifi,
  WifiOff,
} from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

const KEY_BINDINGS = {
  a: ["S0", -1],
  arrowleft: ["S0", -1],
  d: ["S0", 1],
  arrowright: ["S0", 1],
  s: ["S1", -1],
  arrowdown: ["S1", -1],
  w: ["S1", 1],
  arrowup: ["S1", 1],
  f: ["S2", -1],
  r: ["S2", 1],
  g: ["S3", -1],
  t: ["S3", 1],
  q: ["S4", -1],
  e: ["S4", 1],
  z: ["S5", -1],
  x: ["S5", 1],
};

const CONTROL_GROUPS = [
  {
    title: "Base / Shoulder",
    className: "leftDeck",
    controls: [
      { key: "S1", direction: 1, label: "Shoulder", icon: ChevronUp, className: "north" },
      { key: "S0", direction: -1, label: "Base", icon: ChevronLeft, className: "west" },
      { key: "S0", direction: 1, label: "Base", icon: ChevronRight, className: "east" },
      { key: "S1", direction: -1, label: "Shoulder", icon: ChevronDown, className: "south" },
    ],
  },
  {
    title: "Elbow / Wrist",
    className: "rightDeck",
    controls: [
      { key: "S2", direction: 1, label: "Elbow", icon: ChevronUp, className: "north" },
      { key: "S3", direction: -1, label: "Pitch", icon: ChevronLeft, className: "west" },
      { key: "S3", direction: 1, label: "Pitch", icon: ChevronRight, className: "east" },
      { key: "S2", direction: -1, label: "Elbow", icon: ChevronDown, className: "south" },
    ],
  },
];

function App() {
  const [config, setConfig] = React.useState([]);
  const [joints, setJoints] = React.useState({});
  const [state, setState] = React.useState({ connected: false, mock: false });
  const [error, setError] = React.useState("");

  const activeControls = React.useRef(new Set());
  const pressedKeys = React.useRef(new Set());
  const configRef = React.useRef([]);
  const jointsRef = React.useRef({});
  const sendTimer = React.useRef(null);
  const lastInputTick = React.useRef(performance.now());

  React.useEffect(() => {
    configRef.current = config;
  }, [config]);

  React.useEffect(() => {
    jointsRef.current = joints;
  }, [joints]);

  React.useEffect(() => {
    loadInitialState();

    const stateTimer = window.setInterval(loadState, 1200);
    const inputTimer = window.setInterval(applyContinuousInput, 20);

    const onKeyDown = (event) => {
      const key = event.key.toLowerCase();
      if (KEY_BINDINGS[key]) {
        event.preventDefault();
        pressedKeys.current.add(key);
      }
    };

    const onKeyUp = (event) => {
      pressedKeys.current.delete(event.key.toLowerCase());
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);

    return () => {
      window.clearInterval(stateTimer);
      window.clearInterval(inputTimer);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, []);

  async function request(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
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
    }
  }

  async function loadState() {
    try {
      const data = await request("/api/state");
      setState(data);
      setError("");
    } catch (err) {
      setError(err.message);
      setState((current) => ({ ...current, connected: false }));
    }
  }

  function scheduleSend(nextJoints) {
    window.clearTimeout(sendTimer.current);
    sendTimer.current = window.setTimeout(() => {
      request("/api/joints", {
        method: "POST",
        body: JSON.stringify({ joints: nextJoints }),
      }).catch((err) => setError(err.message));
    }, 25);
  }

  function setJointValue(key, value) {
    const joint = getJointConfig(key);
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
    const now = performance.now();
    const elapsed = Math.min((now - lastInputTick.current) / 1000, 0.08);
    lastInputTick.current = now;

    const axes = {};
    for (const id of activeControls.current) {
      const [key, direction] = id.split(":");
      axes[key] = (axes[key] ?? 0) + Number(direction);
    }

    for (const key of pressedKeys.current) {
      const binding = KEY_BINDINGS[key];
      if (!binding) continue;
      const [jointKey, direction] = binding;
      axes[jointKey] = (axes[jointKey] ?? 0) + direction;
    }

    if (!Object.keys(axes).length) return;

    let changed = false;
    const nextJoints = { ...jointsRef.current };

    for (const joint of configRef.current) {
      const axis = clamp(axes[joint.key] ?? 0, -1, 1);
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
      pressedKeys.current.clear();
      window.clearTimeout(sendTimer.current);
      const data = await request("/api/home", { method: "POST" });
      setJoints(data.joints);
      setError("");
      loadState();
    } catch (err) {
      setError(err.message);
    }
  }

  async function sortItem(color) {
    try {
      activeControls.current.clear();
      pressedKeys.current.clear();
      window.clearTimeout(sendTimer.current);
      await request("/api/sort", {
        method: "POST",
        body: JSON.stringify({ color }),
      });
      setError("");
      loadState();
    } catch (err) {
      setError(err.message);
    }
  }

  async function emergencyStop() {
    try {
      activeControls.current.clear();
      pressedKeys.current.clear();
      window.clearTimeout(sendTimer.current);
      const data = await request("/api/emergency-stop", { method: "POST" });
      setState(data.state);
      setJoints(data.state.joints);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  function getJointConfig(key) {
    return configRef.current.find((joint) => joint.key === key);
  }

  return (
    <main className="appShell">
      <header className="topBar">
        <div className="brandBlock">
          <p className="eyebrow">Manual Control</p>
          <h1>Robot Arm</h1>
        </div>

        <div className="statusGroup">
          <StatusPill connected={state.connected} mock={state.mock} />
          <button className="iconButton" type="button" onClick={loadInitialState} aria-label="Refresh">
            <RotateCcw size={18} />
          </button>
          <button className="dangerButton" type="button" onClick={emergencyStop}>
            <CircleStop size={18} />
            Stop
          </button>
          <button className="primaryButton" type="button" onClick={goHome}>
            <Home size={18} />
            Home
          </button>
        </div>
      </header>

      {error ? <div className="errorBanner">{error}</div> : null}

      <section className="gameSurface">
        <ControlDeck
          group={CONTROL_GROUPS[0]}
          joints={joints}
          config={config}
          setControlActive={setControlActive}
        />

        <CenterConsole
          config={config}
          joints={joints}
          state={state}
          setJointValue={setJointValue}
          setControlActive={setControlActive}
          sortItem={sortItem}
        />

        <ControlDeck
          group={CONTROL_GROUPS[1]}
          joints={joints}
          config={config}
          setControlActive={setControlActive}
        />
      </section>
    </main>
  );
}

function ControlDeck({ group, joints, config, setControlActive }) {
  return (
    <section className={`controlDeck ${group.className}`}>
      <div className="deckHeader">
        <CircleDot size={18} />
        <span>{group.title}</span>
      </div>

      <div className="dpad">
        {group.controls.map((control) => (
          <HoldButton
            key={`${control.key}:${control.direction}`}
            control={control}
            value={joints[control.key] ?? getConfig(config, control.key)?.home ?? 0}
            range={getConfig(config, control.key)}
            setControlActive={setControlActive}
          />
        ))}
        <div className="dpadCenter">
          <span>{group.className === "leftDeck" ? "S0/S1" : "S2/S3"}</span>
        </div>
      </div>
    </section>
  );
}

function CenterConsole({ config, joints, state, setJointValue, setControlActive, sortItem }) {
  const wristRoll = getConfig(config, "S4");
  const gripper = getConfig(config, "S5");

  return (
    <section className="centerConsole">
      <div className="readoutPanel">
        <div className="readoutHeader">
          <Activity size={18} />
          <span>Frame</span>
        </div>
        <code>{state.frame || "180,90,135,75,90,40"}</code>
        <div className="miniGrid">
          {config.map((joint) => (
            <div key={joint.key}>
              <span>{joint.key}</span>
              <strong>{joints[joint.key] ?? joint.home}°</strong>
            </div>
          ))}
        </div>
      </div>

      <div className="triggerRow">
        <HoldButton
          control={{ key: "S4", direction: -1, label: "Roll", icon: RotateCcw, className: "trigger" }}
          value={joints.S4 ?? wristRoll?.home ?? 90}
          range={wristRoll}
          setControlActive={setControlActive}
        />
        <HoldButton
          control={{ key: "S4", direction: 1, label: "Roll", icon: RotateCw, className: "trigger" }}
          value={joints.S4 ?? wristRoll?.home ?? 90}
          range={wristRoll}
          setControlActive={setControlActive}
        />
      </div>

      <div className="gripperPanel">
        <div>
          <span className="jointKey">S5</span>
          <h2>Gripper</h2>
        </div>
        <div className="gripperButtons">
          <HoldButton
            control={{ key: "S5", direction: -1, label: "Close", icon: Grab, className: "gripButton" }}
            value={joints.S5 ?? gripper?.home ?? 40}
            range={gripper}
            setControlActive={setControlActive}
          />
          <HoldButton
            control={{ key: "S5", direction: 1, label: "Open", icon: Plus, className: "gripButton open" }}
            value={joints.S5 ?? gripper?.home ?? 40}
            range={gripper}
            setControlActive={setControlActive}
          />
        </div>
      </div>

      <div className="sortPanel">
        <button className="sortButton blueSort" type="button" onClick={() => sortItem("blue")} disabled={state.busy}>
          Blue
        </button>
        <button className="sortButton redSort" type="button" onClick={() => sortItem("red")} disabled={state.busy}>
          Red
        </button>
      </div>

      <div className="trimGrid">
        {config.map((joint) => (
          <TrimSlider
            key={joint.key}
            joint={joint}
            value={joints[joint.key] ?? joint.home}
            onChange={(value) => setJointValue(joint.key, value)}
          />
        ))}
      </div>
    </section>
  );
}

function HoldButton({ control, value, range, setControlActive }) {
  const Icon = control.icon ?? Plus;
  const id = `${control.key}:${control.direction}`;
  const atLimit =
    range &&
    ((control.direction < 0 && value <= range.min) || (control.direction > 0 && value >= range.max));

  const stop = React.useCallback(() => {
    setControlActive(id, false);
  }, [id, setControlActive]);

  React.useEffect(() => stop, [stop]);

  return (
    <button
      className={`holdButton ${control.className} ${atLimit ? "atLimit" : ""}`}
      type="button"
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture(event.pointerId);
        setControlActive(id, true);
      }}
      onPointerUp={stop}
      onPointerCancel={stop}
      onPointerLeave={stop}
      aria-label={`${control.label} ${control.direction > 0 ? "increase" : "decrease"}`}
    >
      <Icon size={24} />
      <span>{control.label}</span>
      <strong>{value}°</strong>
    </button>
  );
}

function TrimSlider({ joint, value, onChange }) {
  const percent = ((value - joint.min) / (joint.max - joint.min)) * 100;

  return (
    <label className="trimSlider" style={{ "--fill": `${percent}%` }}>
      <span>{joint.key}</span>
      <input
        type="range"
        min={joint.min}
        max={joint.max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function StatusPill({ connected, mock }) {
  return (
    <div className={`statusPill ${connected ? "online" : "offline"}`}>
      {connected ? <Wifi size={17} /> : <WifiOff size={17} />}
      {mock ? "Mock" : connected ? "Connected" : "Offline"}
    </div>
  );
}

function getConfig(config, key) {
  return config.find((joint) => joint.key === key);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

createRoot(document.getElementById("root")).render(<App />);
