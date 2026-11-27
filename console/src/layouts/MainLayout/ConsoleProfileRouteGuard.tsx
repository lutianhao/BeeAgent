import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { message } from "antd";
import {
  isMenuIdAllowed,
  useConsoleProfile,
} from "../../hooks/useConsoleProfile";
import { useRoutes } from "../../plugins/registry/hooks";
import { pickSelectedKey } from "./routeSelection";

/** Always reachable even when not listed in member nav.show. */
const ALWAYS_ALLOWED = new Set(["core.chat", "core.settings-center"]);

const FALLBACK_PATH = "/market";

/**
 * Redirect members away from deep-linked routes that console-profile.nav
 * would hide from the sidebar. Admin/operator with unrestricted nav skip.
 */
export function ConsoleProfileRouteGuard() {
  const location = useLocation();
  const navigate = useNavigate();
  const routes = useRoutes();
  const { profile, loading } = useConsoleProfile();

  useEffect(() => {
    if (loading || !profile?.nav) return;
    const nav = profile.nav;
    if (nav.mode === "admin" || nav.show == null) return;

    const selectedKey = pickSelectedKey(location.pathname, routes);
    if (ALWAYS_ALLOWED.has(selectedKey)) return;
    if (isMenuIdAllowed(selectedKey, profile)) return;

    message.warning("当前账号无权访问该页面，已返回技能市场");
    navigate(FALLBACK_PATH, { replace: true });
  }, [loading, location.pathname, navigate, profile, routes]);

  return null;
}
