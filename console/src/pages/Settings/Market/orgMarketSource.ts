/**
 * BeeAgent org skill library as a Market provider source.
 *
 * Browse/install reuse MarketPanel; data still comes from Hub `/hub/org-skills`
 * (org visibility + official-name protection). This avoids a parallel UI while
 * staying compatible with the stock MarketProvider design.
 */

import { hubApi, type HubOrgSkill } from "../../../api/modules/hub";
import type {
  MarketProviderInfo,
  MarketResult,
  MarketSearchResponse,
} from "../../../api/modules/market";
import { authApi } from "../../../api/modules/auth";

export const BEEAGENT_ORG_PROVIDER_KEY = "beeagent-org";

export const BEEAGENT_ORG_PROVIDER: MarketProviderInfo = {
  key: BEEAGENT_ORG_PROVIDER_KEY,
  label: "组织技能",
  available: true,
  reason: null,
  supports_browse: true,
};

export function isBeeagentOrgSource(source: string | null | undefined): boolean {
  return source === BEEAGENT_ORG_PROVIDER_KEY;
}

const CATEGORY_LABELS: Record<string, string> = {
  koujing: "口径",
  yuqing: "舆情",
  appeal: "申诉",
  report: "报告",
  drill: "演练",
  data: "数据处理",
  tools: "工具脚本",
  content: "文案创意",
  ops: "运维办公",
  finance: "金融材料",
  other: "其他",
};

export function orgSkillCategoryLabel(category?: string | null): string {
  if (!category) return CATEGORY_LABELS.other;
  return CATEGORY_LABELS[category] || category;
}

function visibilityLabel(visibility: string | undefined): string {
  if (visibility === "personal") return "仅自己";
  if (visibility === "public") return "公开";
  return "组织内部";
}

export function orgSkillToMarketResult(skill: HubOrgSkill): MarketResult {
  const visKey =
    skill.visibility === "personal" || skill.visibility === "public"
      ? skill.visibility
      : "org";
  const stats: Record<string, string | number> = {
    visibility: visibilityLabel(skill.visibility),
    visibility_key: visKey,
    // Internal fields for update ownership / republish (hidden in detail rows).
    skill_name: skill.name,
    owner_user_id: skill.owner_user_id,
  };
  if (skill.updated_at) {
    stats.updated_at = skill.updated_at;
  }
  if (skill.created_at) {
    stats.created_at = skill.created_at;
  }
  if (skill.has_bundle) {
    stats.bundle = "完整包";
  }
  if (skill.changelog?.trim()) {
    stats.changelog = skill.changelog.trim();
  }
  if (skill.compatibility?.trim()) {
    stats.compatibility = skill.compatibility.trim();
  }
  if (skill.allowed_tools?.length) {
    stats.allowed_tools = skill.allowed_tools.join(", ");
  }
  if (skill.category) {
    stats.category = orgSkillCategoryLabel(skill.category);
    stats.category_key = skill.category;
  }
  if (skill.featured) {
    stats.featured = 1;
  }
  if (skill.status === "delisted") {
    stats.shelf = "已下架";
  }
  if (skill.status === "deleted" || skill.deleted_at) {
    stats.shelf = "回收站";
    stats.deleted_at = skill.deleted_at || "";
  }
  if (typeof skill.install_count === "number") {
    stats.installs = skill.install_count;
  }
  if (skill.installed) {
    // Numeric flag for UI; DetailDrawer still shows the label via stats.
    stats.installed = 1;
    if (skill.pinned) {
      stats.pinned = 1;
      stats.status = skill.newer_version
        ? `已钉住（货架 ${skill.newer_version}）`
        : "已钉住";
    } else {
      stats.status = skill.update_available ? "可更新" : "已安装";
    }
    if (skill.installed_version) {
      stats.installed_version = skill.installed_version;
    }
    if (skill.newer_version) {
      stats.newer_version = skill.newer_version;
    }
  }
  if (skill.update_available) {
    stats.update_available = 1;
  }
  const caps = skill.capabilities;
  if (caps) {
    const flag = (on: boolean | undefined) => (on ? 1 : 0);
    stats.cap_is_owner = flag(caps.is_owner);
    stats.cap_update_version = flag(caps.can_update_version);
    stats.cap_delist = flag(caps.can_delist);
    stats.cap_relist = flag(caps.can_relist);
    stats.cap_feature = flag(caps.can_feature);
    stats.cap_retag = flag(caps.can_retag);
    stats.cap_delete_listing = flag(caps.can_delete_listing);
    stats.cap_install = flag(caps.can_install);
    stats.cap_upgrade = flag(caps.can_upgrade);
    stats.cap_uninstall = flag(caps.can_uninstall);
    stats.cap_pin = flag(caps.can_pin);
    stats.cap_share = flag(caps.can_share);
    stats.cap_list_to_org = flag(caps.can_list_to_org);
    stats.cap_make_personal = flag(caps.can_make_personal);
    stats.cap_restore = flag(caps.can_restore);
  }
  return {
    source: BEEAGENT_ORG_PROVIDER_KEY,
    source_label: BEEAGENT_ORG_PROVIDER.label,
    slug: skill.skill_id,
    name: skill.display_name || skill.name,
    description: skill.description || null,
    source_url: `beeagent-org://skill/${encodeURIComponent(skill.skill_id)}`,
    version: skill.version_text || null,
    author: skill.owner_username || null,
    icon_url: null,
    stats,
  };
}

