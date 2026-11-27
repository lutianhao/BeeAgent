import { useCallback, useEffect, useState } from "react";
import {
  hubApi,
  type HubConsoleProfile,
} from "../api/modules/hub";

let cached: HubConsoleProfile | null = null;
let inflight: Promise<HubConsoleProfile> | null = null;

async function loadProfile(force = false): Promise<HubConsoleProfile> {
  if (!force && cached) return cached;
  if (!force && inflight) return inflight;
  inflight = hubApi
    .meConsoleProfile()
    .then((profile) => {
      cached = profile;
      return profile;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

export function useConsoleProfile() {
  const [profile, setProfile] = useState<HubConsoleProfile | null>(cached);
  const [loading, setLoading] = useState(!cached);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await loadProfile(true);
      setProfile(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void loadProfile(false)
      .then((next) => {
        if (!cancelled) setProfile(next);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { profile, loading, error, refresh };
}

/** Filter builtin/plugin menu ids using console-profile.nav. */
export function filterMenuIdsByNav(
  ids: string[],
  profile: HubConsoleProfile | null | undefined,
): string[] {
  if (!profile?.nav) return ids;
  if (profile.nav.mode === "admin" || profile.nav.show == null) {
    return ids.filter((id) => !profile.nav.hide.includes(id));
  }
  const allow = new Set(profile.nav.show);
  return ids.filter((id) => allow.has(id) && !profile.nav.hide.includes(id));
}

export function isMenuIdAllowed(
  id: string,
  profile: HubConsoleProfile | null | undefined,
): boolean {
  if (!profile?.nav) return true;
  if (profile.nav.hide.includes(id)) return false;
  if (profile.nav.mode === "admin" || profile.nav.show == null) return true;
  return profile.nav.show.includes(id);
}

type MenuTreeItem = {
  id: string;
  __children?: MenuTreeItem[];
  [key: string]: unknown;
};

/** Drop menu nodes (and empty groups) not allowed by console-profile.nav. */
export function filterMenuForConsoleProfile<T extends MenuTreeItem>(
  items: T[],
  profile: HubConsoleProfile | null | undefined,
): T[] {
  if (!profile?.nav) return items;
  if (profile.nav.mode === "admin" && !profile.nav.hide.length) return items;

  return items.flatMap((item) => {
    if (!isMenuIdAllowed(item.id, profile)) return [];
    if (!item.__children?.length) return [item];
    const children = filterMenuForConsoleProfile(
      item.__children as T[],
      profile,
    );
    if (!children.length) return [];
    return [{ ...item, __children: children }];
  });
}
