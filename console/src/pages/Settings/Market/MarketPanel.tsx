import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Input, Select, Tooltip } from "@agentscope-ai/design";
import {
  Button as AntButton,
  Segmented,
  Select as AntSelect,
  message,
} from "antd";
import { ChevronLeft, ChevronRight, RefreshCw, Upload } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMarketSearch } from "./useMarketSearch";
import type {
  InstallTarget,
  InstallQueueItem,
  MarketInstallController,
} from "./useMarketInstall";
import type { MarketResult } from "../../../api/modules/market";
import { ResultCard, DetailDrawer, QueueItem, EmptyState } from "./components";
import { PublishOrgSkillModal } from "../../../components/LoopInput/PublishOrgSkillModal";
import { InstalledSkillsPanel } from "./InstalledSkillsPanel";
import {
  canManageOrgSkill,
  canPublishOrgSkill,
  hubApi,
  ORG_SKILL_CATEGORY_OPTIONS,
  type HubOrgSkillDetail,
} from "../../../api/modules/hub";
import {
  BEEAGENT_ORG_PROVIDER_KEY,
  isBeeagentOrgSource,
  isOrgSkillOwnedBy,
  orgSkillCapUpdateVersion,
  parseOrgSkillIdFromUrl,
  searchOrgMarket,
} from "./orgMarketSource";
import styles from "./index.module.less";

type OrgShelfView = "shelf" | "installed" | "mine" | "recycle";

function getCardKey(item: MarketResult) {
  return `${item.source}:${item.slug}`;
}

/** Memoized install queue panel — only re-renders when queue changes */
export const InstallQueuePanel = memo(function InstallQueuePanel({
  queue,
  onClearCompleted,
  onCancel,
  onRetry,
}: {
  queue: InstallQueueItem[];
  onClearCompleted: () => void;
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className={styles.queueDrawer}>
      <div className={styles.queueHeader}>
        <span>{t("market.installQueue")}</span>
        <Button size="small" onClick={onClearCompleted}>
          {t("market.clearCompleted")}
        </Button>
      </div>
      <div className={styles.queueList}>
        {queue.map((q) => (
          <QueueItem
            key={q.id}
            item={q}
            onCancel={onCancel}
            onRetry={onRetry}
          />
        ))}
      </div>
    </div>
  );
});

/** Multi-select source selector. */
const ProviderSelect = memo(function ProviderSelect({
  providers,
  selectedKeys,
  onSelect,
}: {
  providers: {
    key: string;
    label: string;
    available: boolean;
    reason?: string | null;
  }[];
  selectedKeys: Set<string>;
  onSelect: (keys: string[]) => void;
}) {
  const { t } = useTranslation();
  const availableKeys = useMemo(
    () => providers.filter((provider) => provider.available).map((p) => p.key),
    [providers],
  );
  const value = [...selectedKeys].filter((key) => availableKeys.includes(key));
  const options = useMemo(
    () =>
      providers.map((provider) => {
        const unavailableReason =
          provider.reason ?? t("market.providerUnavailable");
        return {
          value: provider.key,
          label: provider.available ? (
            provider.label
          ) : (
            <Tooltip title={unavailableReason}>
              <span className={styles.providerOption}>{provider.label}</span>
            </Tooltip>
          ),
          disabled: !provider.available,
        };
      }),
    [providers, t],
  );

  return (
    <Select
      className={styles.providerSelect}
      mode="multiple"
      value={value}
      options={options}
      onChange={(nextValues: string[]) => onSelect(nextValues)}
      popupMatchSelectWidth={false}
      classNames={{ popup: { root: styles.providerDropdown } }}
    />
  );
});