function capOn(
  item: { source: string; stats?: Record<string, string | number> | null },
  key: string,
): boolean {
  if (!isBeeagentOrgSource(item.source)) return false;
  const v = item.stats?.[key];
  return v === 1 || v === "1";
}

export function orgSkillCapUpdateVersion(
  item: { source: string; stats?: Record<string, string | number> | null },
): boolean {
  return capOn(item, "cap_update_version");
}

export function orgSkillCapDelist(
  item: { source: string; stats?: Record<string, string | number> | null },
): boolean {
  return capOn(item, "cap_delist");
}

export function orgSkillCapRelist(
  item: { source: string; stats?: Record<string, string | number> | null },
): boolean {
  return capOn(item, "cap_relist");
}

export function orgSkillCapFeature(
  item: { source: string; stats?: Record<string, string | number> | null },
): boolean {
  return capOn(item, "cap_feature");
}

export function orgSkillCapDeleteListing(
  item: { source: string; stats?: Record<string, string | number> | null },
): boolean {
  return capOn(item, "cap_delete_listing");
}

export function orgSkillCapShare(
  item: { source: string; stats?: Record<string, string | number> | null },
): boolean {
  return capOn(item, "cap_share");
}

export function orgSkillCapListToOrg(
  item: { source: string; stats?: Record<string, string | number> | null },
): boolean {
  return capOn(item, "cap_list_to_org");
}

export function orgSkillCapRestore(
  item: { source: string; stats?: Record<string, string | number> | null },
): boolean {
  return capOn(item, "cap_restore");
}

export function getOrgSkillTechnicalName(
  item: { stats?: Record<string, string | number> | null },
): string {
  return String(item.stats?.skill_name || "");
}

export function getOrgSkillOwnerUserId(
  item: { stats?: Record<string, string | number> | null },
): string {
  return String(item.stats?.owner_user_id || "");
}

export function isOrgSkillOwnedBy(
  item: { source: string; stats?: Record<string, string | number> | null },
  userId: string | null | undefined,
): boolean {
  if (!userId || !isBeeagentOrgSource(item.source)) return false;
  if (capOn(item, "cap_is_owner")) return true;
  return getOrgSkillOwnerUserId(item) === userId;
}

