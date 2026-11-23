import type { SplitReport } from "../../shared/data/report";
import styles from "./results.module.css";

function show(v: number | null): string {
  if (v === null) return "n/a";
  return Number.isInteger(v) ? String(v) : v.toFixed(3);
}

export function Gates({ res }: { res: SplitReport }) {
  return (
    <ul className={styles.gates} aria-label="Gates">
      {res.gates.platform.map((g) => (
        <li key={g.gate} className={g.pass ? styles.pass : styles.fail}>
          <span className={styles.mark} aria-hidden="true">
            {g.pass ? "✓" : "✕"}
          </span>
          <span className={styles.gateName}>{g.gate}</span>
          <span className={styles.gateValue}>
            {show(g.value)} <span className={styles.sub}>{g.kind === "min" ? "at least" : "at most"} {g.limit}</span>
          </span>
          <span className={styles.verdict}>{g.pass ? "Pass" : "Fail"}</span>
        </li>
      ))}
      {Object.entries(res.gates.model_swap).map(([name, s]) => (
        <li key={name} className={s.verdict === "passes" ? styles.pass : styles.fail}>
          <span className={styles.mark} aria-hidden="true">
            {s.verdict === "passes" ? "✓" : "✕"}
          </span>
          <span className={styles.gateName}>Release gate for {res.designs[name]?.label.toLowerCase()}</span>
          <span className={styles.gateValue}>
            {s.value_share_below_platform_pts.toFixed(1)} points below <span className={styles.sub}>at most 3.0</span>
          </span>
          <span className={styles.verdict}>{s.verdict === "passes" ? "Pass" : "Blocked"}</span>
        </li>
      ))}
    </ul>
  );
}
