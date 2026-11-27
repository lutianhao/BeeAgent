import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { Button, Card, Tooltip } from "@agentscope-ai/design";
import { Download, Eye, Heart, Star } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { MarketResult } from "../../../../api/modules/market";
import {
  formatOrgUpdatedAt,
  isBeeagentOrgSource,
  isOrgSkillInstalled,
  isOrgSkillPinned,
  isOrgSkillUpdateAvailable,
} from "../orgMarketSource";
import { SkillIcon } from "./SkillIcon";
import { sourceLabel } from "./skillSources";
import styles from "./ResultCard.module.less";
import { CommunityFeedback } from "@/components/CommunityFeedback";
import { skillMarketResource } from "@/utils/communityResources";

interface ResultCardProps {
  item: MarketResult;
  onInstall: () => void;
  onUninstall?: () => void;
  uninstalling?: boolean;
  onOpenDetail: () => void;
  /** Owner can publish a new version of this org skill. */
  onRepublish?: () => void;
  canRepublish?: boolean;
  /** Current user owns this org skill (shows「我的」). */
  isMine?: boolean;
}

const useIsMobile = () => {
  const [isMobile, setIsMobile] = useState(
    typeof window !== "undefined" ? window.innerWidth <= 768 : false,
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const handleResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return isMobile;
};

const CURSOR_STYLE = { cursor: "pointer" } as const;

export const ResultCard = memo(function ResultCard({
  item,
  onInstall,
  onUninstall,
  uninstalling = false,
  onOpenDetail,
  onRepublish,
  canRepublish = false,
  isMine = false,
}: ResultCardProps) {
  const { t } = useTranslation();
  const [hover, setHover] = useState(false);
  const isMobile = useIsMobile();
  const orgInstalled = isOrgSkillInstalled(item);
  const updateAvailable = isOrgSkillUpdateAvailable(item);
  const pinned = isOrgSkillPinned(item);
  const isOrg = isBeeagentOrgSource(item.source);
  const updatedAtLabel = isOrg
    ? formatOrgUpdatedAt(item.stats?.updated_at)
    : "";
  const publisher =
    item.author?.trim() ||
    (isOrg
      ? t("market.publisherUnknown", { defaultValue: "未知" })
      : "");

  const stats = useMemo(() => {
    const s = item.stats ?? {};
    const fmt = (v: string | number | undefined) =>
      typeof v === "number" ? v.toLocaleString() : v ?? "-";
    const rows: Array<{
      key: string;
      Icon: typeof Download;
      value?: string | number;
    }> = [
      { key: "downloads", Icon: Download, value: s.downloads ?? s.installs },
      { key: "stars", Icon: Star, value: s.stars },
      { key: "likes", Icon: Heart, value: s.likes },
      { key: "views", Icon: Eye, value: s.views },
    ];
    return rows
      .filter((r) => r.key === "downloads" || r.value != null)
      .map((r) => ({
        key: r.key,
        Icon: r.Icon,
        label: t(`market.stats.${r.key}`),
        value: fmt(r.value),
      }));
  }, [item.stats, t]);

  const showFooter = useCallback(() => setHover(true), []);
  const hideFooter = useCallback(() => setHover(false), []);
  const stopPropagation = useCallback(
    (e: React.MouseEvent | React.KeyboardEvent) => e.stopPropagation(),
    [],
  );

  const primaryLabel = updateAvailable
    ? t("market.update")
    : orgInstalled
      ? t("market.uninstall")
      : isOrg
        ? t("market.install")
        : t("common.save");

  return (
    <Card
      hoverable
      className={styles.skillCard}
      onClick={onOpenDetail}
      onMouseEnter={showFooter}
      onMouseLeave={hideFooter}
      style={CURSOR_STYLE}
    >
      <div className={styles.cardTopRow}>
        <SkillIcon url={item.icon_url} alt={item.name} source={item.source} />
        <div className={styles.cardTopActions}>
          <CommunityFeedback
            origin={skillMarketResource(item)?.origin}
            resourceName={item.name}
            variant="inline"
          />
          <span className={styles.sourceBadge}>
            {sourceLabel(item.source, item.source_label)}
          </span>
        </div>
      </div>

      <div className={styles.titleRow}>
        <Tooltip title={item.name}>
          <h3 className={styles.skillTitle}>{item.name}</h3>
        </Tooltip>
        {isOrg &&
        (item.stats?.featured === 1 || item.stats?.featured === "1") ? (
          <span className={styles.featuredBadge}>精选</span>
        ) : null}
        {isMine ? (
          <span className={styles.mineBadge}>
            {t("market.mineBadge", { defaultValue: "我的" })}
          </span>
        ) : null}
        {item.version ? (
          <span className={styles.versionBadge}>v{item.version}</span>
        ) : null}
      </div>

      <p className={styles.descriptionText}>
        {item.description || t("market.noDescription")}
      </p>

      {isOrg ? (
        <div className={styles.metaRow}>
          <span className={styles.publisher}>
            {t("market.publisherLabel", {
              name: publisher,
              defaultValue: "发布者 {{name}}",
            })}
          </span>
          {item.stats?.visibility ? (
            <span>{String(item.stats.visibility)}</span>
          ) : null}
          {item.stats?.category ? (
            <span>{String(item.stats.category)}</span>
          ) : null}
          {typeof item.stats?.installs === "number" ||
          typeof item.stats?.installs === "string" ? (
            <span>
              {t("market.installCount", {
                count: Number(item.stats.installs) || 0,
                defaultValue: "安装 {{count}}",
              })}
            </span>
          ) : null}
          {item.stats?.shelf ? (
            <span className={styles.updateHint}>{String(item.stats.shelf)}</span>
          ) : null}
          {updatedAtLabel ? (
            <span>
              {t("market.updatedAtLabel", {
                time: updatedAtLabel,
                defaultValue: "更新 {{time}}",
              })}
            </span>
          ) : null}
          {item.stats?.compatibility ? (
            <span title={String(item.stats.compatibility)}>
              兼容 {String(item.stats.compatibility).slice(0, 32)}
              {String(item.stats.compatibility).length > 32 ? "…" : ""}
            </span>
          ) : null}
          {pinned ? (
            <span className={styles.updateHint}>
              {t("market.pinnedBadge", { defaultValue: "已钉住" })}
              {item.stats?.newer_version
                ? ` · 货架 ${String(item.stats.newer_version)}`
                : ""}
            </span>
          ) : updateAvailable ? (
            <span className={styles.updateHint}>{t("market.updateAvailable")}</span>
          ) : orgInstalled ? (
            <span>{t("market.installed")}</span>
          ) : null}
        </div>
      ) : (
        <div className={styles.statsRow}>
          {stats.map(({ key, Icon, label, value }) => (
            <Tooltip key={key} title={label}>
              <span className={styles.statItem}>
                <Icon size={13} />
                <span className={styles.statValue}>{value}</span>
              </span>
            </Tooltip>
          ))}
        </div>
      )}

      {(hover || isMobile) && (
        <div
          className={styles.cardFooter}
          onClick={stopPropagation}
          onKeyDown={stopPropagation}
        >
          {canRepublish && onRepublish ? (
            <Button type="default" size="small" onClick={onRepublish}>
              {t("market.republish", { defaultValue: "发布新版本" })}
            </Button>
          ) : null}
          {orgInstalled && !updateAvailable ? (
            <Button
              type="default"
              danger
              size="small"
              loading={uninstalling}
              onClick={onUninstall}
              className={styles.installButton}
              disabled={!onUninstall}
            >
              {t("market.uninstall")}
            </Button>
          ) : (
            <Button
              type="primary"
              size="small"
              onClick={onInstall}
              className={styles.installButton}
            >
              {primaryLabel}
            </Button>
          )}
        </div>
      )}
    </Card>
  );
});
