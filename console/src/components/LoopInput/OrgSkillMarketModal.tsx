import { Button, Input, Modal, Radio, Space, Spin, message } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  hubApi,
  type HubOrgSkill,
} from "../../api/modules/hub";
import skillStyles from "./SkillPicker.module.less";

interface OrgSkillMarketModalProps {
  open: boolean;
  onClose: () => void;
  onInstalled?: () => void;
}

const SAMPLE_SKILL_MD = `---
name: my-custom-skill
description: "一句话说明何时使用本技能"
metadata:
  qwenpaw:
    emoji: "🛠️"
---

# 我的自定义技能

说明流程与输出格式。
`;

export function OrgSkillMarketModal({
  open,
  onClose,
  onInstalled,
}: OrgSkillMarketModalProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<HubOrgSkill[]>([]);
  const [tab, setTab] = useState<"browse" | "publish">("browse");
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<"org" | "public">("org");
  const [contentMd, setContentMd] = useState(SAMPLE_SKILL_MD);
  const [publishing, setPublishing] = useState(false);
  const [installingId, setInstallingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await hubApi.listOrgSkills(false);
      setItems(res.items || []);
    } catch (err) {
      message.error(
        err instanceof Error
          ? err.message
          : t("chat.skillPicker.orgMarketLoadFailed"),
      );
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  const handleInstall = async (skill: HubOrgSkill) => {
    setInstallingId(skill.skill_id);
    try {
      await hubApi.installOrgSkill(skill.skill_id);
      message.success(t("chat.skillPicker.orgMarketInstalled", { name: skill.display_name || skill.name }));
      await refresh();
      onInstalled?.();
    } catch (err) {
      message.error(
        err instanceof Error
          ? err.message
          : t("chat.skillPicker.orgMarketInstallFailed"),
      );
    } finally {
      setInstallingId(null);
    }
  };

  const handlePublish = async () => {
    setPublishing(true);
    try {
      await hubApi.publishOrgSkill({
        name: name.trim(),
        display_name: displayName.trim() || name.trim(),
        description: description.trim(),
        content_md: contentMd,
        visibility,
      });
      message.success(t("chat.skillPicker.orgMarketPublished"));
      setTab("browse");
      setName("");
      setDisplayName("");
      setDescription("");
      setContentMd(SAMPLE_SKILL_MD);
      await refresh();
    } catch (err) {
      message.error(
        err instanceof Error
          ? err.message
          : t("chat.skillPicker.orgMarketPublishFailed"),
      );
    } finally {
      setPublishing(false);
    }
  };

  return (
    <Modal
      title={t("chat.skillPicker.orgMarketTitle")}
      open={open}
      onCancel={onClose}
      footer={null}
      width={640}
      destroyOnHidden
      centered
    >
      <p className={skillStyles.guideFooter}>
        {t("chat.skillPicker.orgMarketIntro")}
      </p>
      <Radio.Group
        value={tab}
        onChange={(e) => setTab(e.target.value)}
        style={{ marginBottom: 12 }}
        optionType="button"
        buttonStyle="solid"
        options={[
          { label: t("chat.skillPicker.orgMarketBrowse"), value: "browse" },
          { label: t("chat.skillPicker.orgMarketPublish"), value: "publish" },
        ]}
      />

      {tab === "browse" ? (
        <div className={skillStyles.orgMarketList}>
          {loading ? (
            <div className={skillStyles.orgMarketEmpty}>
              <Spin />
            </div>
          ) : items.length === 0 ? (
            <div className={skillStyles.orgMarketEmpty}>
              {t("chat.skillPicker.orgMarketEmpty")}
            </div>
          ) : (
            items.map((skill) => (
              <div key={skill.skill_id} className={skillStyles.orgMarketItem}>
                <div className={skillStyles.orgMarketItemCopy}>
                  <div className={skillStyles.orgMarketItemTitle}>
                    <span>{skill.emoji || "🛠️"}</span>
                    <strong>{skill.display_name || skill.name}</strong>
                    <em>
                      {skill.visibility === "org"
                        ? t("chat.skillPicker.orgMarketVisibilityOrg")
                        : t("chat.skillPicker.orgMarketVisibilityPublic")}
                    </em>
                  </div>
                  <div className={skillStyles.orgMarketItemMeta}>
                    {`/${skill.name}`} · {skill.owner_username || "—"}
                  </div>
                  {skill.description ? (
                    <div className={skillStyles.orgMarketItemDesc}>
                      {skill.description}
                    </div>
                  ) : null}
                </div>
                <Button
                  type={skill.installed ? "default" : "primary"}
                  size="small"
                  loading={installingId === skill.skill_id}
                  disabled={skill.installed}
                  onClick={() => void handleInstall(skill)}
                >
                  {skill.installed
                    ? t("chat.skillPicker.orgMarketAlreadyInstalled")
                    : t("chat.skillPicker.orgMarketInstall")}
                </Button>
              </div>
            ))
          )}
        </div>
      ) : (
        <Space direction="vertical" style={{ width: "100%" }} size={10}>
          <Input
            placeholder={t("chat.skillPicker.orgMarketNamePlaceholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Input
            placeholder={t("chat.skillPicker.orgMarketDisplayPlaceholder")}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
          <Input
            placeholder={t("chat.skillPicker.orgMarketDescPlaceholder")}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <Radio.Group
            value={visibility}
            onChange={(e) => setVisibility(e.target.value)}
            options={[
              {
                label: t("chat.skillPicker.orgMarketVisibilityOrg"),
                value: "org",
              },
              {
                label: t("chat.skillPicker.orgMarketVisibilityPublic"),
                value: "public",
              },
            ]}
          />
          <Input.TextArea
            rows={12}
            value={contentMd}
            onChange={(e) => setContentMd(e.target.value)}
            placeholder="SKILL.md"
          />
          <Button
            type="primary"
            loading={publishing}
            onClick={() => void handlePublish()}
            disabled={!name.trim() || contentMd.trim().length < 20}
          >
            {t("chat.skillPicker.orgMarketPublishAction")}
          </Button>
        </Space>
      )}
    </Modal>
  );
}
