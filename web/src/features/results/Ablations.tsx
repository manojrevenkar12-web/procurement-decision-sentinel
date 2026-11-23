import type { SplitReport } from "../../shared/data/report";
import { pct, pts } from "../../shared/format";
import styles from "./results.module.css";

const W = 220;
const H = 22;

function Whisker({ lo, hi, diff, min, max }: { lo: number; hi: number; diff: number; min: number; max: number }) {
  const x = (v: number) => ((v - min) / (max - min)) * (W - 12) + 6;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden="true" className={styles.whisker}>
      <line x1={x(0)} x2={x(0)} y1={2} y2={H - 2} className={styles.zeroLine} />
      <line x1={x(lo)} x2={x(hi)} y1={H / 2} y2={H / 2} className={styles.ci} />
      <circle cx={x(diff)} cy={H / 2} r={4.5} className={diff < -0.005 ? styles.dotBad : styles.dot} />
    </svg>
  );
}

export function Ablations({ res }: { res: SplitReport }) {
  const names = [...res.ablations, ...res.model_swap].filter((n) => res.designs[n] && res.comparisons[`${n}_vs_platform`]);
  const all = names.flatMap((n) => [res.comparisons[`${n}_vs_platform`]!.lo, res.comparisons[`${n}_vs_platform`]!.hi]);
  const min = Math.min(-0.02, ...all);
  const max = Math.max(0.02, ...all);
  const pm = res.designs.platform!.metrics;
  return (
    <div className={styles.scroll}>
      <table className={styles.table} aria-label="One switch at a time">
        <thead>
          <tr>
            <th scope="col">Switched off</th>
            <th scope="col">Value vs the sentinel, points (95% CI)</th>
            <th scope="col">Cards that mattered</th>
            <th scope="col">What else moved</th>
          </tr>
        </thead>
        <tbody>
          {names.map((n) => {
            const c = res.comparisons[`${n}_vs_platform`]!;
            const m = res.designs[n]!.metrics;
            const moved: string[] = [];
            if (m.injection_cards !== pm.injection_cards) moved.push(`${m.injection_cards} cards from injected text`);
            if (m.namesake_cards !== pm.namesake_cards) moved.push(`${m.namesake_cards} cards about namesakes`);
            if (m.rumour_cards !== pm.rumour_cards) moved.push(`${m.rumour_cards} cards from rumours that died`);
            if (m.duplicate_cards !== pm.duplicate_cards) moved.push(`${m.duplicate_cards} duplicates`);
            if (Math.abs(m.holds_per_week - pm.holds_per_week) > 0.5) moved.push(`${m.holds_per_week.toFixed(1)} articles a week for the desk (was ${pm.holds_per_week.toFixed(1)})`);
            if (m.suppressed_material !== pm.suppressed_material) moved.push(`${m.suppressed_material} material cards hidden by memory`);
            if (Math.abs(m.cost_eur_per_week - pm.cost_eur_per_week) > 0.01) moved.push(`model cost €${m.cost_eur_per_week.toFixed(2)} a week (was €${pm.cost_eur_per_week.toFixed(2)})`);
            return (
              <tr key={n}>
                <th scope="row">{res.designs[n]!.label}</th>
                <td className={styles.whiskerCell}>
                  <Whisker lo={c.lo} hi={c.hi} diff={c.diff} min={min} max={max} />
                  <span>
                    {pts(c.diff)} ({pts(c.lo)} to {pts(c.hi)})
                  </span>
                </td>
                <td>{pct(m.precision, 0)}</td>
                <td className={styles.moved}>{moved.join("; ") || "Nothing beyond noise"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