/** Expanded single-select category tags. */
const CategoryChips = memo(function CategoryChips({
  categories,
  active,
  onSelect,
}: {
  categories: { id: string; label: string }[];
  active: string;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const options = [{ id: "", label: t("market.categoryAll") }, ...categories];
  const optionsKey = options
    .map((option) => `${option.id}:${option.label}`)
    .join("|");

  const updateScrollState = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    setCanScrollLeft(viewport.scrollLeft > 1);
    setCanScrollRight(
      viewport.scrollLeft + viewport.clientWidth < viewport.scrollWidth - 1,
    );
  }, []);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    updateScrollState();
    viewport.addEventListener("scroll", updateScrollState, { passive: true });
    const resizeObserver =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(updateScrollState)
        : null;
    resizeObserver?.observe(viewport);
    return () => {
      viewport.removeEventListener("scroll", updateScrollState);
      resizeObserver?.disconnect();
    };
  }, [optionsKey, updateScrollState]);

  const scrollCategories = useCallback((direction: -1 | 1) => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    viewport.scrollBy({
      left: direction * viewport.clientWidth,
      behavior: "smooth",
    });
  }, []);

  return (
    <div className={styles.categoryNav}>
      <div
        ref={viewportRef}
        className={styles.categoryViewport}
        role="group"
        aria-label={t("market.categoryPlaceholder")}
      >
        <div className={styles.categoryChips}>
          {options.map((category) => (
            <button
              type="button"
              key={category.id || "all"}
              className={`${styles.categoryChip} ${
                active === category.id ? styles.categoryChipActive : ""
              }`}
              aria-pressed={active === category.id}
              onClick={() => onSelect(category.id)}
            >
              {category.label}
            </button>
          ))}
        </div>
      </div>
      <div className={styles.categoryNavActions}>
        <Button
          type="default"
          className={styles.categoryNavButton}
          icon={<ChevronLeft size={16} />}
          disabled={!canScrollLeft}
          onClick={() => scrollCategories(-1)}
          aria-label={t("common.back")}
          title={t("common.back")}
        />
        <Button
          type="default"
          className={styles.categoryNavButton}
          icon={<ChevronRight size={16} />}
          disabled={!canScrollRight}
          onClick={() => scrollCategories(1)}
          aria-label={t("common.next", "Next")}
          title={t("common.next", "Next")}
        />
      </div>
    </div>
  );
});

function LoadMoreSentinel({ onVisible }: { onVisible: () => void }) {
  const { t } = useTranslation();
  const nodeRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = nodeRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) onVisible();
      },
      { rootMargin: "200px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [onVisible]);
  return (
    <div ref={nodeRef} className={styles.sentinel}>
      {t("common.loading")}
    </div>
  );
}

/**
 * Embeddable market browser. The host page fixes the install destination:
 * Skills page saves into the current agent's workspace, Skill Pool page
 * imports into the pool.
 */
