import type { ReactElement, ReactNode } from "react";
import { ArrowUpRight, Sparkles } from "lucide-react";
import styles from "./ChatWelcome.module.less";

const BRAND_MARK = `${import.meta.env.BASE_URL}brand-avatar.gif`;

export function ChatWelcome({
  greeting,
  description,
  avatar,
  prompts,
  onSubmit,
}: {
  greeting?: ReactNode;
  description?: ReactNode;
  avatar?: ReactNode;
  prompts?: (
    | string
    | { label?: ReactNode; value: string; icon?: ReactElement }
  )[];
  onSubmit: (data: { query: string }) => void;
}) {
  // Prefer composed brand lockup (animated mark + HTML text) so light/dark
  // themes never show a baked rectangular background from a wide GIF.
  const brand =
    typeof avatar === "string" || avatar == null ? (
      <div className={styles.brand}>
        <img
          src={typeof avatar === "string" ? avatar : BRAND_MARK}
          alt=""
          className={styles.brandMark}
        />
        <div className={styles.brandCopy}>
          <div className={styles.brandTitle}>小蜜蜂</div>
          <div className={styles.brandSubtitle}>金融声誉智护平台</div>
        </div>
      </div>
    ) : (
      avatar
    );

  return (
    <section className={styles.welcome}>
      {brand}
      <div className={styles.greeting} role="heading" aria-level={2}>
        {greeting}
      </div>
      {description && <p>{description}</p>}
      {!!prompts?.length && (
        <div className={styles.prompts}>
          {prompts.map((item) => {
            const prompt = typeof item === "string" ? { value: item } : item;
            return (
              <button
                key={prompt.value}
                type="button"
                data-press
                onClick={() => onSubmit({ query: prompt.value })}
              >
                {prompt.icon ?? <Sparkles size={17} aria-hidden="true" />}
                <span>{prompt.label || prompt.value}</span>
                <ArrowUpRight size={16} aria-hidden="true" />
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
