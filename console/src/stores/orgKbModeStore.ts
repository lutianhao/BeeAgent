import { create } from "zustand";

interface OrgKbModeState {
  enabled: boolean;
  setEnabled: (enabled: boolean) => void;
  toggle: () => void;
}

export const useOrgKbModeStore = create<OrgKbModeState>((set, get) => ({
  enabled: false,
  setEnabled: (enabled) => set({ enabled: Boolean(enabled) }),
  toggle: () => set({ enabled: !get().enabled }),
}));

export function isOrgKbModeEnabled(): boolean {
  return useOrgKbModeStore.getState().enabled;
}

/** Slash / natural prefixes that mean「查企业知识」. */
const ORG_KB_PREFIX_RE =
  /^\/(?:kb|org-kb|企业知识)(?:\s+|$)/iu;

const ORG_KB_CONSTRAINT_RE =
  /^【企业知识】[\s\S]*?\n【用户原文】\n?/u;

/** Host slash commands that must not be rewritten. */
const HOST_SLASH_RE =
  /^\/(?:new|clear|compact|skills)(?:\s|$)/i;

/** Output of ``prepareSkillMessage``: ``/skill 【专项约束】…【用户原文】\n…``. */
const SKILL_WRAPPED_RE =
  /^\/([a-z][a-z0-9-]{0,62})\s+(【专项约束】[\s\S]*?)(【用户原文】\n?)([\s\S]*)$/u;

export function extractOrgKbPrefix(text: string): {
  rest: string;
} | null {
  const match = ORG_KB_PREFIX_RE.exec(text);
  if (!match) return null;
  return { rest: text.slice(match[0].length) };
}

const ORG_KB_CONSTRAINT =
  "【企业知识】本轮优先查组织知识库。" +
  "必须先调用工具 kb_search（可按问题选 kb_slug / skill / customer_key / as_of），" +
  "再基于命中片段作答，并引用文档标题与库名；无命中时明确告知，可再问用户或 web_search。" +
  "禁止编造组织内部口径、案例或客户清单。\n";

/**
 * When org-KB mode is on (or user typed ``/kb``), inject a hard instruction
 * to call ``kb_search`` before answering from org knowledge.
 */
export function prepareOrgKbMessage(text: string): string {
  let body = text;
  const extracted = extractOrgKbPrefix(body);
  let enabled = isOrgKbModeEnabled();

  if (extracted) {
    enabled = true;
    useOrgKbModeStore.getState().setEnabled(true);
    body = extracted.rest.replace(/^\s+/, "");
  }

  if (!enabled) return text;

  const trimmed = body.trimStart();
  if (!extracted && HOST_SLASH_RE.test(trimmed)) {
    return text;
  }

  // Drop a previously injected org-kb block so resends stay clean.
  body = body.replace(ORG_KB_CONSTRAINT_RE, "");
  // Also strip a mid-message org-kb block if we re-wrap a skill message.
  body = body.replace(
    /\n?【企业知识】[\s\S]*?(?=【用户原文】)/u,
    "",
  );

  const skillMatch = SKILL_WRAPPED_RE.exec(body);
  if (skillMatch) {
    const [, skill, skillConstraint, userMarker, rest] = skillMatch;
    return `/${skill} ${skillConstraint}${ORG_KB_CONSTRAINT}${userMarker}${rest}`;
  }

  body = body.replace(/^\s+/, "");
  return body
    ? `/kb ${ORG_KB_CONSTRAINT}【用户原文】\n${body}`
    : `/kb ${ORG_KB_CONSTRAINT}【用户原文】\n`;
}
