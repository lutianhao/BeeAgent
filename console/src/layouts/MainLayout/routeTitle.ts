import { resolveLocalized, type RouteMeta } from "../../plugins/registry/types";

interface TitledRoute {
  id: string;
  path: string;
  meta?: RouteMeta;
}

function titleFromPath(path: string): string | undefined {
  const segments = path
    .split("/")
    .filter((part) => part && !part.startsWith(":") && part !== "*");
  const segment = segments[segments.length - 1];

  if (!segment) return undefined;
  return segment
    .replace(/[-_]+/g, " ")
    .replace(/\b\w/g, (character: string) => character.toUpperCase());
}

export function getRouteTitle(route: TitledRoute | undefined, locale: string) {
  if (!route) return "小蜜蜂";
  return (
    resolveLocalized(route.meta?.title, locale) ??
    titleFromPath(route.path) ??
    "小蜜蜂"
  );
}
