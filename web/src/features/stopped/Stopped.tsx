import type { MessageView } from "../../shared/data/report";
import { Trace } from "../docket/Docket";
import { Empty } from "../../shared/ui/states";
import styles from "./stopped.module.css";

const TITLES: Record<string, string> = {
  injection: "An article that tries to instruct the model",
  namesake: "A company with our supplier's name",
  rumour: "A report nobody has confirmed",
};

export function Stopped({ messages }: { messages: Record<string, MessageView> }) {
  const keys = Object.keys(TITLES).filter((k) => messages[k]);
  if (!keys.length) return <Empty title="No stopped articles in this sample">The first seed kept no example of an injection, a namesake or a rumour.</Empty>;
  return (
    <div className={styles.grid}>
      {keys.map((k) => {
        const m = messages[k]!;
        return (
          <article key={k} className={styles.item} aria-labelledby={`stopped-${k}`}>
            <h3 id={`stopped-${k}`}>{TITLES[k]}</h3>
            <p className={styles.headline}>{m.headline}</p>
            <p className={styles.body}>{m.body}</p>
            <p className={styles.result}>{m.note}</p>
            <Trace steps={m.trace} />
          </article>
        );
      })}
    </div>
  );
}
