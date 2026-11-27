import { BookOpen, X } from "lucide-react";
import { Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useIsMobile } from "../../hooks/useIsMobile";
import { useOrgKbModeStore } from "../../stores/orgKbModeStore";
import styles from "./index.module.less";
import skillStyles from "./SkillPicker.module.less";

interface OrgKnowledgeControlProps {
  className?: string;
  compact?: boolean;
}

/**
 * Composer toggle for「企业知识」— aligns with 豆包-style explicit KB entry.
 * When on, outbound messages are wrapped to force ``kb_search`` first.
 */
export function OrgKnowledgeControl({
  className,
  compact = false,
}: OrgKnowledgeControlProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const enabled = useOrgKbModeStore((s) => s.enabled);
  const toggle = useOrgKbModeStore((s) => s.toggle);

  const label = t("chat.orgKnowledge.trigger", {
    defaultValue: "企业知识",
  });
  const hint = enabled
    ? t("chat.orgKnowledge.onHint", {
        defaultValue: "已开启：发送时先查组织知识库（再点可关闭）",
      })
    : t("chat.orgKnowledge.offHint", {
        defaultValue: "开启后本轮优先 kb_search；也可输入 /kb",
      });

  const button = (
    <button
      aria-pressed={enabled}
      aria-label={t("chat.orgKnowledge.aria", {
        defaultValue: "企业知识库检索",
      })}
      className={[
        styles.modeTrigger,
        enabled ? skillStyles.selectedTrigger : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={() => toggle()}
      onContextMenu={(e) => {
        e.preventDefault();
        navigate("/knowledge-base");
      }}
      title={hint}
      type="button"
    >
      {enabled ? <X size={14} /> : <BookOpen size={14} />}
      {!compact && (
        <span className={enabled ? skillStyles.selectedLabel : undefined}>
          {label}
        </span>
      )}
    </button>
  );

  if (isMobile) return button;
  return (
    <Tooltip
      title={
        <span>
          {hint}
          <br />
          {t("chat.orgKnowledge.openConsole", {
            defaultValue: "右键打开知识库管理",
          })}
        </span>
      }
    >
      {button}
    </Tooltip>
  );
}
