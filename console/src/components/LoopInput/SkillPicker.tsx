import { ChevronDown, Library, Plus, Sparkles, X } from "lucide-react";
import { Modal, Popover, Tooltip } from "antd";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import type { SkillSpec } from "../../api/types";
import { useIsMobile } from "../../hooks/useIsMobile";
import { OsDrawer } from "../../os/OsOverlay";
import {
  getActiveSenderTextarea,
  setTextareaValue,
} from "../../pages/Chat/utils";
import { BEEAGENT_ORG_PROVIDER_KEY } from "../../pages/Settings/Market/orgMarketSource";
import {
  OFFICIAL_SKILL_SET,
  extractOfficialSkillPrefix,
  listPickerSkills,
  useSkillPickerStore,
} from "../../stores/skillPickerStore";
import styles from "./index.module.less";
import skillStyles from "./SkillPicker.module.less";

interface SkillPickerProps {
  skills: SkillSpec[];
  className?: string;
  compact?: boolean;
  onSkillsChanged?: () => void;
}

function skillLabelKey(name: string): string {
  return `chat.skillPicker.skills.${name}`;
}

function skillHintKey(name: string): string {
  return `chat.skillPicker.hints.${name}`;
}

function resolveSkillLabel(
  skill: SkillSpec,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const key = skillLabelKey(skill.name);
  const translated = t(key, { defaultValue: "" });
  if (translated && translated !== key) return translated;
  return skill.name;
}

function resolveSkillHint(
  skill: SkillSpec,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (!OFFICIAL_SKILL_SET.has(skill.name)) {
    return (
      skill.description?.trim() ||
      t("chat.skillPicker.orgSkillHint", { defaultValue: "组织技能" })
    );
  }
  const key = skillHintKey(skill.name);
  const translated = t(key, { defaultValue: "" });
  if (translated && translated !== key) return translated;
  return `/${skill.name}`;
}

/** If the composer still has a raw official prefix, absorb it into picker state. */
function absorbPrefixFromTextarea(
  setSelectedSkill: (skill: string | null) => void,
  allowed: Set<string>,
): void {
  const textarea = getActiveSenderTextarea();
  if (!textarea) return;
  const extracted = extractOfficialSkillPrefix(textarea.value);
  if (!extracted || !allowed.has(extracted.skill)) return;
  setSelectedSkill(extracted.skill);
  setTextareaValue(textarea, extracted.rest);
}

