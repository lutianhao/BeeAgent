import { describe, expect, it } from "vitest";

import {
  sanitizeRequestForDisplay,
  unwrapAgentComposerText,
} from "./composerDisplay";

describe("unwrapAgentComposerText", () => {
  it("strips skill constraint and keeps user body", () => {
    const raw =
      "/jinri-yunshi 【专项约束】已启用专项 Skill「jinri-yunshi」。必须先读取。\n" +
      "【用户原文】\n帮我看看今天运势";
    const parts = unwrapAgentComposerText(raw);
    expect(parts.skillName).toBe("jinri-yunshi");
    expect(parts.orgKb).toBe(false);
    expect(parts.displayText).toBe("帮我看看今天运势");
    expect(parts.changed).toBe(true);
  });

  it("detects nested org-KB inside skill wrap", () => {
    const raw =
      "/koujing-xiezhuan 【专项约束】已启用。\n" +
      "【企业知识】本轮优先查组织知识库。\n" +
      "【用户原文】\n写个口径";
    const parts = unwrapAgentComposerText(raw);
    expect(parts.skillName).toBe("koujing-xiezhuan");
    expect(parts.orgKb).toBe(true);
    expect(parts.displayText).toBe("写个口径");
  });

  it("strips standalone org-KB wrap", () => {
    const raw =
      "/kb 【企业知识】必须先调用工具 kb_search。\n【用户原文】\n查下客户名单";
    const parts = unwrapAgentComposerText(raw);
    expect(parts.skillName).toBeNull();
    expect(parts.orgKb).toBe(true);
    expect(parts.displayText).toBe("查下客户名单");
  });

  it("leaves plain user text alone", () => {
    const parts = unwrapAgentComposerText("普通提问");
    expect(parts).toEqual({
      displayText: "普通提问",
      skillName: null,
      orgKb: false,
      changed: false,
    });
  });
});

describe("sanitizeRequestForDisplay", () => {
  it("rewrites text parts and reports skill meta", () => {
    const data = {
      input: [
        {
          role: "user",
          content: [
            {
              type: "text",
              text:
                "/demo-skill 【专项约束】x\n【用户原文】\n你好",
            },
          ],
        },
      ],
    };
    const result = sanitizeRequestForDisplay(data);
    expect(result.changed).toBe(true);
    expect(result.skillName).toBe("demo-skill");
    expect(result.data.input![0].content).toEqual([
      { type: "text", text: "你好" },
    ]);
  });
});
