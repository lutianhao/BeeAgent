import {
  Alert,
  Button,
  Input,
  Modal,
  Radio,
  Select,
  Space,
  Upload,
  message,
} from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { Upload as UploadIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  hubApi,
  ORG_SKILL_CATEGORY_OPTIONS,
  type HubOrgSkill,
  type HubOrgSkillCategory,
  type HubOrgSkillDetail,
} from "../../api/modules/hub";

interface PublishOrgSkillModalProps {
  open: boolean;
  onClose: () => void;
  onPublished?: (skill?: HubOrgSkill) => void;
  /** When set, modal opens in "publish new version" mode for this skill. */
  editSkill?: HubOrgSkillDetail | HubOrgSkill | null;
}

const SAMPLE_SKILL_MD = `---
name: my-custom-skill
description: "一句话说明何时使用本技能"
metadata:
  qwenpaw:
    emoji: "🛠️"
---

# 我的自定义技能

说明流程与输出格式。可在同级目录附带：

- \`scripts/\` 可执行脚本
- \`references/\` 按需加载文档
- \`assets/\` 模板与静态资源
`;

type PublishMode = "zip" | "markdown";

function hasUseCaseHint(text: string) {
  return /(何时|适用|用于|当.{0,12}(时|用)|use when|when to|适用于)/i.test(
    text.trim(),
  );
}