export function MarketPanel({
  installTarget,
  install,
  preferredProviders,
}: {
  installTarget: InstallTarget;
  install: MarketInstallController;
  preferredProviders?: string[];
}) {
  const { t } = useTranslation();
  const market = useMarketSearch({ preferredProviders });
  const [detailItem, setDetailItem] = useState<MarketResult | null>(null);
  const [publishOpen, setPublishOpen] = useState(false);
  const [editSkill, setEditSkill] = useState<HubOrgSkillDetail | null>(null);
  const [uninstallingKey, setUninstallingKey] = useState<string | null>(null);
  const [canPublish, setCanPublish] = useState(false);
  const [canManage, setCanManage] = useState(false);
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [orgCategory, setOrgCategory] = useState<string>("");
  const [orgVisibility, setOrgVisibility] = useState<string>("");
  const [orgView, setOrgView] = useState<OrgShelfView>("shelf");
  const [scopedOrgResults, setScopedOrgResults] = useState<MarketResult[] | null>(
    null,
  );
  const [scopedOrgLoading, setScopedOrgLoading] = useState(false);
  const orgSourceSelected = [...market.selectedProviderKeys].some((key) =>
    isBeeagentOrgSource(key),
  );
  const showOrgPublish = orgSourceSelected && canPublish;
  const orgScopedView = orgView === "mine" || orgView === "recycle";
  const orgOnlyEmpty =
    orgSourceSelected &&
    market.selectedProviderKeys.size === 1 &&
    !market.query.trim() &&
    !market.category &&
    !orgCategory &&
    !orgVisibility &&
    !orgScopedView;
  const refreshedInstallIds = useRef(new Set<string>());

  const reloadScopedOrg = useCallback(async () => {
    if (!orgSourceSelected || !orgScopedView) {
      setScopedOrgResults(null);
      return;
    }
    setScopedOrgLoading(true);
    try {
      const res = await searchOrgMarket(market.query, {
        category: orgCategory || undefined,
        mine: orgView === "mine",
        recycleOnly: orgView === "recycle",
        includeDeleted: orgView === "recycle",
        includeDelisted: true,
      });
      let items = res.results;
      if (orgVisibility) {
        items = items.filter((item) => {
          const key = String(item.stats?.visibility_key || "");
          if (key) return key === orgVisibility;
          const label =
            orgVisibility === "personal"
              ? "仅自己"
              : orgVisibility === "public"
                ? "公开"
                : "组织内部";
          return String(item.stats?.visibility || "") === label;
        });
      }
      setScopedOrgResults(items);
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : "加载我的技能失败",
      );
      setScopedOrgResults([]);
    } finally {
      setScopedOrgLoading(false);
    }
  }, [
    market.query,
    orgCategory,
    orgScopedView,
    orgSourceSelected,
    orgView,
    orgVisibility,
  ]);

  useEffect(() => {
    void reloadScopedOrg();
  }, [reloadScopedOrg]);

  const displayResults = useMemo(() => {
    if (!orgSourceSelected) return market.results;
    if (orgScopedView) return scopedOrgResults ?? [];
    return market.results.filter((item) => {
      if (!isBeeagentOrgSource(item.source)) return true;
      if (
        orgCategory &&
        String(item.stats?.category_key || "other") !== orgCategory
      ) {
        return false;
      }
      if (orgVisibility) {
        const key = String(item.stats?.visibility_key || "");
        if (key) {
          if (key !== orgVisibility) return false;
        } else {
          const label =
            orgVisibility === "personal"
              ? "仅自己"
              : orgVisibility === "public"
                ? "公开"
                : "组织内部";
          if (String(item.stats?.visibility || "") !== label) return false;
        }
      }
      return true;
    });
  }, [
    market.results,
    orgCategory,
    orgVisibility,
    orgSourceSelected,
    orgScopedView,
    scopedOrgResults,
  ]);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([hubApi.meEntitlements(), hubApi.me()])
      .then(([ent, me]) => {
        if (cancelled) return;
        setCurrentUserId(me.user_id);
        setCanPublish(
          Boolean(ent.is_hub_admin) || canPublishOrgSkill(ent.permissions),
        );
        setCanManage(
          Boolean(ent.is_hub_admin) || canManageOrgSkill(ent.permissions),
        );
      })
      .catch(() => {
        if (cancelled) return;
        setCanPublish(false);
        setCanManage(false);
        setCurrentUserId(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const openCreatePublish = useCallback(() => {
    setEditSkill(null);
    setPublishOpen(true);
  }, []);

  const openRepublish = useCallback(
    async (item: MarketResult) => {
      const skillId = parseOrgSkillIdFromUrl(item.source_url) || item.slug;
      try {
        const detail = await hubApi.getOrgSkill(skillId);
        setEditSkill(detail);
        setDetailItem(null);
        setPublishOpen(true);
      } catch (err) {
        message.error(
          err instanceof Error
            ? err.message
            : t("market.republishFailed", { defaultValue: "无法打开更新发布" }),
        );
      }
    },
    [t],
  );

  useEffect(() => {
    if (
      detailItem &&
      !market.providers.some((p) => p.key === detailItem.source)
    ) {
      setDetailItem(null);
    }
  }, [detailItem, market.providers]);

  // Refresh org catalog after a successful personal install so the button flips.
  useEffect(() => {
    for (const item of install.queue) {
      if (
        item.status === "completed" &&
        isBeeagentOrgSource(item.result.source) &&
        !refreshedInstallIds.current.has(item.id)
      ) {
        refreshedInstallIds.current.add(item.id);
        market.refresh();
        break;
      }
    }
  }, [install.queue, market]);

  const onInstall = useCallback(
    (item: MarketResult) => {
      install.enqueue([item], installTarget);
    },
    [install, installTarget],
  );

  const onUninstall = useCallback(
    async (item: MarketResult) => {
      const key = getCardKey(item);
      setUninstallingKey(key);
      try {
        const res = await install.uninstallOrg(item);
        message.success(
          t("market.uninstallSuccess", {
            name: res.name || item.name,
            defaultValue: "已卸载「{{name}}」",
          }),
        );
        if (detailItem && getCardKey(detailItem) === key) {
          setDetailItem(null);
        }
        market.refresh();
      } catch (err) {
        message.error(
          err instanceof Error
            ? err.message
            : t("market.uninstallFailed", { defaultValue: "卸载失败" }),
        );
      } finally {
        setUninstallingKey(null);
      }
    },
    [detailItem, install, market, t],
  );

  // Stable callbacks for DetailDrawer
  const detailItemRef = useRef(detailItem);
  detailItemRef.current = detailItem;

  const handleDetailInstall = useCallback(() => {
    const current = detailItemRef.current;
    if (!current) return;
    // Install / upgrade always enqueue; uninstall is a separate footer button.
    onInstall(current);
    setDetailItem(null);
  }, [onInstall]);

  const handleDetailClose = useCallback(() => {
    setDetailItem(null);
  }, []);

  const browseHintLabel = useMemo(() => {
    if (market.query.trim() || market.category) return "";
    return market.providers
      .filter(
        (p) =>
          p.available &&
          !p.supports_browse &&
          market.selectedProviderKeys.has(p.key),
      )
      .map((p) => p.label)
      .join(", ");
  }, [
    market.query,
    market.category,
    market.providers,
    market.selectedProviderKeys,
  ]);

  return (
    <div className={styles.marketPage}>
      <div className={styles.content}>
        <div className={styles.toolbar}>
          {orgSourceSelected ? (
            <Segmented
              value={orgView}
              onChange={(v) => setOrgView(v as OrgShelfView)}
              options={[
                {
                  label: t("market.orgShelf", { defaultValue: "货架" }),
                  value: "shelf",
                },
                {
                  label: t("market.orgMine", { defaultValue: "我的" }),
                  value: "mine",
                },
                {
                  label: t("market.orgRecycle", { defaultValue: "回收站" }),
                  value: "recycle",
                },
                {
                  label: t("market.orgInstalled", { defaultValue: "已安装" }),
                  value: "installed",
                },
              ]}
              style={{ marginBottom: 12 }}
            />
          ) : null}
          {(!orgSourceSelected || orgView === "shelf") && (
            <CategoryChips
              categories={market.categories}
              active={market.category}
              onSelect={market.setCategory}
            />
          )}
          <div className={styles.filters}>
            {(!orgSourceSelected ||
              orgView === "shelf" ||
              orgView === "mine" ||
              orgView === "recycle") && (
              <Input.Search
                className={styles.searchInput}
                placeholder={t("market.searchPlaceholder")}
                allowClear
                value={market.query}
                onChange={(e) => market.setQuery(e.target.value)}
                aria-label={t("market.searchPlaceholder")}
              />
            )}
            <div className={styles.providerFilters}>
              <ProviderSelect
                providers={market.providers}
                selectedKeys={market.selectedProviderKeys}
                onSelect={market.setSelectedProviders}
              />
              {orgSourceSelected &&
              (orgView === "shelf" ||
                orgView === "mine" ||
                orgView === "recycle") ? (
                <>
                  <AntSelect
                    allowClear
                    placeholder={t("market.orgCategory", {
                      defaultValue: "业务域",
                    })}
                    style={{ minWidth: 120 }}
                    value={orgCategory || undefined}
                    options={ORG_SKILL_CATEGORY_OPTIONS}
                    onChange={(value) => setOrgCategory(value || "")}
                  />
                  {orgView !== "recycle" ? (
                    <AntSelect
                      allowClear
                      placeholder={t("market.orgVisibility", {
                        defaultValue: "可见性",
                      })}
                      style={{ minWidth: 120 }}
                      value={orgVisibility || undefined}
                      options={[
                        { value: "personal", label: "仅自己" },
                        { value: "org", label: "组织内部" },
                        { value: "public", label: "公开" },
                      ]}
                      onChange={(value) => setOrgVisibility(value || "")}
                    />
                  ) : null}
                </>
              ) : null}
              {showOrgPublish && (
                <AntButton
                  type="default"
                  icon={<Upload size={14} />}
                  onClick={openCreatePublish}
                >
                  {t("chat.skillPicker.orgMarketPublish")}
                </AntButton>
              )}
              <AntButton
                type="default"
                className={styles.refreshButton}
                icon={<RefreshCw size={14} />}
                onClick={() => {
                  if (orgScopedView) void reloadScopedOrg();
                  else market.refresh();
                }}
                disabled={orgScopedView ? scopedOrgLoading : market.loading}
                aria-label={t("common.refresh")}
                title={t("common.refresh")}
              />
            </div>
          </div>
        </div>

        {orgSourceSelected && orgView === "recycle" ? (
          <div
            style={{
              marginBottom: 12,
              color: "var(--color-text-secondary, #666)",
            }}
          >
            回收站内技能 7 天内可恢复；到期后由系统自动永久清除。
          </div>
        ) : null}

        {orgSourceSelected && orgView === "installed" ? (
          <InstalledSkillsPanel
            onUninstallOrg={async (skillId) => {
              try {
                await hubApi.uninstallOrgSkill(skillId);
                message.success(t("market.uninstall"));
                market.refresh();
              } catch (err) {
                message.error(
                  err instanceof Error ? err.message : t("market.uninstall"),
                );
              }
            }}
          />
        ) : (
          <>
            {market.query.trim() && !market.loading && !market.globalError && (
              <div className={styles.searchHint}>
                {t("market.searchResult", {
                  keyword: market.query.trim(),
                  count: market.totalCount,
                })}
              </div>
            )}

            {browseHintLabel && (
              <div className={styles.browseHint}>
                {t("market.browseHint", { providers: browseHintLabel })}
              </div>
            )}

            {market.globalError && (
              <div className={styles.errorRow}>{market.globalError}</div>
            )}
            {market.errors.map((err) => {
              const provider = market.providers.find(
                (p) => p.key === err.provider,
              );
              const label = provider?.label ?? err.provider;
              return (
                <div className={styles.errorRow} key={err.provider}>
                  <strong>{label}</strong>: {err.message}
                </div>
              );
            })}

            {market.providersLoaded && market.providers.length === 0 ? (
              <EmptyState text={t("market.noHubs")} />
            ) : (orgScopedView ? scopedOrgLoading : market.loading) &&
              displayResults.length === 0 ? (
              <EmptyState text={t("common.loading")} />
            ) : displayResults.length === 0 &&
              !orgScopedView &&
              (market.globalError || market.errors.length > 0) ? (
              <EmptyState text={t("market.noResults")}>
                <Button onClick={market.retry} loading={market.loading}>
                  {t("market.retry")}
                </Button>
              </EmptyState>
            ) : displayResults.length === 0 ? (
              <EmptyState
                text={
                  orgView === "recycle"
                    ? t("market.orgRecycleEmpty", {
                        defaultValue: "回收站为空。",
                      })
                    : orgView === "mine"
                      ? t("market.orgMineEmpty", {
                          defaultValue:
                            "你还没有发布技能。可先以「仅自己」发布，验证后再上架到组织。",
                        })
                      : orgOnlyEmpty
                        ? t("market.orgEmpty", {
                            defaultValue:
                              "组织专业能力货架暂无技能。有发布权限时可上传完整技能包，供同事安装使用。",
                          })
                        : t("market.noResults")
                }
              >
                {orgOnlyEmpty && showOrgPublish ? (
                  <AntButton type="primary" onClick={openCreatePublish}>
                    {t("chat.skillPicker.orgMarketPublish")}
                  </AntButton>
                ) : null}
              </EmptyState>
            ) : (
              <>
                <div className={styles.resultsGrid}>
                  {displayResults.map((item) => {
                    const mine =
                      isBeeagentOrgSource(item.source) &&
                      isOrgSkillOwnedBy(item, currentUserId);
                    const canRepublish =
                      isBeeagentOrgSource(item.source) &&
                      (orgSkillCapUpdateVersion(item) ||
                        (Boolean(canPublish) && mine));
                    return (
                      <ResultCard
                        key={getCardKey(item)}
                        item={item}
                        onInstall={() => onInstall(item)}
                        onUninstall={
                          isBeeagentOrgSource(item.source)
                            ? () => void onUninstall(item)
                            : undefined
                        }
                        uninstalling={uninstallingKey === getCardKey(item)}
                        onOpenDetail={() => setDetailItem(item)}
                        isMine={mine}
                        canRepublish={canRepublish}
                        onRepublish={
                          canRepublish
                            ? () => {
                                void openRepublish(item);
                              }
                            : undefined
                        }
                      />
                    );
                  })}
                </div>
                <div className={styles.loadMoreRow}>
                  {market.hasMore && market.autoLoadBlocked ? (
                    <Button onClick={market.loadMore} loading={market.loading}>
                      {t("market.loadMore")}
                    </Button>
                  ) : market.hasMore ? (
                    <LoadMoreSentinel
                      key={market.results.length}
                      onVisible={market.autoLoadMore}
                    />
                  ) : (
                    <span className={styles.noMoreText}>
                      {t("market.noMoreResults")}
                    </span>
                  )}
                </div>
              </>
            )}
          </>
        )}
      </div>

      <PublishOrgSkillModal
        open={publishOpen}
        editSkill={editSkill}
        onClose={() => {
          setPublishOpen(false);
          setEditSkill(null);
        }}
        onPublished={() => {
          setEditSkill(null);
          market.setSelectedProviders([BEEAGENT_ORG_PROVIDER_KEY]);
          market.refresh();
        }}
      />

      <DetailDrawer
        item={detailItem}
        onInstall={handleDetailInstall}
        onUninstall={
          detailItem && isBeeagentOrgSource(detailItem.source)
            ? () => void onUninstall(detailItem)
            : undefined
        }
        uninstalling={
          detailItem ? uninstallingKey === getCardKey(detailItem) : false
        }
        canRepublish={
          Boolean(detailItem) &&
          (orgSkillCapUpdateVersion(detailItem!) ||
            (Boolean(canPublish) &&
              isOrgSkillOwnedBy(detailItem!, currentUserId)))
        }
        onRepublish={
          detailItem
            ? () => {
                void openRepublish(detailItem);
              }
            : undefined
        }
        canManage={canManage}
        onOpsChanged={() => {
          if (orgScopedView) void reloadScopedOrg();
          else market.refresh();
          setDetailItem(null);
        }}
        onClose={handleDetailClose}
      />
    </div>
  );
}
