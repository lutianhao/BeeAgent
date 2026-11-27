import { memo, useEffect, useMemo, useState } from "react";
import { Button, Drawer } from "@agentscope-ai/design";
import { Modal, message, Select, Space, Spin, Tag } from "antd";
import { useTranslation } from "react-i18next";
import type { MarketResult } from "../../../../api/modules/market";
import {
  hubApi,
  ORG_SKILL_CATEGORY_OPTIONS,
  type HubOrgSkillFile,
} from "../../../../api/modules/hub";
import {
  formatOrgUpdatedAt,
  isBeeagentOrgSource,
  isOrgSkillInstalled,
  isOrgSkillPinned,
  isOrgSkillUpdateAvailable,
  orgSkillCapDelist,
  orgSkillCapDeleteListing,
  orgSkillCapFeature,
  orgSkillCapListToOrg,
  orgSkillCapRelist,
  orgSkillCapRestore,
  orgSkillCapShare,
  parseOrgSkillIdFromUrl,
} from "../orgMarketSource";
import { SkillIcon } from "./SkillIcon";
import { sourceLabel } from "./skillSources";
import styles from "./DetailDrawer.module.less";

interface DetailDrawerProps {
  item: MarketResult | null;
  onInstall: () => void;
  onUninstall?: () => void;
  uninstalling?: boolean;
  onClose: () => void;
  /** Publisher can open "publish new version" for their own skill. */
  onRepublish?: () => void;
  canRepublish?: boolean;
  /** Org skill operators can feature / delist / retag. */
  canManage?: boolean;
  onOpsChanged?: () => void;
}

const STAT_KEY_LABELS: Record<string, string> = {
  downloads: "market.stats.downloads",
  installs: "market.stats.installs",
  stars: "market.stats.stars",
  likes: "market.stats.likes",
  views: "market.stats.views",
  category: "market.stats.category",
  updated_at: "market.stats.updatedAt",
  created_at: "market.stats.createdAt",
  installed_version: "market.stats.installedVersion",
  visibility: "market.stats.visibility",
  status: "market.stats.status",
  changelog: "market.stats.changelog",
  bundle: "market.stats.bundle",
  compatibility: "market.stats.compatibility",
  allowed_tools: "market.stats.allowedTools",
};

const HIDDEN_STAT_KEYS = new Set([
  "installed",
  "update_available",
  "pinned",
  "newer_version",
  "skill_name",
  "owner_user_id",
  "category_key",
  "visibility_key",
  "featured",
  "shelf",
  "deleted_at",
  "cap_is_owner",
  "cap_update_version",
  "cap_delist",
  "cap_relist",
  "cap_feature",
  "cap_retag",
  "cap_delete_listing",
  "cap_install",
  "cap_upgrade",
  "cap_uninstall",
  "cap_pin",
  "cap_share",
  "cap_list_to_org",
  "cap_make_personal",
  "cap_restore",
]);

