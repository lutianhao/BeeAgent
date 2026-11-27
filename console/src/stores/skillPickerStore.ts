import { create } from "zustand";

import type { SkillSpec } from "../api/types";

/** BeeAgent official specialized skills eligible for the composer picker. */
export const OFFICIAL_SKILLS = [
  "koujing-xiezhuan",
  "wangping-huashu",
  "yuqing-yanpan",
  "yuan-xiezhuan",
  "shiqian-pinggu",
  "paicha-fangan",
  "weike-wenan",
  "yanlian-jiaoben",
  "shensu-chegao",
  "shuju-chuli",
  "yuqing-baogao",
] as const;

export type OfficialSkillName = (typeof OFFICIAL_SKILLS)[number];

export const OFFICIAL_SKILL_SET = new Set<string>(OFFICIAL_SKILLS);

const SKILL_NAME_RE = /^[a-z][a-z0-9-]{0,62}$/;

/** Official or org-market installed skills that belong in 专项能力. */
export function isSpecializedPickerSkill(skill: SkillSpec): boolean {
  if (OFFICIAL_SKILL_SET.has(skill.name)) return true;
  if (skill.enabled === false) return false;
  const tags = skill.tags ?? [];
  return tags.includes("specialized") || tags.includes("org_skills");
}

export function listPickerSkills(skills: SkillSpec[]): SkillSpec[] {
  const byName = new Map(skills.map((skill) => [skill.name, skill]));
  const official = OFFICIAL_SKILLS.map((name) => byName.get(name)).filter(
    (skill): skill is SkillSpec => Boolean(skill),
  );
  const extras = skills
    .filter(
      (skill) =>
        !OFFICIAL_SKILL_SET.has(skill.name) && isSpecializedPickerSkill(skill),
    )
    .sort((a, b) => a.name.localeCompare(b.name));
  return [...official, ...extras];
}

interface SkillPickerState {
  selectedSkill: string | null;
  setSelectedSkill: (skill: string | null) => void;
}

export const useSkillPickerStore = create<SkillPickerState>((set) => ({
  selectedSkill: null,
  setSelectedSkill: (skill) =>
    set({
      selectedSkill:
        skill && SKILL_NAME_RE.test(skill) ? skill.toLowerCase() : null,
    }),
}));

export function getSelectedSkill(): string | null {
  return useSkillPickerStore.getState().selectedSkill;
}

/** Drop sticky picker selection (new chat / session switch). */
export function clearSelectedSkill(): void {
  useSkillPickerStore.getState().setSelectedSkill(null);
}

/**
 * Pull a specialized skill summon prefix out of composer text.
 * Supports both ``/skill-name`` and ``@skill-name`` (豆包式召唤).
 */
export function extractOfficialSkillPrefix(
  text: string,
): { skill: string; rest: string; marker: "/" | "@" } | null {
  const match = /^([/@])([a-z][a-z0-9-]{0,62})(?:\s+|$)/i.exec(text);
  if (!match) return null;
  return {
    marker: match[1] as "/" | "@",
    skill: match[2].toLowerCase(),
    rest: text.slice(match[0].length),
  };
}

/** True when text is an in-progress ``/`` or ``@`` skill summon (no space yet). */
export function isSkillSummonPopupOpen(value: string): boolean {
  return /^[/@][a-z0-9-]*$/i.test(value);
}

/** Strip a previously injected skill-constraint block so resends stay clean. */
const SKILL_CONSTRAINT_RE =
  /^【专项约束】[\s\S]*?\n【用户原文】\n?/u;

/**
 * Ensure the outgoing message starts with `/<skill> ` when the picker has a
 * selection, and inject a hard constraint: follow the Skill flow; if the user
 * ask clearly mismatches the Skill, clarify first. Does not override unrelated
 * slash commands the user typed.
 */
export function prepareSkillMessage(text: string): string {
  let body = text;
  const extracted = extractOfficialSkillPrefix(body);

  // Typing ``/skill`` or ``@skill`` without picker selection still summons.
  let skill = getSelectedSkill();
  if (!skill && extracted) {
    skill = extracted.skill;
    useSkillPickerStore.getState().setSelectedSkill(skill);
  }
  if (!skill) return text;

  if (extracted) {
    body = extracted.rest.replace(/^\s+/, "");
  } else {
    const trimmed = body.trimStart();
    // Leave unrelated slash commands (e.g. /compact) alone.
    if (trimmed.startsWith("/") || trimmed.startsWith("@")) return text;
    body = body.replace(/^\s+/, "");
  }

  body = body.replace(SKILL_CONSTRAINT_RE, "").replace(/^\s+/, "");

  const constraint =
    `【专项约束】已启用专项 Skill「${skill}」。` +
    `必须先读取并严格按该 Skill 的 SKILL.md 流程、口径与输出格式执行，不得跳过关键步骤或改做其他专项。` +
    `若用户本轮指令/材料主题明显与本 Skill 不符，先用一两句话澄清询问（切换能力还是仍按本专项处理），确认前不要输出最终交付；主题相符则直接按流程交付。\n` +
    `【用户原文】\n`;

  return body ? `/${skill} ${constraint}${body}` : `/${skill} ${constraint}`;
}
