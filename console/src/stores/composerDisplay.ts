/**
 * Strip agent-only composer wrappers (skill / org-KB constraints) for UI.
 * The raw text still goes to the model; bubbles show the user-facing body.
 */

const SKILL_WRAP_RE =
  /^\/([a-z][a-z0-9-]{0,62})\s+【专项约束】[\s\S]*?【用户原文】\n?/u;

const ORG_KB_WRAP_RE =
  /^\/(?:kb|org-kb|企业知识)\s*【企业知识】[\s\S]*?【用户原文】\n?/iu;

const ORG_KB_MARKER_RE = /【企业知识】/;

export interface ComposerDisplayParts {
  /** Text shown in the user bubble / copy clipboard. */
  displayText: string;
  /** Summoned skill slug, if a skill wrapper was present. */
  skillName: string | null;
  /** True when org-KB constraint was injected. */
  orgKb: boolean;
  /** True when anything agent-only was stripped. */
  changed: boolean;
}

/** Peel BeeAgent skill / KB instruction wrappers off stored user text. */
export function unwrapAgentComposerText(text: string): ComposerDisplayParts {
  if (!text) {
    return {
      displayText: "",
      skillName: null,
      orgKb: false,
      changed: false,
    };
  }

  let body = text;
  let skillName: string | null = null;
  let orgKb = false;
  let changed = false;

  const skillMatch = SKILL_WRAP_RE.exec(body);
  if (skillMatch) {
    skillName = skillMatch[1].toLowerCase();
    if (ORG_KB_MARKER_RE.test(skillMatch[0])) orgKb = true;
    body = body.slice(skillMatch[0].length);
    changed = true;
  }

  const kbMatch = ORG_KB_WRAP_RE.exec(body);
  if (kbMatch) {
    orgKb = true;
    body = body.slice(kbMatch[0].length);
    changed = true;
  } else if (!skillMatch && ORG_KB_MARKER_RE.test(body) && body.includes("【用户原文】")) {
    // Defensive: orphan org-KB block without /kb prefix.
    const cut = body.search(/【用户原文】\n?/u);
    if (cut >= 0) {
      orgKb = true;
      body = body.slice(cut).replace(/^【用户原文】\n?/u, "");
      changed = true;
    }
  }

  return {
    displayText: body,
    skillName,
    orgKb,
    changed,
  };
}

export type SanitizedRequestResult<T> = {
  data: T;
  skillName: string | null;
  orgKb: boolean;
  changed: boolean;
};

/** Clone request card data with user-visible text only. */
export function sanitizeRequestForDisplay<T extends { input?: unknown[] }>(
  data: T,
): SanitizedRequestResult<T> {
  const input = data?.input;
  if (!Array.isArray(input) || input.length === 0) {
    return { data, skillName: null, orgKb: false, changed: false };
  }

  let skillName: string | null = null;
  let orgKb = false;
  let changed = false;

  const nextInput = input.map((rawMessage) => {
    const message = rawMessage as {
      content?: unknown;
      [key: string]: unknown;
    };
    const content = message?.content;
    if (typeof content === "string") {
      const parts = unwrapAgentComposerText(content);
      skillName = skillName || parts.skillName;
      orgKb = orgKb || parts.orgKb;
      changed = changed || parts.changed;
      if (!parts.changed) return rawMessage;
      return { ...message, content: parts.displayText };
    }
    if (!Array.isArray(content)) return rawMessage;
    let messageChanged = false;
    const nextContent = content.map((rawPart) => {
      const part = rawPart as { type?: string; text?: string };
      if (part?.type !== "text" || typeof part.text !== "string") {
        return rawPart;
      }
      const parts = unwrapAgentComposerText(part.text);
      skillName = skillName || parts.skillName;
      orgKb = orgKb || parts.orgKb;
      if (!parts.changed) return rawPart;
      messageChanged = true;
      changed = true;
      return { ...part, text: parts.displayText };
    });
    return messageChanged ? { ...message, content: nextContent } : rawMessage;
  });

  if (!changed) {
    return { data, skillName: null, orgKb: false, changed: false };
  }
  return {
    data: { ...data, input: nextInput as T["input"] },
    skillName,
    orgKb,
    changed: true,
  };
}