export function SkillPicker({
  skills,
  className,
  compact = false,
  onSkillsChanged: _onSkillsChanged,
}: SkillPickerProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const selectedName = useSkillPickerStore((state) => state.selectedSkill);
  const setSelectedSkill = useSkillPickerStore(
    (state) => state.setSelectedSkill,
  );

  const pickerSkills = useMemo(() => listPickerSkills(skills), [skills]);
  const allowedNames = useMemo(
    () => new Set(pickerSkills.map((skill) => skill.name)),
    [pickerSkills],
  );

  const selectedSkill =
    pickerSkills.find((skill) => skill.name === selectedName) ?? null;

  // One-time cleanup if a previous build left `/skill` plain text in the box.
  useEffect(() => {
    absorbPrefixFromTextarea(setSelectedSkill, allowedNames);
  }, [setSelectedSkill, allowedNames]);

  const handleOpenChange = (next: boolean) => {
    if (next) {
      absorbPrefixFromTextarea(setSelectedSkill, allowedNames);
    }
    setOpen(next);
  };

  const pickSkill = (skill: SkillSpec | null) => {
    const textarea = getActiveSenderTextarea();
    // Keep the composer clean — prefix is applied on submit.
    if (textarea) {
      const extracted = extractOfficialSkillPrefix(textarea.value);
      if (extracted) setTextareaValue(textarea, extracted.rest);
    }
    setSelectedSkill(skill?.name ?? null);
    setOpen(false);
    textarea?.focus();
  };

  const openCreateGuide = () => {
    setOpen(false);
    setGuideOpen(true);
  };

  const openOrgMarket = () => {
    setOpen(false);
    // Reuse stock Market UI; org catalog is registered as provider beeagent-org.
    navigate(`/market?tab=skills&source=${BEEAGENT_ORG_PROVIDER_KEY}`);
  };

  const content = (
    <div className={`${styles.modeMenu} ${skillStyles.menu}`}>
      <div className={styles.menuHeader}>
        <div>
          <div className={styles.menuTitle}>{t("chat.skillPicker.title")}</div>
          <div className={styles.menuHint}>{t("chat.skillPicker.hint")}</div>
        </div>
        {isMobile && (
          <div className={styles.menuActions}>
            <button
              aria-label={t("common.close")}
              className={styles.settingsButton}
              onClick={() => setOpen(false)}
              type="button"
            >
              <X size={18} />
            </button>
          </div>
        )}
      </div>
      <div className={`${styles.modeList} ${skillStyles.list}`} role="listbox">
        <section className={styles.modeGroup}>
          {selectedSkill ? (
            <button
              aria-selected={false}
              className={styles.modeOption}
              onClick={() => pickSkill(null)}
              role="option"
              type="button"
            >
              <span className={styles.optionIcon}>
                <X size={16} />
              </span>
              <span className={styles.optionCopy}>
                <span className={styles.optionName}>
                  {t("chat.skillPicker.clear")}
                </span>
                <span className={styles.optionDescription}>
                  {t("chat.skillPicker.clearHint")}
                </span>
              </span>
            </button>
          ) : null}
          {pickerSkills.map((skill) => {
            const selected = skill.name === selectedName;
            const isOrg = !OFFICIAL_SKILL_SET.has(skill.name);
            return (
              <button
                aria-selected={selected}
                className={`${styles.modeOption} ${
                  selected ? styles.selected : ""
                }`}
                key={skill.name}
                onClick={() => pickSkill(skill)}
                role="option"
                type="button"
              >
                <span className={styles.optionIcon}>
                  {isOrg ? (
                    <Library size={16} />
                  ) : (
                    <Sparkles size={16} />
                  )}
                </span>
                <span className={styles.optionCopy}>
                  <span className={styles.optionName}>
                    {resolveSkillLabel(skill, t)}
                  </span>
                  <span className={styles.optionDescription}>
                    {resolveSkillHint(skill, t)}
                  </span>
                </span>
              </button>
            );
          })}
          <button
            aria-selected={false}
            className={`${styles.modeOption} ${skillStyles.createOption}`}
            onClick={openOrgMarket}
            role="option"
            type="button"
          >
            <span className={styles.optionIcon}>
              <Library size={16} />
            </span>
            <span className={styles.optionCopy}>
              <span className={styles.optionName}>
                {t("chat.skillPicker.orgMarketTitle")}
              </span>
              <span className={styles.optionDescription}>
                {t("chat.skillPicker.orgMarketHint")}
              </span>
            </span>
          </button>
          <button
            aria-selected={false}
            className={styles.modeOption}
            onClick={openCreateGuide}
            role="option"
            type="button"
          >
            <span className={styles.optionIcon}>
              <Plus size={16} />
            </span>
            <span className={styles.optionCopy}>
              <span className={styles.optionName}>
                {t("chat.skillPicker.createSkill")}
              </span>
              <span className={styles.optionDescription}>
                {t("chat.skillPicker.createSkillHint")}
              </span>
            </span>
          </button>
        </section>
      </div>
    </div>
  );

  const guideModal = (
    <Modal
      title={t("chat.skillPicker.createGuideTitle")}
      open={guideOpen}
      onCancel={() => setGuideOpen(false)}
      onOk={() => setGuideOpen(false)}
      okText={t("chat.skillPicker.createGuideOk")}
      cancelButtonProps={{ style: { display: "none" } }}
      centered
      destroyOnHidden
    >
      <div className={skillStyles.guideBody}>
        <p>{t("chat.skillPicker.createGuideIntro")}</p>
        <ol>
          <li>{t("chat.skillPicker.createGuideStep1")}</li>
          <li>{t("chat.skillPicker.createGuideStep2")}</li>
          <li>{t("chat.skillPicker.createGuideStep3")}</li>
        </ol>
        <p className={skillStyles.guideExampleLabel}>
          {t("chat.skillPicker.createGuideExampleLabel")}
        </p>
        <blockquote className={skillStyles.guideExample}>
          {t("chat.skillPicker.createGuideExample")}
        </blockquote>
        <p className={skillStyles.guideFooter}>
          {t("chat.skillPicker.createGuideFooter")}
        </p>
      </div>
    </Modal>
  );

  const triggerLabel = selectedSkill
    ? resolveSkillLabel(selectedSkill, t)
    : t("chat.skillPicker.trigger");

  const triggerButton = (
    <button
      aria-expanded={open}
      aria-haspopup="listbox"
      aria-label={t("chat.skillPicker.aria")}
      className={[
        styles.modeTrigger,
        selectedSkill ? skillStyles.selectedTrigger : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={isMobile ? () => handleOpenChange(!open) : undefined}
      type="button"
    >
      <Sparkles size={14} />
      {!compact && (
        <>
          <span className={selectedSkill ? skillStyles.selectedLabel : undefined}>
            {triggerLabel}
          </span>
          <ChevronDown size={13} />
        </>
      )}
    </button>
  );

  if (isMobile) {
    return (
      <>
        {compact ? (
          <Tooltip title={triggerLabel}>{triggerButton}</Tooltip>
        ) : (
          triggerButton
        )}
        <OsDrawer
          aria-label={t("chat.skillPicker.title")}
          open={open}
          placement="bottom"
          height="auto"
          closable={false}
          destroyOnHidden
          rootClassName={styles.modeDrawer}
          onClose={() => setOpen(false)}
          styles={{
            body: { padding: 0, overflow: "hidden" },
            content: {
              borderRadius: "14px 14px 0 0",
              overflow: "hidden",
            },
            wrapper: { maxHeight: "min(56dvh, 480px)" },
          }}
        >
          {content}
        </OsDrawer>
        {guideModal}
      </>
    );
  }

  return (
    <>
      <Popover
        arrow={false}
        content={content}
        onOpenChange={handleOpenChange}
        open={open}
        classNames={{ root: `${styles.modePopover} ${skillStyles.popover}` }}
        placement="topLeft"
        trigger="click"
        destroyOnHidden
      >
        {triggerButton}
      </Popover>
      {guideModal}
    </>
  );
}
