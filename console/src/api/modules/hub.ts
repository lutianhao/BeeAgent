import { clearAuthToken, getApiToken, getApiUrl } from "../config";
import { buildAuthHeaders } from "../authHeaders";
import { responseErrorMessage } from "../error";
import { addRouterBasename } from "../../utils/navigationMode";
import {
  DownloadCancelledError,
  downloadFileFromUrl,
} from "../../utils/downloadFileFromUrl";

export interface HubUser {
  user_id: string;
  username: string;
  role: "admin" | "user";
  disabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface HubRuntime {
  runtime_id: string;
  tenant_id: string;
  owner_user_id: string;
  owner_username: string | null;
  owner_role: HubUser["role"] | null;
  provisioner: string;
  host: string;
  port: number;
  state: "created" | "starting" | "running" | "stopped" | "failed";
  desired_state: "created" | "running" | "stopped";
  start_policy: "owner_allowed" | "admin_only";
  endpoint: string;
  security_level: string;
  metadata?: {
    docker?: {
      image: string;
      pull_policy: "always" | "if_not_present" | "never";
      image_id?: string;
      image_digests?: string[];
      container_id?: string;
      boundary_mode?: "token" | "loopback_only";
    };
    [key: string]: unknown;
  };
  last_error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface HubCredential {
  scope: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface HubPage<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface HubListParams {
  page?: number;
  pageSize?: number;
  query?: string;
}

export interface HubRuntimeListParams extends HubListParams {
  state?: HubRuntime["state"];
  provisioner?: string;
  owner?: string;
}

export interface HubUserListParams extends HubListParams {
  role?: HubUser["role"];
  disabled?: boolean;
}

export interface HubCredentialListParams extends HubListParams {
  scope?: string;
}

export interface HubAuditEvent {
  event_id: string;
  actor_user_id: string;
  actor_username: string;
  action: string;
  resource_type: string;
  resource_id: string;
  outcome: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface HubOverview {
  runtime_counts: Record<HubRuntime["state"], number>;
  total_runtimes: number;
  total_users: number;
  runtime_available: boolean;
  host: {
    cpu_percent: number;
    memory_percent: number;
    disk_percent: number;
    memory_used: number;
    memory_total: number;
    memory_available: number;
    disk_used: number;
    disk_total: number;
    disk_free: number;
    disk_path: string;
  };
  recent_events: HubAuditEvent[];
}

export interface HubProvisionerStatus {
  available: boolean;
  reason?: string | null;
  security_level: string;
}

export interface HubHealth {
  status: "ok" | "degraded";
  mode: "hub";
  default_provisioner: string;
  runtime_available: boolean;
  runtime_state: HubRuntime["state"] | null;
  runtime_desired_state: HubRuntime["desired_state"] | null;
  runtime_start_policy: HubRuntime["start_policy"] | null;
  runtime_last_error: string | null;
  provisioner_statuses: Record<string, HubProvisionerStatus>;
}

export interface HubRuntimeCapacity {
  max_running_runtimes: number | null;
}

export interface HubRateLimitConfig {
  enabled: boolean;
  max_attempts: number;
  window_seconds: number;
  block_seconds: number;
}

export interface HubConfig {
  version: 1;
  control_plane: {
    public_base_url: string | null;
    registration: {
      mode: "open" | "invite" | "closed";
      default_role: "user";
    };
    security: {
      ip_blacklist: string[];
      trusted_proxy_ips: string[];
      login_rate_limit: HubRateLimitConfig;
      registration_rate_limit: HubRateLimitConfig;
    };
    proxy: {
      max_request_size_mb: number;
      request_idle_timeout_seconds: number;
      response_header_timeout_seconds: number;
      connect_timeout_seconds: number;
      websocket_max_message_size_mb: number;
    };
  };
  runtime: {
    provisioner: "local" | "docker";
    docker: HubDockerConfig;
  };
  capacity: HubRuntimeCapacity;
}

export interface HubDockerConfig {
  source: "docker_hub" | "aliyun_acr" | "custom";
  image: string;
  pull_policy: "always" | "if_not_present" | "never";
  cpu_limit: number | null;
  memory_limit_mb: number | null;
  pids_limit: number | null;
  shm_size_mb: number;
}

export interface HubDockerImage {
  reference: string;
  image_id: string;
  short_id: string;
  digests: string[];
  size: number;
  created?: string | null;
  downloaded: boolean;
}

export interface HubOfficialDockerImage {
  source: "docker_hub" | "aliyun_acr";
  reference: string;
  tag: string;
  downloaded: boolean;
}

export interface HubDockerImageCatalog {
  available: boolean;
  reason?: string | null;
  sources: Record<"docker_hub" | "aliyun_acr", string>;
  official_images: HubOfficialDockerImage[];
  local_images: HubDockerImage[];
  policy: HubDockerConfig;
}

export interface HubDockerImagePull {
  pull_id: string;
  reference: string;
  status: "queued" | "pulling" | "completed" | "failed";
  progress: number;
  message: string;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface HubSettings {
  config: HubConfig;
  revision: number;
  updated_at: string;
  available_provisioners: string[];
}

async function handleHubResponse<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    clearAuthToken();
    window.location.assign(
      addRouterBasename(window.location.pathname, "/login"),
    );
    throw new Error("Authentication expired");
  }
  if (!response.ok) {
    throw new Error(
      await responseErrorMessage(
        response,
        `Request failed with ${response.status}`,
      ),
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getApiToken();
  const response = await fetch(getApiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  });
  return handleHubResponse<T>(response);
}

/** Multipart upload — do not set Content-Type (browser needs the boundary). */
async function requestForm<T>(path: string, form: FormData): Promise<T> {
  const token = getApiToken();
  const response = await fetch(getApiUrl(path), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: form,
  });
  return handleHubResponse<T>(response);
}

function listPath<T extends HubListParams>(path: string, params: T): string {
  const query = new URLSearchParams();
  if (params.page) query.set("page", String(params.page));
  if (params.pageSize) query.set("page_size", String(params.pageSize));
  if (params.query?.trim()) query.set("q", params.query.trim());
  Object.entries(params).forEach(([key, value]) => {
    if (["page", "pageSize", "query"].includes(key)) return;
    if (value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  });
  const suffix = query.toString();
  return suffix ? `${path}?${suffix}` : path;
}

export const hubApi = {
  getHealth: () => request<HubHealth>("/hub/healthz"),
  me: () => request<HubUser>("/hub/me"),
  changePassword: (newPassword: string) =>
    request<HubUser>("/hub/me/password", {
      method: "POST",
      body: JSON.stringify({ new_password: newPassword }),
    }),
  restartOwnRuntime: () =>
    request<HubRuntime>("/hub/me/runtime/restart", {
      method: "POST",
    }),
  listRuntimes: (params: HubRuntimeListParams = {}) =>
    request<HubPage<HubRuntime>>(listPath("/hub/runtimes", params)),
  createRuntime: (runtimeId: string, autoStart = false) =>
    request<HubRuntime>("/hub/runtimes", {
      method: "POST",
      body: JSON.stringify({ runtime_id: runtimeId, auto_start: autoStart }),
    }),
  startRuntime: (runtimeId: string) =>
    request<HubRuntime>(`/hub/runtimes/${runtimeId}/start`, {
      method: "POST",
    }),
  stopRuntime: (runtimeId: string) =>
    request<HubRuntime>(`/hub/runtimes/${runtimeId}/stop`, {
      method: "POST",
    }),
  rebuildRuntime: (runtimeId: string) =>
    request<HubRuntime>(`/hub/runtimes/${runtimeId}/rebuild`, {
      method: "POST",
    }),
  disableRuntime: (runtimeId: string) =>
    request<HubRuntime>(`/hub/runtimes/${runtimeId}/disable`, {
      method: "POST",
    }),
  deleteRuntime: (runtimeId: string) =>
    request<void>(`/hub/runtimes/${runtimeId}`, { method: "DELETE" }),
  listUsers: (params: HubUserListParams = {}) =>
    request<HubPage<HubUser>>(listPath("/hub/admin/users", params)),
  createUser: (username: string, password: string, role: HubUser["role"]) =>
    request<HubUser>("/hub/admin/users", {
      method: "POST",
      body: JSON.stringify({ username, password, role }),
    }),
  updateUser: (
    userId: string,
    patch: Partial<Pick<HubUser, "role" | "disabled">>,
  ) =>
    request<HubUser>(`/hub/admin/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  getSettings: () => request<HubSettings>("/hub/admin/settings"),
  updateSettings: (revision: number, config: HubConfig) =>
    request<HubSettings>("/hub/admin/settings", {
      method: "PUT",
      body: JSON.stringify({ revision, config }),
    }),
  getDockerImages: () => request<HubDockerImageCatalog>("/hub/images"),
  listDockerImagePulls: () =>
    request<HubDockerImagePull[]>("/hub/images/pulls"),
  pullDockerImage: (reference: string) =>
    request<HubDockerImagePull>("/hub/images/pulls", {
      method: "POST",
      body: JSON.stringify({ reference }),
    }),
  listCredentials: (params: HubCredentialListParams = {}) =>
    request<HubPage<HubCredential>>(listPath("/hub/credentials", params)),
  putCredential: (scope: string, name: string, value: string) =>
    request<void>("/hub/credentials", {
      method: "PUT",
      body: JSON.stringify({ scope, name, value }),
    }),
  deleteCredential: (scope: string, name: string) =>
    request<void>(
      `/hub/credentials/${encodeURIComponent(scope)}/${encodeURIComponent(
        name,
      )}`,
      { method: "DELETE" },
    ),
  getOverview: () => request<HubOverview>("/hub/admin/overview"),
  listAuditEvents: (params: HubListParams & { action?: string } = {}) =>
    request<HubPage<HubAuditEvent>>(listPath("/hub/admin/audit", params)),
  meEntitlements: () => request<HubEntitlements>("/hub/me/entitlements"),
  meConsoleProfile: () =>
    request<HubConsoleProfile>("/hub/me/console-profile"),
  listOrgSkills: (
    mine = false,
    opts?: {
      category?: string;
      includeDelisted?: boolean;
      includeDeleted?: boolean;
    },
  ) => {
    const params = new URLSearchParams();
    if (mine) params.set("mine", "true");
    if (opts?.category) params.set("category", opts.category);
    if (opts?.includeDelisted) params.set("include_delisted", "true");
    if (opts?.includeDeleted) params.set("include_deleted", "true");
    const qs = params.toString();
    return request<{
      items: HubOrgSkill[];
      official_protected: boolean;
      categories?: string[];
      viewer?: { can_publish_new?: boolean; can_manage?: boolean };
    }>(qs ? `/hub/org-skills?${qs}` : "/hub/org-skills");
  },
  getOrgSkill: (skillId: string) =>
    request<HubOrgSkillDetail>(`/hub/org-skills/${skillId}`),
  listOrgSkillFiles: (skillId: string) =>
    request<{ skill_id: string; files: HubOrgSkillFile[] }>(
      `/hub/org-skills/${skillId}/files`,
    ),
  publishOrgSkill: (body: HubOrgSkillPublishBody) =>
    request<HubOrgSkill>("/hub/org-skills", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  publishOrgSkillZip: (params: HubOrgSkillZipPublishBody) => {
    const form = new FormData();
    form.append("file", params.file);
    form.append("visibility", params.visibility || "personal");
    if (params.name?.trim()) form.append("name", params.name.trim());
    if (params.display_name?.trim()) {
      form.append("display_name", params.display_name.trim());
    }
    if (params.description?.trim()) {
      form.append("description", params.description.trim());
    }
    if (params.emoji) form.append("emoji", params.emoji);
    if (params.version_text) form.append("version_text", params.version_text);
    if (params.changelog?.trim()) {
      form.append("changelog", params.changelog.trim());
    }
    if (params.category?.trim()) {
      form.append("category", params.category.trim());
    }
    return requestForm<HubOrgSkill>("/hub/org-skills/upload", form);
  },
  patchOrgSkillOps: (skillId: string, body: HubOrgSkillOpsBody) =>
    request<HubOrgSkill>(`/hub/org-skills/${skillId}/ops`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  installOrgSkill: (skillId: string, opts?: { force?: boolean }) => {
    const qs = opts?.force ? "?force=true" : "";
    return request<{
      skill_id: string;
      name: string;
      installed: boolean;
      pinned?: boolean;
      version_text?: string;
    }>(`/hub/org-skills/${skillId}/install${qs}`, { method: "POST" });
  },
  pinOrgSkill: (skillId: string, pinned: boolean) =>
    request<{
      skill_id: string;
      name: string;
      installed: boolean;
      installed_version: string;
      pinned: boolean;
      update_available: boolean;
      newer_version?: string;
      version_text?: string;
    }>(`/hub/org-skills/${skillId}/pin`, {
      method: "PUT",
      body: JSON.stringify({ pinned }),
    }),
  uninstallOrgSkill: (skillId: string) =>
    request<{ skill_id: string; name: string; installed: boolean }>(
      `/hub/org-skills/${skillId}/uninstall`,
      { method: "POST" },
    ),
  deleteOrgSkill: (skillId: string) =>
    request<void>(`/hub/org-skills/${skillId}`, { method: "DELETE" }),
  restoreOrgSkill: (skillId: string) =>
    request<HubOrgSkill>(`/hub/org-skills/${skillId}/restore`, {
      method: "POST",
    }),
  shareOrgSkill: (skillId: string, opts?: { make_public?: boolean }) =>
    request<{
      skill_id: string;
      name?: string;
      display_name?: string;
      version_text?: string;
      visibility?: string;
      owner_username?: string;
      share_path: string;
      share_text: string;
    }>(`/hub/org-skills/${skillId}/share`, {
      method: "POST",
      body: JSON.stringify({ make_public: Boolean(opts?.make_public) }),
    }),

  listOrgKbs: () =>
    request<{ items: HubOrgKb[] }>("/hub/org-kb"),
  createOrgKb: (body: HubOrgKbCreateBody) =>
    request<HubOrgKb>("/hub/org-kb", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteOrgKb: (kbId: string) =>
    request<void>(`/hub/org-kb/${kbId}`, { method: "DELETE" }),
  exportOrgKb: async (kbId: string, filenameHint?: string) => {
    const url = getApiUrl(`/hub/org-kb/${kbId}/export`);
    try {
      await downloadFileFromUrl(
        url,
        filenameHint ? `${filenameHint}.zip` : "org-kb.zip",
        {
          headers: buildAuthHeaders(),
          errorMessage: "知识库导出失败",
        },
      );
    } catch (error) {
      if (error instanceof DownloadCancelledError) return;
      throw error;
    }
  },
  exportAllOrgKbs: async () => {
    const url = getApiUrl("/hub/org-kb/export");
    try {
      await downloadFileFromUrl(url, "org-kb-backup.zip", {
        headers: buildAuthHeaders(),
        errorMessage: "知识库备份失败",
      });
    } catch (error) {
      if (error instanceof DownloadCancelledError) return;
      throw error;
    }
  },
  listOrgKbDocs: (kbId: string) =>
    request<{ items: HubOrgKbDoc[] }>(`/hub/org-kb/${kbId}/docs`),
  ingestOrgKbText: (
    kbId: string,
    body: {
      title: string;
      text: string;
      customer_key?: string;
      effective_from?: string;
      effective_until?: string;
    },
  ) =>
    request<HubOrgKbDoc>(`/hub/org-kb/${kbId}/docs/text`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  uploadOrgKbDoc: (
    kbId: string,
    file: File,
    opts?: {
      title?: string;
      customer_key?: string;
      effective_from?: string;
      effective_until?: string;
    },
  ) => {
    const form = new FormData();
    form.append("file", file);
    if (opts?.title?.trim()) form.append("title", opts.title.trim());
    if (opts?.customer_key?.trim()) {
      form.append("customer_key", opts.customer_key.trim().toLowerCase());
    }
    if (opts?.effective_from?.trim()) {
      form.append("effective_from", opts.effective_from.trim());
    }
    if (opts?.effective_until?.trim()) {
      form.append("effective_until", opts.effective_until.trim());
    }
    return requestForm<HubOrgKbDoc>(`/hub/org-kb/${kbId}/docs`, form);
  },
  deleteOrgKbDoc: (docId: string) =>
    request<void>(`/hub/org-kb/docs/${docId}`, { method: "DELETE" }),
  patchOrgKbDoc: (
    docId: string,
    body: {
      customer_key?: string;
      effective_from?: string;
      effective_until?: string;
    },
  ) =>
    request<HubOrgKbDoc>(`/hub/org-kb/docs/${docId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  patchOrgKbDocCustomer: (docId: string, customerKey: string) =>
    request<HubOrgKbDoc>(`/hub/org-kb/docs/${docId}`, {
      method: "PATCH",
      body: JSON.stringify({ customer_key: customerKey }),
    }),
  searchOrgKb: (body: HubOrgKbSearchBody) =>
    request<HubOrgKbSearchResult>("/hub/org-kb/search", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  feedbackOrgKb: (body: {
    useful: boolean;
    chunk_id?: string;
    doc_id?: string;
    kb_id?: string;
    query?: string;
    note?: string;
  }) =>
    request<{
      feedback_id: string;
      useful: boolean;
      chunk_id: string;
      doc_id: string;
      kb_id: string;
    }>("/hub/org-kb/feedback", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  orgKbFeedbackStats: (kbId: string) =>
    request<{
      kb_id: string;
      useful: number;
      not_useful: number;
      total: number;
    }>(`/hub/org-kb/${kbId}/feedback-stats`),
  listOrgKbBindings: () =>
    request<{ items: HubSkillKbBinding[] }>("/hub/org-kb/bindings"),
  getOrgKbBinding: (skillName: string) =>
    request<HubSkillKbBinding>(
      `/hub/org-kb/bindings/${encodeURIComponent(skillName)}`,
    ),
  setOrgKbBinding: (skillName: string, kbSlugs: string[]) =>
    request<HubSkillKbBinding>(
      `/hub/org-kb/bindings/${encodeURIComponent(skillName)}`,
      {
        method: "PUT",
        body: JSON.stringify({ kb_slugs: kbSlugs }),
      },
    ),
  listOrgKbCustomerGrants: (userId?: string) => {
    const qs = userId
      ? `?user_id=${encodeURIComponent(userId)}`
      : "";
    return request<{
      items: HubOrgKbCustomerGrant[];
      known_customer_keys: string[];
    }>(`/hub/org-kb/customer-grants${qs}`);
  },
  setOrgKbCustomerGrants: (userId: string, customerKeys: string[]) =>
    request<{ user_id: string; customer_keys: string[] }>(
      "/hub/org-kb/customer-grants",
      {
        method: "PUT",
        body: JSON.stringify({
          user_id: userId,
          customer_keys: customerKeys,
        }),
      },
    ),
};

export interface HubEntitlements {
  user_id: string;
  is_hub_admin: boolean;
  roles: string[];
  permissions: string[];
}

export interface HubConsoleNav {
  mode: "member" | "operator" | "admin" | string;
  /** null/undefined = show all (admin). */
  show: string[] | null;
  hide: string[];
  advanced_collapsed?: boolean;
}

export interface HubConsoleFeatures {
  org_skill_publish?: boolean;
  org_skill_manage?: boolean;
  org_kb_write?: boolean;
  org_kb_manage?: boolean;
  hub_governance?: boolean;
  advanced_workspace?: boolean;
}

export interface HubConsoleProfile extends HubEntitlements {
  username?: string;
  nav: HubConsoleNav;
  features: HubConsoleFeatures;
}

export interface HubOrgSkillFile {
  path: string;
  size: number;
}

export type HubOrgSkillCategory =
  | "koujing"
  | "yuqing"
  | "appeal"
  | "report"
  | "drill"
  | "data"
  | "tools"
  | "content"
  | "ops"
  | "finance"
  | "other"
  | string;

export interface HubOrgSkill {
  skill_id: string;
  name: string;
  display_name: string;
  description: string;
  emoji: string;
  visibility: "personal" | "org" | "public";
  version_text: string;
  owner_user_id: string;
  owner_username: string;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
  changelog?: string;
  category?: HubOrgSkillCategory;
  featured?: boolean;
  status?: "active" | "delisted" | "deleted" | string;
  compatibility?: string;
  allowed_tools?: string[];
  install_count?: number;
  installed?: boolean;
  installed_version?: string;
  pinned?: boolean;
  update_available?: boolean;
  newer_version?: string;
  has_bundle?: boolean;
  is_update?: boolean;
  previous_version?: string | null;
  /** Server authz flags (capability + ownership). */
  capabilities?: HubOrgSkillCapabilities;
}

export interface HubOrgSkillCapabilities {
  is_owner?: boolean;
  is_admin?: boolean;
  can_publish_new?: boolean;
  can_update_version?: boolean;
  can_delist?: boolean;
  can_relist?: boolean;
  can_feature?: boolean;
  can_retag?: boolean;
  can_delete_listing?: boolean;
  can_install?: boolean;
  can_upgrade?: boolean;
  can_uninstall?: boolean;
  can_pin?: boolean;
  can_share?: boolean;
  can_list_to_org?: boolean;
  can_make_personal?: boolean;
  can_restore?: boolean;
}

export interface HubOrgSkillDetail extends HubOrgSkill {
  content_md: string;
}

export interface HubOrgSkillPublishBody {
  name: string;
  display_name?: string;
  description?: string;
  content_md: string;
  visibility?: "personal" | "org" | "public";
  emoji?: string;
  version_text?: string;
  changelog?: string;
  category?: HubOrgSkillCategory;
}

export interface HubOrgSkillZipPublishBody {
  file: File;
  visibility?: "personal" | "org" | "public";
  name?: string;
  display_name?: string;
  description?: string;
  emoji?: string;
  version_text?: string;
  changelog?: string;
  category?: HubOrgSkillCategory;
}

export interface HubOrgSkillOpsBody {
  category?: HubOrgSkillCategory;
  featured?: boolean;
  status?: "active" | "delisted";
  visibility?: "personal" | "org" | "public";
}

/** 业务域：前半对齐官方专项，后半为通用创作/工具域（不必绑专家 Skill）。 */
export const ORG_SKILL_CATEGORY_OPTIONS: Array<{
  value: HubOrgSkillCategory;
  label: string;
}> = [
  { value: "koujing", label: "口径" },
  { value: "yuqing", label: "舆情" },
  { value: "appeal", label: "申诉" },
  { value: "report", label: "报告" },
  { value: "drill", label: "演练" },
  { value: "data", label: "数据处理" },
  { value: "tools", label: "工具脚本" },
  { value: "content", label: "文案创意" },
  { value: "ops", label: "运维办公" },
  { value: "finance", label: "金融材料" },
  { value: "other", label: "其他" },
];

export function canPublishOrgSkill(
  permissions: string[] | null | undefined,
): boolean {
  if (!permissions?.length) return false;
  if (permissions.includes("*") || permissions.includes("org_skill:*")) {
    return true;
  }
  return (
    permissions.includes("org_skill:publish") ||
    permissions.includes("org_skill:manage")
  );
}

export function canManageOrgSkill(
  permissions: string[] | null | undefined,
): boolean {
  if (!permissions?.length) return false;
  if (permissions.includes("*") || permissions.includes("org_skill:*")) {
    return true;
  }
  return permissions.includes("org_skill:manage");
}

export interface HubOrgKb {
  kb_id: string;
  slug: string;
  name: string;
  kb_type: string;
  description: string;
  visibility: "org" | "public";
  created_by: string;
  created_at: string;
  updated_at: string;
  doc_count?: number;
  ready_count?: number;
}

export interface HubOrgKbDoc {
  doc_id: string;
  kb_id: string;
  title: string;
  filename: string;
  content_type: string;
  status: "pending" | "ready" | "failed" | string;
  error: string;
  uploaded_by: string;
  customer_key?: string;
  effective_from?: string;
  effective_until?: string;
  created_at: string;
  updated_at: string;
  chunk_count?: number;
}

export interface HubOrgKbCustomerGrant {
  user_id: string;
  customer_key: string;
  granted_by: string;
  created_at: string;
}

export interface HubOrgKbCreateBody {
  slug: string;
  name: string;
  kb_type?: string;
  description?: string;
  visibility?: "org" | "public";
}

export interface HubOrgKbSearchBody {
  query: string;
  kb_id?: string;
  kb_slug?: string;
  skill_name?: string;
  customer_key?: string;
  as_of?: string;
  include_expired?: boolean;
  limit?: number;
}

export interface HubSkillKbBinding {
  skill_name: string;
  kb_slugs: string[];
}

export interface HubOrgKbHit {
  chunk_id: string;
  kb_id: string;
  doc_id: string;
  title: string;
  body?: string;
  snippet?: string;
  score?: number;
  kb_slug?: string;
  kb_name?: string;
  kb_type?: string;
  bound_skill?: string;
  customer_key?: string;
  effective_from?: string;
  effective_until?: string;
}

export interface HubOrgKbSearchResult {
  query: string;
  hits: HubOrgKbHit[];
}

export function canUseOrgKb(
  permissions: string[] | null | undefined,
): boolean {
  if (!permissions?.length) return false;
  if (permissions.includes("*") || permissions.includes("org_kb:*")) {
    return true;
  }
  return (
    permissions.includes("org_kb:use") ||
    permissions.includes("org_kb:write") ||
    permissions.includes("org_kb:manage")
  );
}

export function canWriteOrgKb(
  permissions: string[] | null | undefined,
): boolean {
  if (!permissions?.length) return false;
  if (permissions.includes("*") || permissions.includes("org_kb:*")) {
    return true;
  }
  return (
    permissions.includes("org_kb:write") ||
    permissions.includes("org_kb:manage")
  );
}

export function canManageOrgKb(
  permissions: string[] | null | undefined,
): boolean {
  if (!permissions?.length) return false;
  if (permissions.includes("*") || permissions.includes("org_kb:*")) {
    return true;
  }
  return permissions.includes("org_kb:manage");
}
