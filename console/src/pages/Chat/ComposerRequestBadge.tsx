import { Library, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";

import styles from "./ComposerRequestBadge.module.less";

function skillTitle(
  skillName: string,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const key = `chat.skillPicker.skills.${skillName}`;
  const translated = t(key, { defaultValue: "" });
  if (translated && translated !== key) return translated;
  return skillName;
}

/** Light chip above the user bubble: which skill / KB mode was applied. */
export function ComposerRequestBadge({
  skillName,
  orgKb,
}: {
  skillName?: string | null;
  orgKb?: boolean;
}) {
  const { t } = useTranslation();
  if (!skillName && !orgKb) return null;

  return (
    <div className={styles.row} aria-hidden>
      {skillName ? (
        <span className={styles.chip}>
          <Sparkles size={12} />
          {t("chat.skillChip", {
            name: skillTitle(skillName, t),
            defaultValue: `专项 · {{name}}`,
          })}
        </span>
      ) : null}
      {orgKb ? (
        <span className={styles.chip}>
          <Library size={12} />
          {t("chat.orgKbChip", { defaultValue: "企业知识" })}
        </span>
      ) : null}
    </div>
  );
}
