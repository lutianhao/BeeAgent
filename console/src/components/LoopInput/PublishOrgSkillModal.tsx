import { Button, Input, Modal, Radio, Space, Upload, message } from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { Upload as UploadIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { hubApi } from "../../api/modules/hub";

interface PublishOrgSkillModalProps {
  open: boolean;
  onClose: () => void;
  onPublished?: () => void;
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

/** Publish-only dialog for BeeAgent org skill library (browse lives in Market). */
export function PublishOrgSkillModal({
  open,
  onClose,
  onPublished,
}: PublishOrgSkillModalProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<PublishMode>("zip");
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<"org" | "public">("org");
  const [contentMd, setContentMd] = useState(SAMPLE_SKILL_MD);
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [publishing, setPublishing] = useState(false);

  const reset = () => {
    setMode("zip");
    setName("");
    setDisplayName("");
    setDescription("");
    setVisibility("org");
    setContentMd(SAMPLE_SKILL_MD);
    setZipFile(null);
    setFileList([]);
  };

  const canPublish =
    mode === "zip"
      ? Boolean(zipFile)
      : Boolean(name.trim() && contentMd.trim().length >= 20);

  const handlePublish = async () => {
    setPublishing(true);
    try {
      if (mode === "zip") {
        if (!zipFile) {
          message.error(t("chat.skillPicker.orgMarketZipRequired"));
          return;
        }
        await hubApi.publishOrgSkillZip({
          file: zipFile,
          name: name.trim() || undefined,
          display_name: displayName.trim() || undefined,
          description: description.trim() || undefined,
          visibility,
        });
      } else {
        await hubApi.publishOrgSkill({
          name: name.trim(),
          display_name: displayName.trim() || name.trim(),
          description: description.trim(),
          content_md: contentMd,
          visibility,
        });
      }
      message.success(t("chat.skillPicker.orgMarketPublished"));
      reset();
      onPublished?.();
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

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={t("chat.skillPicker.orgMarketPublish")}
      footer={null}
      width={680}
      destroyOnClose
    >
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
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
              {t("chat.skillPicker.orgMarketZipStructure")}
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
          onChange={(e) => setName(e.target.value)}
        />
        <Input
          placeholder={t("chat.skillPicker.orgMarketDisplayPlaceholder")}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
        <Input.TextArea
          rows={2}
          placeholder={t("chat.skillPicker.orgMarketDescPlaceholder")}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <Radio.Group
          value={visibility}
          onChange={(e) => setVisibility(e.target.value)}
        >
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
          onClick={() => void handlePublish()}
        >
          {t("chat.skillPicker.orgMarketPublishAction")}
        </Button>
      </Space>
    </Modal>
  );
}