function formatStatValue(key: string, value: string | number): string {
  if ((key === "updated_at" || key === "created_at") && typeof value === "string") {
    return formatOrgUpdatedAt(value) || value;
  }
  if (typeof value === "number") return value.toLocaleString();
  return String(value);
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export const DetailDrawer = memo(function DetailDrawer({
  item,
  onInstall,
  onUninstall,
  uninstalling = false,
  onClose,
  onRepublish,
  canRepublish = false,
  canManage = false,
  onOpsChanged,
}: DetailDrawerProps) {
  const { t } = useTranslation();
  const open = !!item;
  const missing = t("market.detail.missing");
  const orgInstalled = item ? isOrgSkillInstalled(item) : false;
  const updateAvailable = item ? isOrgSkillUpdateAvailable(item) : false;
  const pinned = item ? isOrgSkillPinned(item) : false;
  const isOrg = item ? isBeeagentOrgSource(item.source) : false;
  const primaryLabel = updateAvailable
    ? t("market.update")
    : orgInstalled
      ? t("market.uninstall")
      : isOrg
        ? t("market.install")
        : t("common.save");

  const [files, setFiles] = useState<HubOrgSkillFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [filesError, setFilesError] = useState("");
  const [opsBusy, setOpsBusy] = useState(false);
  const [pinBusy, setPinBusy] = useState(false);
  const [shareBusy, setShareBusy] = useState(false);
  const featured = item?.stats?.featured === 1 || item?.stats?.featured === "1";
  const delisted = item?.stats?.shelf === "已下架";
  const inRecycle = item?.stats?.shelf === "回收站";
  const categoryKey = String(item?.stats?.category_key || "other");
  const visibilityKey = String(item?.stats?.visibility_key || "org");
  const installCount = Number(item?.stats?.installs ?? 0);
  const canDelist = item ? orgSkillCapDelist(item) || canManage : false;
  const canRelist = item ? orgSkillCapRelist(item) || canManage : false;
  const canFeature = item ? orgSkillCapFeature(item) || canManage : false;
  const canShare = item ? orgSkillCapShare(item) : false;
  const canListToOrg = item ? orgSkillCapListToOrg(item) : false;
  const canRestore = item ? orgSkillCapRestore(item) : false;
  const canDeleteListing = item
    ? orgSkillCapDeleteListing(item) || canManage
    : false;
  const showOwnerOps =
    isOrg &&
    (canDelist || canRelist || canListToOrg || canRestore || canDeleteListing);
  const showManageOps = isOrg && (canManage || canFeature);

  useEffect(() => {
    if (!item || !isBeeagentOrgSource(item.source)) {
      setFiles([]);
      setFilesError("");
      setFilesLoading(false);
      return;
    }
    const skillId = parseOrgSkillIdFromUrl(item.source_url) || item.slug;
    let cancelled = false;
    setFilesLoading(true);
    setFilesError("");
    void hubApi
      .listOrgSkillFiles(skillId)
      .then((res) => {
        if (!cancelled) setFiles(res.files || []);
      })
      .catch((err) => {
        if (!cancelled) {
          setFiles([]);
          setFilesError(
            err instanceof Error
              ? err.message
              : t("market.detail.filesLoadFailed"),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setFilesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [item, t]);

  const patchOps = async (body: {
    category?: string;
    featured?: boolean;
    status?: "active" | "delisted";
    visibility?: "personal" | "org" | "public";
  }) => {
    if (!item || !isBeeagentOrgSource(item.source)) return;
    const skillId = parseOrgSkillIdFromUrl(item.source_url) || item.slug;
    setOpsBusy(true);
    try {
      await hubApi.patchOrgSkillOps(skillId, body);
      message.success(
        t("market.opsUpdated", { defaultValue: "运营设置已更新" }),
      );
      onOpsChanged?.();
    } catch (err) {
      message.error(
        err instanceof Error
          ? err.message
          : t("market.opsFailed", { defaultValue: "运营设置失败" }),
      );
    } finally {
      setOpsBusy(false);
    }
  };

  const softDeleteListing = () => {
    if (!item || !isBeeagentOrgSource(item.source)) return;
    const skillId = parseOrgSkillIdFromUrl(item.source_url) || item.slug;
    Modal.confirm({
      title: "确认删除到回收站？",
      content: "删除后 7 天内可在回收站恢复；到期后将永久清除技能包。",
      okText: "移入回收站",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        setOpsBusy(true);
        try {
          await hubApi.deleteOrgSkill(skillId);
          message.success("已移入回收站");
          onOpsChanged?.();
          onClose();
        } catch (err) {
          message.error(err instanceof Error ? err.message : "删除失败");
        } finally {
          setOpsBusy(false);
        }
      },
    });
  };

  const restoreListing = async () => {
    if (!item || !isBeeagentOrgSource(item.source)) return;
    const skillId = parseOrgSkillIdFromUrl(item.source_url) || item.slug;
    setOpsBusy(true);
    try {
      await hubApi.restoreOrgSkill(skillId);
      message.success("已从回收站恢复");
      onOpsChanged?.();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "恢复失败");
    } finally {
      setOpsBusy(false);
    }
  };

  const togglePin = async () => {
    if (!item || !isBeeagentOrgSource(item.source) || !orgInstalled) return;
    const skillId = parseOrgSkillIdFromUrl(item.source_url) || item.slug;
    setPinBusy(true);
    try {
      const next = !pinned;
      await hubApi.pinOrgSkill(skillId, next);
      message.success(
        next
          ? t("market.pinned", { defaultValue: "已钉住当前版本" })
          : t("market.unpinned", { defaultValue: "已解除钉版本" }),
      );
      onOpsChanged?.();
    } catch (err) {
      message.error(
        err instanceof Error
          ? err.message
          : t("market.pinFailed", { defaultValue: "钉版本失败" }),
      );
    } finally {
      setPinBusy(false);
    }
  };

  const shareSkill = async (makePublic = false) => {
    if (!item || !isBeeagentOrgSource(item.source) || !canShare) return;
    const skillId = parseOrgSkillIdFromUrl(item.source_url) || item.slug;
    setShareBusy(true);
    try {
      const res = await hubApi.shareOrgSkill(skillId, {
        make_public: makePublic,
      });
      const text = res.share_text || res.share_path;
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        message.success(
          t("market.shareCopied", {
            defaultValue: "分享文案已复制到剪贴板",
          }),
        );
      } else {
        message.success(text);
      }
      if (makePublic) onOpsChanged?.();
    } catch (err) {
      message.error(
        err instanceof Error
          ? err.message
          : t("market.shareFailed", { defaultValue: "分享失败" }),
      );
    } finally {
      setShareBusy(false);
    }
  };

  const rows = useMemo<Array<[string, React.ReactNode]>>(() => {
    if (!item) return [];
    const result: Array<[string, React.ReactNode]> = [
      [
        t("market.detail.author", { defaultValue: "发布者" }),
        item.author || missing,
      ],
      [
        t("market.detail.version"),
        item.version ? `v${item.version}` : missing,
      ],
    ];
    if (item.stats) {
      for (const [key, value] of Object.entries(item.stats)) {
        if (HIDDEN_STAT_KEYS.has(key)) continue;
        const labelKey = STAT_KEY_LABELS[key];
        const label = labelKey ? t(labelKey) : key;
        result.push([label, formatStatValue(key, value)]);
      }
    }
    if (!isOrg) {
      result.push(
        [
          t("market.detail.sourceUrl"),
          <code key="src" className={styles.mono}>
            {item.source_url}
          </code>,
        ],
        [
          t("market.detail.slug"),
          <code key="slug" className={styles.mono}>
            {item.slug}
          </code>,
        ],
      );
    }
    return result;
  }, [item, t, missing, isOrg]);

  return (
    <Drawer
      width={520}
      placement="right"
      title={t("market.detail.title")}
      open={open}
      onClose={onClose}
      destroyOnHidden
      footer={
        item ? (
          <div className={styles.drawerFooter}>
            {canRepublish && onRepublish ? (
              <Button type="default" onClick={onRepublish}>
                {t("market.republish", { defaultValue: "发布新版本" })}
              </Button>
            ) : null}
            {isOrg && canShare ? (
              <Button
                type="default"
                loading={shareBusy}
                onClick={() => void shareSkill(false)}
              >
                {t("market.share", { defaultValue: "分享" })}
              </Button>
            ) : null}
            {isOrg && orgInstalled ? (
              <Button
                type="default"
                loading={pinBusy}
                onClick={() => void togglePin()}
              >
                {pinned
                  ? t("market.unpin", { defaultValue: "解除钉版本" })
                  : t("market.pin", { defaultValue: "钉住版本" })}
              </Button>
            ) : null}
            {orgInstalled && !updateAvailable ? (
              <Button
                type="default"
                danger
                loading={uninstalling}
                disabled={!onUninstall}
                onClick={onUninstall}
              >
                {t("market.uninstall")}
              </Button>
            ) : (
              <Button type="primary" onClick={onInstall}>
                {primaryLabel}
              </Button>
            )}
          </div>
        ) : null
      }
    >
      {item && (
        <>
          <div className={styles.detailHeader}>
            <SkillIcon
              url={item.icon_url}
              alt={item.name}
              source={item.source}
            />
            <div className={styles.detailHeaderText}>
              <h3 className={styles.detailTitle}>
                {item.name}
                {featured ? (
                  <Tag color="gold" style={{ marginLeft: 8 }}>
                    精选
                  </Tag>
                ) : null}
                {isOrg ? (
                  <Tag
                    color={
                      visibilityKey === "personal"
                        ? "default"
                        : visibilityKey === "public"
                          ? "green"
                          : "blue"
                    }
                    style={{ marginLeft: 8 }}
                  >
                    {visibilityKey === "personal"
                      ? "仅自己"
                      : visibilityKey === "public"
                        ? "公开"
                        : "组织内部"}
                  </Tag>
                ) : null}
                {delisted ? (
                  <Tag color="default" style={{ marginLeft: 8 }}>
                    已下架
                  </Tag>
                ) : null}
                {inRecycle ? (
                  <Tag color="red" style={{ marginLeft: 8 }}>
                    回收站
                  </Tag>
                ) : null}
                {pinned ? (
                  <Tag color="purple" style={{ marginLeft: 8 }}>
                    已钉住
                  </Tag>
                ) : null}
              </h3>
              <div className={styles.detailMeta}>
                <span className={styles.sourceBadge}>
                  {sourceLabel(item.source, item.source_label)}
                </span>
                {isOrg ? (
                  <>
                    <span style={{ marginLeft: 8, fontWeight: 600 }}>
                      {t("market.publisherLabel", {
                        name:
                          item.author ||
                          t("market.publisherUnknown", {
                            defaultValue: "未知",
                          }),
                        defaultValue: "发布者 {{name}}",
                      })}
                    </span>
                    <span style={{ marginLeft: 8 }}>
                      {t("market.installCount", {
                        count: installCount,
                        defaultValue: "安装 {{count}}",
                      })}
                    </span>
                  </>
                ) : null}
              </div>
            </div>
          </div>

          <div className={styles.detailDescription}>
            {item.description || t("market.noDescription")}
          </div>

          {showOwnerOps || showManageOps ? (
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 4, fontWeight: 600 }}>
                {canManage ? "运营设置" : "货架管理"}
              </div>
              <div
                style={{
                  marginBottom: 8,
                  fontSize: 12,
                  color: "var(--color-text-secondary, #666)",
                }}
              >
                业务域用于筛选，不必对应某个官方专项；可见性控制谁能在货架看到。
              </div>
              <Space wrap>
                {canManage ? (
                  <Select
                    size="small"
                    style={{ width: 160 }}
                    value={categoryKey}
                    disabled={opsBusy}
                    options={ORG_SKILL_CATEGORY_OPTIONS}
                    placeholder="业务域"
                    onChange={(value) => void patchOps({ category: value })}
                  />
                ) : null}
                {!inRecycle && (canDelist || canRelist || canManage) ? (
                  <Select
                    size="small"
                    style={{ width: 140 }}
                    value={
                      visibilityKey === "personal" ||
                      visibilityKey === "public"
                        ? visibilityKey
                        : "org"
                    }
                    disabled={opsBusy}
                    options={[
                      { value: "personal", label: "仅自己" },
                      { value: "org", label: "组织内部" },
                      { value: "public", label: "公开" },
                    ]}
                    placeholder="可见性"
                    onChange={(value) =>
                      void patchOps({
                        visibility: value as "personal" | "org" | "public",
                      })
                    }
                  />
                ) : null}
                {canListToOrg ? (
                  <Button
                    size="small"
                    type="primary"
                    loading={opsBusy}
                    onClick={() => void patchOps({ visibility: "org" })}
                  >
                    上架到组织
                  </Button>
                ) : null}
                {canFeature && !inRecycle ? (
                  <Button
                    size="small"
                    loading={opsBusy}
                    onClick={() => void patchOps({ featured: !featured })}
                  >
                    {featured ? "取消精选" : "设为精选"}
                  </Button>
                ) : null}
                {!inRecycle && (delisted ? canRelist : canDelist) ? (
                  <Button
                    size="small"
                    danger={!delisted}
                    loading={opsBusy}
                    onClick={() => {
                      if (delisted) {
                        void patchOps({ status: "active" });
                        return;
                      }
                      Modal.confirm({
                        title: "确认下架？",
                        content:
                          "下架后同事在组织技能货架默认看不到该技能；你仍可在「含已下架」或详情里重新上架。",
                        okText: "确认下架",
                        okType: "danger",
                        cancelText: "取消",
                        onOk: () => patchOps({ status: "delisted" }),
                      });
                    }}
                  >
                    {delisted ? "重新上架" : "下架"}
                  </Button>
                ) : null}
                {canRestore && inRecycle ? (
                  <Button
                    size="small"
                    type="primary"
                    loading={opsBusy}
                    onClick={() => void restoreListing()}
                  >
                    从回收站恢复
                  </Button>
                ) : null}
                {canDeleteListing && !inRecycle ? (
                  <Button
                    size="small"
                    danger
                    loading={opsBusy}
                    onClick={() => softDeleteListing()}
                  >
                    删除
                  </Button>
                ) : null}
              </Space>
            </div>
          ) : null}

          <dl className={styles.detailRows}>
            {rows.map(([key, value]) => (
              <div className={styles.detailRow} key={key}>
                <dt className={styles.detailKey}>{key}</dt>
                <dd className={styles.detailValue}>{value}</dd>
              </div>
            ))}
          </dl>

          {isOrg ? (
            <div className={styles.fileSection}>
              <div className={styles.fileSectionTitle}>
                {t("market.detail.files")}
              </div>
              {filesLoading ? (
                <div className={styles.fileLoading}>
                  <Spin size="small" />
                </div>
              ) : filesError ? (
                <div className={styles.fileError}>{filesError}</div>
              ) : files.length === 0 ? (
                <div className={styles.fileEmpty}>
                  {t("market.detail.filesEmpty")}
                </div>
              ) : (
                <ul className={styles.fileList}>
                  {files.map((file) => (
                    <li key={file.path} className={styles.fileItem}>
                      <code className={styles.mono}>{file.path}</code>
                      <span className={styles.fileSize}>
                        {formatBytes(file.size)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}
        </>
      )}
    </Drawer>
  );
});
