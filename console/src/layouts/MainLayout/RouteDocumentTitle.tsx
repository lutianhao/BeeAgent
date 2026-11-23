import { useLayoutEffect } from "react";

export function RouteDocumentTitle({ title }: { title: string }) {
  useLayoutEffect(() => {
    const nextTitle = title === "小蜜蜂" ? title : `${title} · 小蜜蜂`;
    document.title = nextTitle;
    document.dispatchEvent(
      new CustomEvent("qwenpaw:document-title-change", {
        detail: nextTitle,
      }),
    );
  }, [title]);

  return null;
}
