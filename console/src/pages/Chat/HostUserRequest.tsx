/**
 * User request bubble that hides agent-only skill/KB constraint text and
 * shows a light chip instead. Must not call VendorRequestCard (would re-enter
 * options.request.render).
 */
import React, { useMemo } from "react";
import {
  AgentScopeRuntimeContentType,
  Bubble,
  type IAgentScopeRuntimeRequest,
} from "@agentscope-ai/chat";
import { useChatAnywhereOptions } from "@agentscope-ai/chat/lib/AgentScopeRuntimeWebUI/core/Context/ChatAnywhereOptionsContext";
import RequestActions from "@agentscope-ai/chat/lib/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Request/Actions";

import { sanitizeRequestForDisplay } from "../../stores/composerDisplay";
import { ComposerRequestBadge } from "./ComposerRequestBadge";

type ContentPart = {
  type?: string;
  text?: string;
  image_url?: string;
  file_url?: string;
  file_name?: string;
  fileName?: string;
  file_size?: number;
};

function DefaultSanitizedRequest({
  data,
}: {
  data: IAgentScopeRuntimeRequest;
}) {
  const onFileCardClick = useChatAnywhereOptions((v) => v.api?.onFileCardClick);
  const { data: clean, skillName, orgKb } = useMemo(
    () => sanitizeRequestForDisplay(data),
    [data],
  );

  const cards = useMemo(() => {
    const contents = (clean.input || []).flatMap((message) => {
      const parts = message.content;
      return Array.isArray(parts) ? (parts as ContentPart[]) : [];
    });
    return contents.reduce<
      Array<{ code: string; data: unknown; onClick?: unknown }>
    >((acc, part) => {
      if (part.type === AgentScopeRuntimeContentType.TEXT) {
        const text = String(part.text || "");
        if (!text.trim()) return acc;
        acc.push({ code: "Text", data: { content: text, raw: true } });
      }
      if (part.type === AgentScopeRuntimeContentType.IMAGE) {
        const imageCard = acc.find((item) => item.code === "Images");
        const url = part.image_url;
        if (!imageCard) acc.push({ code: "Images", data: [{ url }] });
        else (imageCard.data as Array<{ url?: string }>).push({ url });
      }
      if (part.type === AgentScopeRuntimeContentType.FILE) {
        const fileCard = acc.find((item) => item.code === "Files");
        const file = {
          url: part.file_url,
          name: part.file_name || part.fileName,
          size: part.file_size,
        };
        if (!fileCard) {
          acc.push({ code: "Files", data: [file], onClick: onFileCardClick });
        } else {
          (fileCard.data as unknown[]).push(file);
        }
      }
      return acc;
    }, []);
  }, [clean.input, onFileCardClick]);

  if (!cards.length && !skillName && !orgKb) return null;

  return (
    <>
      <ComposerRequestBadge skillName={skillName} orgKb={orgKb} />
      {cards.length ? <Bubble role="user" cards={cards} /> : null}
      <RequestActions data={clean as IAgentScopeRuntimeRequest} />
    </>
  );
}

/** options.request.render entry — strip wrappers, badge, then default bubble. */
export function renderHostUserRequest(ctx: {
  data: IAgentScopeRuntimeRequest;
  fallback: () => React.ReactNode;
}): React.ReactNode {
  const { changed } = sanitizeRequestForDisplay(ctx.data);
  if (!changed) return ctx.fallback();
  return <DefaultSanitizedRequest data={ctx.data} />;
}
