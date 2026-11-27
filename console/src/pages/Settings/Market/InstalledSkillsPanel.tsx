import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Empty, Spin, Switch, Tag, message } from "antd";
import { Power, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { skillApi } from "../../../api/modules/skill";
import { hubApi, type HubOrgSkill } from "../../../api/modules/hub";
import { useAgentStore } from "../../../stores/agentStore";
import {
  OFFICIAL_SKILL_SET,
  isSpecializedPickerSkill,
} from "../../../stores/skillPickerStore";
import type { SkillSpec } from "../../../api/types";
import { orgSkillCategoryLabel } from "./orgMarketSource";
import styles from "./InstalledSkillsPanel.module.less";

interface InstalledRow {
  name: string;
  displayName: string;
  description: string;
  category?: string;
  version?: string;
  enabled: boolean;
  source: "org" | "official" | "other";
  orgSkillId?: string;
}

/**
 * Installed specialized skills with enable/disable toggles (B7).
 * Complements Market browse — advisors can mute a skill without uninstalling.
 */
export function InstalledSkillsPanel({
  onUninstallOrg,
}: {
  onUninstallOrg?: (skillId: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const selectedAgent = useAgentStore((s) => s.selectedAgent);
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<InstalledRow[]>([]);
  const [busyName, setBusyName] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [skills, orgRes] = await Promise.all([
        skillApi.listSkills(selectedAgent),
        hubApi.listOrgSkills(false).catch(() => ({ items: [] as HubOrgSkill[] })),
      ]);
      const list = Array.isArray(skills) ? skills : [];
      const orgByName = new Map(
        (orgRes.items || []).map((s) => [s.name, s] as const),
      );
      const next: InstalledRow[] = [];
      for (const skill of list as SkillSpec[]) {
        if (!skill?.name) continue;
        const isOfficial = OFFICIAL_SKILL_SET.has(skill.name);
        const org = orgByName.get(skill.name);
        const specialized =
          isOfficial ||
          isSpecializedPickerSkill(skill) ||
          Boolean(org?.installed);
        if (!specialized) continue;
        // Show if enabled OR was installed from org (even if disabled).
        if (!skill.enabled && !org?.installed && !isOfficial) continue;
        next.push({
          name: skill.name,
          displayName: org?.display_name || skill.name,
          description: org?.description || skill.description || "",
          category: org?.category,
          version: org?.version_text || skill.version_text,
          enabled: Boolean(skill.enabled),
          source: isOfficial ? "official" : org ? "org" : "other",
          orgSkillId: org?.installed ? org.skill_id : undefined,
        });
      }
      // Org installed but not yet reflected in skill list (race after install).
      for (const org of orgRes.items || []) {
        if (!org.installed) continue;
        if (next.some((r) => r.name === org.name)) continue;
        next.push({
          name: org.name,
          displayName: org.display_name || org.name,
          description: org.description || "",
          category: org.category,
          version: org.version_text,
          enabled: false,
          source: "org",
          orgSkillId: org.skill_id,
        });
      }
      next.sort((a, b) => {
        if (a.enabled !== b.enabled) return a.enabled ? -1 : 1;
        return a.displayName.localeCompare(b.displayName, "zh");
      });
      setRows(next);
    } catch (err) {
      message.error(
        err instanceof Error
          ? err.message
          : t("market.installedLoadFailed", {
              defaultValue: "加载已安装技能失败",
            }),
      );
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [selectedAgent, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const enabledCount = useMemo(
    () => rows.filter((r) => r.enabled).length,
    [rows],
  );

  const toggle = async (row: InstalledRow, nextEnabled: boolean) => {
    setBusyName(row.name);
    try {
      if (nextEnabled) {
        await skillApi.enableSkill(row.name, selectedAgent);
        message.success(
          t("skills.enabledSuccessfully", { defaultValue: "已启用" }),
        );
      } else {
        await skillApi.disableSkill(row.name, selectedAgent);
        message.success(
          t("skills.disabledSuccessfully", { defaultValue: "已停用" }),
        );
      }
      setRows((prev) =>
        prev.map((r) =>
          r.name === row.name ? { ...r, enabled: nextEnabled } : r,
        ),
      );
    } catch (err) {
      message.error(
        err instanceof Error
          ? err.message
          : t("market.toggleFailed", { defaultValue: "启停失败" }),
      );
    } finally {
      setBusyName(null);
    }
  };

  if (loading) {
    return (
      <div className={styles.panel}>
        <Spin />
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className={styles.panel}>
        <Empty
          description={t("market.installedEmpty", {
            defaultValue:
              "暂无已安装的专项技能。在「货架」安装组织技能后，可在此启停。",
          })}
        />
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div>
          <div className={styles.title}>
            <Power size={16} />
            {t("market.installedTitle", { defaultValue: "已安装专项" })}
          </div>
          <div className={styles.subtitle}>
            {t("market.installedHint", {
              enabled: enabledCount,
              total: rows.length,
              defaultValue: "已启用 {{enabled}} / {{total}} · 停用后不会自动命中，可用 / 或 @ 强制召唤",
            })}
          </div>
        </div>
        <Button
          icon={<RefreshCw size={14} />}
          onClick={() => void load()}
          type="text"
        >
          {t("common.refresh")}
        </Button>
      </div>
      <ul className={styles.list}>
        {rows.map((row) => (
          <li key={row.name} className={styles.item}>
            <div className={styles.itemMain}>
              <div className={styles.itemName}>
                {row.displayName}
                {row.displayName !== row.name ? (
                  <span className={styles.nameSlug}>{row.name}</span>
                ) : null}
                {row.version ? (
                  <span className={styles.version}>v{row.version}</span>
                ) : null}
              </div>
              <div className={styles.itemMeta}>
                <Tag>
                  {row.source === "official"
                    ? "官方"
                    : row.source === "org"
                      ? "组织"
                      : "其他"}
                </Tag>
                {row.category ? (
                  <Tag>{orgSkillCategoryLabel(row.category)}</Tag>
                ) : null}
                <code className={styles.slug}>
                  /{row.name} · @{row.name}
                </code>
              </div>
              {row.description ? (
                <div className={styles.itemDesc}>{row.description}</div>
              ) : null}
            </div>
            <div className={styles.itemActions}>
              <Switch
                checked={row.enabled}
                loading={busyName === row.name}
                onChange={(checked) => void toggle(row, checked)}
                checkedChildren="开"
                unCheckedChildren="停"
              />
              {row.orgSkillId && onUninstallOrg ? (
                <Button
                  type="link"
                  danger
                  size="small"
                  disabled={busyName === row.name}
                  onClick={() => void onUninstallOrg(row.orgSkillId!)}
                >
                  {t("market.uninstall")}
                </Button>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
