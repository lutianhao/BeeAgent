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

export function orgSkillToMarketResult(skill: HubOrgSkill): MarketResult {
  const stats: Record<string, string | number> = {
    visibility: skill.visibility === "org" ? "组织内部" : "公开",
  };
  if (skill.has_bundle) {
    stats.bundle = "完整包";
  }
  if (skill.installed) {
    // Numeric flag for UI; DetailDrawer still shows the label via stats.
    stats.installed = 1;
    stats.status = "已安装";
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

export async function searchOrgMarket(query: string): Promise<MarketSearchResponse> {
  const res = await hubApi.listOrgSkills(false);
  const needle = query.trim().toLowerCase();
  let items = res.items || [];
  if (needle) {
    items = items.filter((skill) => {
      const hay = `${skill.name} ${skill.display_name} ${skill.description}`.toLowerCase();
      return hay.includes(needle);
    });
  }
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
