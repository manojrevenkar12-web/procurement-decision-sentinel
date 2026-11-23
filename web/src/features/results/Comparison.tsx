import { motion, useReducedMotion } from "framer-motion";
import type { SplitReport } from "../../shared/data/report";
import { hours, pct, pts } from "../../shared/format";
import { settle } from "../../shared/theme/motion";
import styles from "./results.module.css";

const MAIN = ["status_quo", "model_alone", "platform"];

export function Comparison({ res }: { res: SplitReport }) {
  const reduce = useReducedMotion();
  const sq = res.designs.status_quo?.metrics;
  return (
    <div className={styles.scroll}>
      <table className={styles.table} aria-label={`Three designs on the same feed. Seeds ${res.seeds.join(", ")}`}>
        <caption className={styles.caption}>
          Seeds {res.seeds.join(", ")} in the {res.variant === "heldout" ? "held-out" : "development"} world. Every design reads the same {Math.round(res.designs.platform?.metrics.messages_per_week ?? 0)} articles a week and meets the same luck.
        </caption>
        <thead>
          <tr>
            <th scope="col">Design</th>
            <th scope="col" className={styles.barCol}>
              Mitigable value captured
            </th>
            <th scope="col">vs analyst, points (95% CI)</th>
            <th scope="col">Cards a week</th>
            <th scope="col">Cards that mattered</th>
            <th scope="col">People, minutes a week</th>
            <th scope="col">Signal to decision</th>
          </tr>
        </thead>
        <tbody>
          {MAIN.filter((n) => res.designs[n]).map((n) => {
            const d = res.designs[n]!;
            const m = d.metrics;
            const c = res.comparisons[`${n}_vs_status_quo`];
            const mine = n === "platform";
            return (
              <tr key={n} className={mine ? styles.mine : undefined}>
                <th scope="row">{d.label}</th>
                <td className={styles.barCell}>
                  <span className={styles.barTrack} aria-hidden="true">
                    <motion.span className={mine ? styles.barMine : styles.bar} initial={reduce ? false : { width: 0 }} animate={{ width: `${m.value_share * 100}%` }} transition={settle} />
                  </span>
                  <span className={styles.barValue}>{pct(m.value_share)}</span>
                </td>
                <td>{c ? `${pts(c.diff)} (${pts(c.lo)} to ${pts(c.hi)})` : "baseline"}</td>
                <td>{m.cards_per_week.toFixed(1)}</td>
                <td>{pct(m.precision, 0)}</td>
                <td>
                  {Math.round(m.minutes_per_week)}
                  {sq && n !== "status_quo" && <span className={styles.sub}> {Math.round((m.minutes_per_week / sq.minutes_per_week) * 100)}% of analyst</span>}
                </td>
                <td>{hours(m.decision_median_h)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