export function formatOrgUpdatedAt(value: string | number | null | undefined): string {
  if (value == null || value === "") return "";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

export function isOrgSkillUpdateAvailable(
  item: { source: string; stats?: Record<string, string | number> | null },
): boolean {
  if (!isBeeagentOrgSource(item.source)) return false;
  return item.stats?.update_available === 1 || item.stats?.update_available === "1";
}

export function isOrgSkillPinned(
  item: { source: string; stats?: Record<string, string | number> | null },
): boolean {
  if (!isBeeagentOrgSource(item.source)) return false;
  return item.stats?.pinned === 1 || item.stats?.pinned === "1";
}

let hubModeCache: boolean | null = null;
let hubModePromise: Promise<boolean> | null = null;

/** Detect Hub console once per session (org source only applies there). */
export function detectHubMode(): Promise<boolean> {
  if (hubModeCache !== null) return Promise.resolve(hubModeCache);
  if (hubModePromise) return hubModePromise;
  hubModePromise = authApi
    .getStatus()
    .then((status) => {
      hubModeCache = status.mode === "hub";
      return hubModeCache;
    })
    .catch(() => {
      hubModeCache = false;
      return false;
    })
    .finally(() => {
      hubModePromise = null;
    });
  return hubModePromise;
}

export function mergeOrgProvider(
  providers: MarketProviderInfo[],
): MarketProviderInfo[] {
  if (providers.some((p) => p.key === BEEAGENT_ORG_PROVIDER_KEY)) {
    return providers;
  }
  // Put org source first so Hub users see it without scrolling.
  return [BEEAGENT_ORG_PROVIDER, ...providers];
}

/** Lowercase + strip separators so "baziyunshi" matches "bazi-yunshi". */
export function normalizeOrgSkillSearchText(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\s_\-./\\]+/g, "");
}

export async function searchOrgMarket(
  query: string,
  opts?: {
    category?: string;
    includeDelisted?: boolean;
    includeDeleted?: boolean;
    mine?: boolean;
    /** When true, only soft-deleted rows (回收站). */
    recycleOnly?: boolean;
  },
): Promise<MarketSearchResponse> {
  // Request delisted; Hub only returns them when caller has org_skill:manage.
  const recycleOnly = Boolean(opts?.recycleOnly);
  const res = await hubApi.listOrgSkills(Boolean(opts?.mine) || recycleOnly, {
    category: opts?.category,
    includeDelisted: opts?.includeDelisted ?? true,
    includeDeleted: opts?.includeDeleted ?? recycleOnly,
  });
  const needle = query.trim().toLowerCase();
  const needleCompact = normalizeOrgSkillSearchText(query);
  let items = res.items || [];
  if (recycleOnly) {
    items = items.filter(
      (skill) => skill.status === "deleted" || Boolean(skill.deleted_at),
    );
  } else if (opts?.mine) {
    // 「我的」含个人/组织/下架，不含回收站。
    items = items.filter(
      (skill) => skill.status !== "deleted" && !skill.deleted_at,
    );
  }
  if (needle) {
    items = items.filter((skill) => {
      const hay =
        `${skill.name} ${skill.display_name} ${skill.description} ${skill.category || ""}`.toLowerCase();
      if (hay.includes(needle)) return true;
      // Hyphen / underscore insensitive: baziyunshi ↔ bazi-yunshi
      return normalizeOrgSkillSearchText(hay).includes(needleCompact);
    });
  }
  // Featured already sorted server-side; keep featured first after filter.
  items = [...items].sort((a, b) => Number(b.featured) - Number(a.featured));
  const results = items.map(orgSkillToMarketResult);
  return {
    results,
    errors: [],
    by_provider: {
      [BEEAGENT_ORG_PROVIDER_KEY]: {
        has_more: false,
        total: results.length,
      },
    },
  };
}

export function parseOrgSkillIdFromUrl(url: string): string | null {
  const prefix = "beeagent-org://skill/";
  if (!url.startsWith(prefix)) return null;
  try {
    return decodeURIComponent(url.slice(prefix.length));
  } catch {
    return null;
  }
}

export function isOrgSkillInstalled(
  item: { source: string; stats?: Record<string, string | number> | null },
): boolean {
  if (!isBeeagentOrgSource(item.source)) return false;
  const value = item.stats?.installed;
  return value === 1 || value === "1" || value === "已安装";
}
