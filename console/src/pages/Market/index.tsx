import { Navigate, useSearchParams } from "react-router-dom";
import { MarketplaceHeader } from "./components/MarketplaceHeader";
import CommunityPage from "./Community";
import AppCenterPage from "../AppCenter";
import PluginManagerPage from "../Settings/PluginManager";
import { InstallQueuePanel, MarketPanel } from "../Settings/Market/MarketPanel";
import {
  useMarketInstall,
  type InstallTarget,
  type MarketInstallController,
} from "../Settings/Market/useMarketInstall";
import { useAgentStore } from "../../stores/agentStore";
import { BEEAGENT_ORG_PROVIDER_KEY } from "../Settings/Market/orgMarketSource";
import styles from "./index.module.less";

function getSkillMarketTarget(value: string | null): InstallTarget {
  return value === "pool" ? "pool" : "workspace";
}

function SkillMarketplace({
  installTarget,
  install,
  preferredProviders,
}: {
  installTarget: InstallTarget;
  install: MarketInstallController;
  preferredProviders?: string[];
}) {
  return (
    <div className={styles.page}>
      <MarketplaceHeader activeSection="skills" />
      <MarketPanel
        installTarget={installTarget}
        install={install}
        preferredProviders={preferredProviders}
      />
    </div>
  );
}

export default function MarketplacePage() {
  const [searchParams] = useSearchParams();
  const tab = searchParams.get("tab");
  const source = searchParams.get("source");
  const selectedAgent = useAgentStore((state) => state.selectedAgent);
  const install = useMarketInstall({ selectedAgent });
  // Skills tab defaults to org library when no explicit source is set.
  const preferredProviders =
    tab === "skills"
      ? [source || BEEAGENT_ORG_PROVIDER_KEY]
      : source
        ? [source]
        : undefined;

  // Hub landing: bare /market opens org skill shelf (not App Center).
  if (!tab) {
    const target = searchParams.get("target");
    const suffix =
      target === "pool" || target === "workspace" ? `&target=${target}` : "";
    return (
      <Navigate
        to={`/market?tab=skills&source=${BEEAGENT_ORG_PROVIDER_KEY}${suffix}`}
        replace
      />
    );
  }

  let content = <AppCenterPage />;
  if (tab === "community") {
    content = <CommunityPage />;
  } else if (tab === "plugins") {
    content = <PluginManagerPage />;
  } else if (tab === "apps") {
    content = <AppCenterPage />;
  } else if (tab === "skills") {
    content = (
      <SkillMarketplace
        installTarget={getSkillMarketTarget(searchParams.get("target"))}
        install={install}
        preferredProviders={preferredProviders}
      />
    );
  }

  return (
    <>
      {content}
      {install.queue.length > 0 && (
        <InstallQueuePanel
          queue={install.queue}
          onClearCompleted={install.clearFinished}
          onCancel={install.cancel}
          onRetry={install.retry}
        />
      )}
    </>
  );
}