/** Publish / update dialog for BeeAgent org skill library. */
export function PublishOrgSkillModal({
  open,
  onClose,
  onPublished,
  editSkill = null,
}: PublishOrgSkillModalProps) {
  const { t } = useTranslation();
  const isUpdateMode = Boolean(editSkill?.skill_id);
  const [mode, setMode] = useState<PublishMode>("zip");
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [versionText, setVersionText] = useState("");
  const [changelog, setChangelog] = useState("");
  const [visibility, setVisibility] = useState<"personal" | "org" | "public">(
    "personal",
  );
  const [category, setCategory] = useState<HubOrgSkillCategory>("other");
  const [contentMd, setContentMd] = useState(SAMPLE_SKILL_MD);
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [publishing, setPublishing] = useState(false);
  const [mySkills, setMySkills] = useState<HubOrgSkill[]>([]);

  const reset = () => {
    setMode("zip");
    setName("");
    setDisplayName("");
    setDescription("");
    setVersionText("");
    setChangelog("");
    setVisibility("personal");
    setCategory("other");
    setContentMd(SAMPLE_SKILL_MD);
    setZipFile(null);
    setFileList([]);
  };

  useEffect(() => {
    if (!open) return;
    if (editSkill) {
      setMode("zip");
      setName(editSkill.name);
      setDisplayName(editSkill.display_name || editSkill.name);
      setDescription(editSkill.description || "");
      setVersionText("");
      setChangelog("");
      setVisibility(
        editSkill.visibility === "public" ||
          editSkill.visibility === "personal"
          ? editSkill.visibility
          : "org",
      );
      setCategory(editSkill.category || "other");
      {
        const md =
          "content_md" in editSkill
            ? String(editSkill.content_md || "").trim()
            : "";
        setContentMd(
          md || SAMPLE_SKILL_MD.replace("my-custom-skill", editSkill.name),
        );
      }
      setZipFile(null);
      setFileList([]);
      return;
    }
    reset();
  }, [open, editSkill]);

  useEffect(() => {
    if (!open || isUpdateMode) return;
    let cancelled = false;
    void hubApi
      .listOrgSkills(true)
      .then((res) => {
        if (!cancelled) setMySkills(res.items || []);
      })
      .catch(() => {
        if (!cancelled) setMySkills([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open, isUpdateMode]);

  const matchedExisting = useMemo(() => {
    if (isUpdateMode) return editSkill;
    const key = name.trim().toLowerCase();
    if (!key) return null;
    return mySkills.find((s) => s.name === key) || null;
  }, [editSkill, isUpdateMode, mySkills, name]);

  const willUpdate = Boolean(matchedExisting);

  const canPublish =
    mode === "zip"
      ? Boolean(zipFile)
      : Boolean(name.trim() && contentMd.trim().length >= 20);

  const doPublish = async () => {
    const desc = description.trim();
    if (mode === "markdown" && (!desc || !hasUseCaseHint(desc))) {
      message.error(t("chat.skillPicker.orgMarketDescUseCaseRequired"));
      return;
    }
    if (mode === "zip" && desc && !hasUseCaseHint(desc)) {
      message.error(t("chat.skillPicker.orgMarketDescUseCaseRequired"));
      return;
    }
    if (willUpdate && !changelog.trim()) {
      message.warning(t("chat.skillPicker.orgMarketChangelogRecommended"));
    }
    setPublishing(true);
    try {
      let skill: HubOrgSkill;
      const lockedName = (matchedExisting?.name || name).trim();
      if (mode === "zip") {
        if (!zipFile) {
          message.error(t("chat.skillPicker.orgMarketZipRequired"));
          return;
        }
        skill = await hubApi.publishOrgSkillZip({
          file: zipFile,
          // Always send name when updating so zip stays bound to the same skill.
          name: willUpdate ? lockedName : name.trim() || undefined,
          display_name: displayName.trim() || undefined,
          description: desc || undefined,
          version_text: versionText.trim() || undefined,
          changelog: changelog.trim() || undefined,
          visibility,
          category,
        });
      } else {
        skill = await hubApi.publishOrgSkill({
          name: lockedName,
          display_name: displayName.trim() || lockedName,
          description: desc,
          content_md: contentMd,
          version_text: versionText.trim() || undefined,
          changelog: changelog.trim() || undefined,
          visibility,
          category,
        });
      }
      if (skill.is_update) {
        message.success(
          t("chat.skillPicker.orgMarketUpdated", {
            version: skill.version_text,
            previous: skill.previous_version || "-",
            defaultValue: "已更新到 v{{version}}（原 {{previous}}）",
          }),
        );
      } else {
        message.success(
          t("chat.skillPicker.orgMarketPublishedVersion", {
            version: skill.version_text,
            defaultValue: "发布成功（v{{version}}）",
          }),
        );
      }
      if (!editSkill) reset();
      onPublished?.(skill);
      onClose();
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

  const handlePublish = () => {
    if (!canPublish) return;
    if (willUpdate && matchedExisting) {
      Modal.confirm({
        title: t("chat.skillPicker.orgMarketUpdateConfirmTitle"),
        content: t("chat.skillPicker.orgMarketUpdateConfirmBody", {
          name: matchedExisting.display_name || matchedExisting.name,
          version: matchedExisting.version_text || "-",
          next:
            versionText.trim() ||
            t("chat.skillPicker.orgMarketAutoBump", {
              defaultValue: "自动 patch +1",
            }),
        }),
        okText: t("chat.skillPicker.orgMarketPublishUpdate"),
        cancelText: t("common.cancel", { defaultValue: "取消" }),
        onOk: () => doPublish(),
      });
      return;
    }
    void doPublish();
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={
        isUpdateMode
          ? t("chat.skillPicker.orgMarketUpdateTitle")
          : t("chat.skillPicker.orgMarketPublish")
      }
      footer={null}
      width={680}
      destroyOnClose
    >
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <Alert
          type={willUpdate ? "warning" : "info"}
          showIcon
          message={
            willUpdate
              ? t("chat.skillPicker.orgMarketUpdateAlert", {
                  name: matchedExisting?.display_name || matchedExisting?.name,
                  version: matchedExisting?.version_text || "-",
                })
              : t("chat.skillPicker.orgMarketCreateAlert")
          }
        />

        {!isUpdateMode && mySkills.length > 0 ? (
          <div>
            <div
              style={{
                marginBottom: 8,
                color: "var(--color-text-secondary)",
              }}
            >
              {t("chat.skillPicker.orgMarketUpdateExistingHint", {
                defaultValue:
                  "要更新已发布的技能？先选中下方条目，再上传新包（会自动升版本）。",
              })}
            </div>
            <Select
              allowClear
              showSearch
              style={{ width: "100%" }}
              placeholder={t("chat.skillPicker.orgMarketUpdateExistingPlaceholder", {
                defaultValue: "选择要更新的已有技能（可选）",
              })}
              optionFilterProp="label"
              value={matchedExisting?.skill_id}
              options={mySkills.map((s) => ({
                value: s.skill_id,
                label: `${s.display_name || s.name} · v${s.version_text || "-"} (${s.name})`,
              }))}
              onChange={(skillId) => {
                if (!skillId) {
                  setName("");
                  setDisplayName("");
                  setDescription("");
                  setVersionText("");
                  setChangelog("");
                  return;
                }
                const picked = mySkills.find((s) => s.skill_id === skillId);
                if (!picked) return;
                setName(picked.name);
                setDisplayName(picked.display_name || picked.name);
                setDescription(picked.description || "");
                setVersionText("");
                setChangelog("");
                setVisibility(
                  picked.visibility === "public" ||
                    picked.visibility === "personal"
                    ? picked.visibility
                    : "org",
                );
                setCategory(picked.category || "other");
              }}
            />
          </div>
        ) : null}

        <div>
          <div style={{ marginBottom: 8, color: "var(--color-text-secondary)" }}>
            {t("chat.skillPicker.orgMarketBundleHint")}
          </div>
          <Radio.Group
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            optionType="button"
            buttonStyle="solid"
          >
            <Radio.Button value="zip">
              {t("chat.skillPicker.orgMarketModeZip")}
            </Radio.Button>
            <Radio.Button value="markdown">
              {t("chat.skillPicker.orgMarketModeMarkdown")}
            </Radio.Button>
          </Radio.Group>
        </div>

        {mode === "zip" ? (
          <Upload.Dragger
            accept=".zip,application/zip"
            maxCount={1}
            fileList={fileList}
            beforeUpload={(file) => {
              setZipFile(file);
              setFileList([
                {
                  uid: file.uid,
                  name: file.name,
                  status: "done",
                  size: file.size,
                },
              ]);
              return false;
            }}
            onRemove={() => {
              setZipFile(null);
              setFileList([]);
            }}
          >
            <p className="ant-upload-drag-icon">
              <UploadIcon size={28} />
            </p>
            <p className="ant-upload-text">
              {t("chat.skillPicker.orgMarketZipDrop")}
            </p>
            <p className="ant-upload-hint">
              {willUpdate
                ? t("chat.skillPicker.orgMarketZipUpdateHint", {
                    name: matchedExisting?.name,
                  })
                : t("chat.skillPicker.orgMarketZipStructure")}
            </p>
          </Upload.Dragger>
        ) : null}

        <Input
          placeholder={
            mode === "zip"
              ? t("chat.skillPicker.orgMarketNameOptionalPlaceholder")
              : t("chat.skillPicker.orgMarketNamePlaceholder")
          }
          value={name}
          disabled={isUpdateMode}
          onChange={(e) => setName(e.target.value)}
          addonBefore={
            isUpdateMode
              ? t("chat.skillPicker.orgMarketNameLocked", {
                  defaultValue: "技能名",
                })
              : undefined
          }
        />
        <Input
          placeholder={t("chat.skillPicker.orgMarketDisplayPlaceholder")}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
        <Select
          style={{ width: "100%" }}
          value={category}
          options={ORG_SKILL_CATEGORY_OPTIONS}
          onChange={setCategory}
          placeholder={t("chat.skillPicker.orgMarketCategory", {
            defaultValue: "业务域（可与官方专项对齐，也可选工具/文案等）",
          })}
        />
        <Input.TextArea
          rows={2}
          placeholder={t("chat.skillPicker.orgMarketDescPlaceholder")}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <div
          style={{
            marginTop: -4,
            fontSize: 12,
            color: "var(--color-text-secondary)",
          }}
        >
          {t("chat.skillPicker.orgMarketDescUseCaseHint")}
        </div>
        <div>
          <Input
            placeholder={t("chat.skillPicker.orgMarketVersionPlaceholder")}
            value={versionText}
            onChange={(e) => setVersionText(e.target.value)}
          />
          <div
            style={{
              marginTop: 6,
              fontSize: 12,
              color: "var(--color-text-secondary)",
            }}
          >
            {willUpdate
              ? t("chat.skillPicker.orgMarketVersionUpdateHint")
              : t("chat.skillPicker.orgMarketVersionHint")}
          </div>
        </div>
        <Input.TextArea
          rows={2}
          placeholder={
            willUpdate
              ? t("chat.skillPicker.orgMarketChangelogUpdatePlaceholder")
              : t("chat.skillPicker.orgMarketChangelogPlaceholder")
          }
          value={changelog}
          onChange={(e) => setChangelog(e.target.value)}
        />
        <Radio.Group
          value={visibility}
          onChange={(e) => setVisibility(e.target.value)}
        >
          <Radio value="personal">仅自己（默认）</Radio>
          <Radio value="org">
            {t("chat.skillPicker.orgMarketVisibilityOrg")}
          </Radio>
          <Radio value="public">
            {t("chat.skillPicker.orgMarketVisibilityPublic")}
          </Radio>
        </Radio.Group>

        {mode === "markdown" ? (
          <Input.TextArea
            rows={12}
            value={contentMd}
            onChange={(e) => setContentMd(e.target.value)}
            style={{ fontFamily: "ui-monospace, monospace", fontSize: 12 }}
          />
        ) : null}

        <Button
          type="primary"
          loading={publishing}
          disabled={!canPublish}
          onClick={handlePublish}
        >
          {willUpdate
            ? t("chat.skillPicker.orgMarketPublishUpdate")
            : t("chat.skillPicker.orgMarketPublishAction")}
        </Button>
      </Space>
    </Modal>
  );
}
