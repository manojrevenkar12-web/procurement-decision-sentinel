import type { SplitReport } from "../../shared/data/report";
import { CAUSES } from "../../shared/format";
import styles from "./results.module.css";

const MAIN = ["status_quo", "model_alone", "platform"];

export function FalseCards({ res }: { res: SplitReport }) {
  const names = MAIN.filter((n) => res.designs[n]);
  const causes = Object.keys(res.designs.platform?.metrics.false_causes ?? {});
  return (
    <div className={styles.scroll}>
      <table className={styles.table} aria-label="Why cards did not matter">
        <thead>
          <tr>
            <th scope="col">Why a card did not matter</th>
            {names.map((n) => (
              <th scope="col" key={n}>
                {res.designs[n]!.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {causes.map((c) => (
            <tr key={c}>
              <th scope="row">{CAUSES[c] ?? c}</th>
              {names.map((n) => (
                <td key={n} className={res.designs[n]!.metrics.false_causes[c] ? undefined : styles.zero}>
                  {res.designs[n]!.metrics.false_causes[c]}
                </td>
              ))}
            </tr>
          ))}
          <tr>
            <th scope="row">A duplicate of an earlier card</th>
            {names.map((n) => (
              <td key={n} className={res.designs[n]!.metrics.duplicate_cards ? undefined : styles.zero}>
                {res.designs[n]!.metrics.duplicate_cards}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">Never reviewed: the queue was too long</th>
            {names.map((n) => (
              <td key={n} className={res.designs[n]!.metrics.unreviewed_cards ? undefined : styles.zero}>
                {res.designs[n]!.metrics.unreviewed_cards}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
