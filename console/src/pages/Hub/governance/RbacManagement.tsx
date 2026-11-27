import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  App,
  Button,
  Checkbox,
  Input,
  InputNumber,
  Modal,
  Select,
  Skeleton,
  Switch,
  Tabs,
  Tag,
} from "antd";
import { Plus, RefreshCw, Shield } from "lucide-react";
import { hubApi, type HubUser } from "../../../api/modules/hub";
import {
  governanceRequest as request,
  type RbacEntitlements,
  type RbacOrgDefaults,
  type RbacRole,
} from "../../../api/modules/hubGovernance";
import { governanceErrorMessage } from "./errors";
import styles from "./governance.module.less";

type Props = {
  users: HubUser[];
};

const OFFICIAL_SKILL_OPTIONS = [
  "koujing-xiezhuan",
  "wangping-huashu",
  "shensu-chegao",
  "yuqing-yanpan",
  "yuan-xiezhuan",
  "shiqian-pinggu",
  "paicha-fangan",
  "weike-wenan",
  "yanlian-jiaoben",
  "shuju-chuli",
  "yuqing-baogao",
];

const OFFICIAL_TOOL_OPTIONS = [
  "web_search",
  "web_fetch",
  "kb_search",
  "org_skill_list",
  "org_skill_publish",
  "org_skill_install",
  "org_skill_pin",
  "skill_set_enabled",
];

function limitLabel(value: number | null | undefined, unlimited: string) {
  if (value === undefined || value === null || value < 0) return unlimited;
  return String(value);
}

function isCustomRoleId(roleId: string) {
  return roleId.startsWith("custom.");
}

function customRoleIdFor(userId: string) {
  return `custom.${userId}`;
}

function permissionsFromRole(role: RbacRole | undefined): string[] {
  return role ? [...role.permissions] : [];
}

function expandSkills(permissions: string[]): string[] {
  if (
    permissions.includes("skill:use:*") ||
    permissions.includes("skill:use") ||
    permissions.includes("*")
  ) {
    return [...OFFICIAL_SKILL_OPTIONS];
  }
  return OFFICIAL_SKILL_OPTIONS.filter((s) =>
    permissions.includes(`skill:use:${s}`),
  );
}

function expandTools(permissions: string[]): string[] {
  if (
    permissions.includes("tool:use:*") ||
    permissions.includes("tool:use") ||
    permissions.includes("*")
  ) {
    return [...OFFICIAL_TOOL_OPTIONS];
  }
  return OFFICIAL_TOOL_OPTIONS.filter((t) =>
    permissions.includes(`tool:use:${t}`),
  );
}

function buildPermissions(input: {
  chat: boolean;
  skills: string[];
  tools: string[];
  extra: string[];
}): string[] {
  const perms = new Set<string>(input.extra);
  if (input.chat) perms.add("chat:use");
  if (input.skills.length === OFFICIAL_SKILL_OPTIONS.length) {
    perms.add("skill:use:*");
  } else {
    input.skills.forEach((s) => perms.add(`skill:use:${s}`));
  }
  if (input.tools.length === OFFICIAL_TOOL_OPTIONS.length) {
    perms.add("tool:use:*");
  } else {
    input.tools.forEach((t) => perms.add(`tool:use:${t}`));
  }
  return [...perms].sort();
}

function samePermissionSet(a: string[], b: string[]) {
  if (a.length !== b.length) return false;
  const left = [...a].sort();
  const right = [...b].sort();
  return left.every((v, i) => v === right[i]);
}

/** Normalize wildcards so template matching is stable. */
function normalizeAclPermissions(permissions: string[]): string[] {
  const skills = expandSkills(permissions);
  const tools = expandTools(permissions);
  return buildPermissions({
    chat: permissions.includes("chat:use") || permissions.includes("*"),
    skills,
    tools,
    extra: permissions.filter(
      (p) =>
        p === "rbac:manage" ||
        p === "quota:bypass" ||
        (!p.startsWith("skill:use") &&
          !p.startsWith("tool:use") &&
          p !== "chat:use" &&
          p !== "*"),
    ),
  });
}

export default function RbacManagement(props: Props) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [tab, setTab] = useState("members");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [memberUsers, setMemberUsers] = useState<HubUser[]>(props.users);
  const [roles, setRoles] = useState<RbacRole[]>([]);
  const [defaults, setDefaults] = useState<RbacOrgDefaults | null>(null);
  const [selectedUserId, setSelectedUserId] = useState<string>();
  const [entitlements, setEntitlements] = useState<RbacEntitlements | null>(
    null,
  );
  const [templateRoleId, setTemplateRoleId] = useState<string>();
  const [chatEnabled, setChatEnabled] = useState(true);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [extraPerms, setExtraPerms] = useState<string[]>([]);
  const [aclDirty, setAclDirty] = useState(false);
  const [inheritQuota, setInheritQuota] = useState(true);
  const [dailyChat, setDailyChat] = useState<number | null>(-1);
  const [dailyToken, setDailyToken] = useState<number | null>(-1);
  const [orgChat, setOrgChat] = useState<number>(-1);
  const [orgToken, setOrgToken] = useState<number>(-1);
  const [orgTimezone, setOrgTimezone] = useState("Asia/Shanghai");
  const [roleModalOpen, setRoleModalOpen] = useState(false);
  const [newRoleId, setNewRoleId] = useState("");
  const [newRoleName, setNewRoleName] = useState("");
  const [newRoleDesc, setNewRoleDesc] = useState("");
  const [newRolePerms, setNewRolePerms] = useState<string[]>([
    "chat:use",
    "tool:use:*",
  ]);

  const templateRoles = useMemo(
    () => roles.filter((r) => !isCustomRoleId(r.role_id)),
    [roles],
  );

  const applyPermissionsToForm = useCallback((permissions: string[]) => {
    setChatEnabled(
      permissions.includes("chat:use") || permissions.includes("*"),
    );
    setSelectedSkills(expandSkills(permissions));
    setSelectedTools(expandTools(permissions));
    setExtraPerms(
      permissions.filter(
        (p) =>
          p === "rbac:manage" ||
          p === "quota:bypass" ||
          p === "org_skill:publish" ||
          p === "org_skill:manage" ||
          p === "org_kb:use" ||
          p === "org_kb:write" ||
          p === "org_kb:manage",
      ),
    );
    setAclDirty(false);
  }, []);

  const loadRolesAndDefaults = useCallback(async () => {
    try {
      const [rolePayload, orgDefaults, userPage] = await Promise.all([
        request<{ roles: RbacRole[] }>("admin/rbac/roles"),
        request<RbacOrgDefaults>("admin/rbac/org-defaults"),
        hubApi.listUsers({ page: 1, pageSize: 100 }),
      ]);
      setRoles(rolePayload.roles);
      setDefaults(orgDefaults);
      setOrgChat(orgDefaults.daily_chat_limit);
      setOrgToken(orgDefaults.daily_token_limit);
      setOrgTimezone(orgDefaults.timezone || "Asia/Shanghai");
      setMemberUsers(userPage.items);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const loadUserEntitlements = useCallback(
    async (userId: string) => {
      setBusy(true);
      try {
        const ent = await request<RbacEntitlements>(
          `admin/rbac/users/${userId}/entitlements`,
        );
        setEntitlements(ent);
        setInheritQuota(ent.quota.inherit_org_defaults);
        setDailyChat(ent.quota.daily_chat_limit);
        setDailyToken(ent.quota.daily_token_limit);
        const nonCustom = ent.roles.filter((id) => !isCustomRoleId(id));
        setTemplateRoleId(nonCustom[0]);
        applyPermissionsToForm(ent.permissions);
      } catch (e) {
        message.error(governanceErrorMessage(e, t));
      } finally {
        setBusy(false);
      }
    },
    [applyPermissionsToForm, message, t],
  );

  useEffect(() => {
    void loadRolesAndDefaults();
  }, [loadRolesAndDefaults]);

  useEffect(() => {
    if (props.users.length) setMemberUsers(props.users);
  }, [props.users]);

  useEffect(() => {
    if (selectedUserId) void loadUserEntitlements(selectedUserId);
  }, [selectedUserId, loadUserEntitlements]);

  const members = useMemo(
    () => memberUsers.filter((u) => !u.disabled),
    [memberUsers],
  );

  const selectedUser = members.find((u) => u.user_id === selectedUserId);

  const draftPermissions = useMemo(
    () =>
      buildPermissions({
        chat: chatEnabled,
        skills: selectedSkills,
        tools: selectedTools,
        extra: extraPerms,
      }),
    [chatEnabled, selectedSkills, selectedTools, extraPerms],
  );

  const matchedTemplate = useMemo(() => {
    const normalized = normalizeAclPermissions(draftPermissions);
    return templateRoles.find((role) =>
      samePermissionSet(
        normalizeAclPermissions(permissionsFromRole(role)),
        normalized,
      ),
    );
  }, [draftPermissions, templateRoles]);

  const willSaveAsCustom = !matchedTemplate;

  const markAclDirty = () => setAclDirty(true);

  const applyTemplate = (roleId: string) => {
    setTemplateRoleId(roleId);
    const role = roles.find((r) => r.role_id === roleId);
    applyPermissionsToForm(permissionsFromRole(role));
    setAclDirty(true);
  };

  const saveOrgDefaults = async () => {
    setBusy(true);
    try {
      const next = await request<RbacOrgDefaults>(
        "admin/rbac/org-defaults",
        "PUT",
        {
          daily_chat_limit: orgChat,
          daily_token_limit: orgToken,
          timezone: orgTimezone,
        },
      );
      setDefaults(next);
      message.success(t("hub.rbac.saved"));
    } catch (e) {
      message.error(governanceErrorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const saveMemberAcl = async () => {
    if (!selectedUserId || !selectedUser) return;
    if (entitlements?.is_hub_admin) {
      message.warning(t("hub.rbac.adminLocked"));
      return;
    }
    setBusy(true);
    try {
      const permissions = draftPermissions;
      if (matchedTemplate) {
        await request(`admin/rbac/users/${selectedUserId}/roles`, "PUT", {
          role_ids: [matchedTemplate.role_id],
        });
        setTemplateRoleId(matchedTemplate.role_id);
      } else {
        const roleId = customRoleIdFor(selectedUserId);
        await request("admin/rbac/roles", "POST", {
          role_id: roleId,
          name: t("hub.rbac.customRoleName", {
            user: selectedUser.username,
          }),
          description: t("hub.rbac.customRoleDesc"),
          permissions,
        });
        await request(`admin/rbac/users/${selectedUserId}/roles`, "PUT", {
          role_ids: [roleId],
        });
        setTemplateRoleId(undefined);
      }
      await loadRolesAndDefaults();
      await loadUserEntitlements(selectedUserId);
      message.success(t("hub.rbac.aclSavedHint"));
    } catch (e) {
      message.error(governanceErrorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const saveUserQuota = async () => {
    if (!selectedUserId) return;
    setBusy(true);
    try {
      await request(`admin/rbac/users/${selectedUserId}/quota`, "PUT", {
        inherit_org_defaults: inheritQuota,
        daily_chat_limit: inheritQuota ? null : dailyChat,
        daily_token_limit: inheritQuota ? null : dailyToken,
      });
      await loadUserEntitlements(selectedUserId);
      message.success(t("hub.rbac.saved"));
    } catch (e) {
      message.error(governanceErrorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const createRole = async () => {
    if (!newRoleId.trim() || !newRoleName.trim()) {
      message.error(t("hub.rbac.roleRequired"));
      return;
    }
    if (isCustomRoleId(newRoleId.trim())) {
      message.error(t("hub.rbac.customRoleIdReserved"));
      return;
    }
    setBusy(true);
    try {
      await request("admin/rbac/roles", "POST", {
        role_id: newRoleId.trim(),
        name: newRoleName.trim(),
        description: newRoleDesc.trim(),
        permissions: newRolePerms,
      });
      setRoleModalOpen(false);
      setNewRoleId("");
      setNewRoleName("");
      setNewRoleDesc("");
      setNewRolePerms(["chat:use", "tool:use:*"]);
      await loadRolesAndDefaults();
      message.success(t("hub.rbac.saved"));
    } catch (e) {
      message.error(governanceErrorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  const deleteRole = async (roleId: string) => {
    setBusy(true);
    try {
      await request(`admin/rbac/roles/${roleId}`, "DELETE");
      await loadRolesAndDefaults();
      message.success(t("hub.rbac.saved"));
    } catch (e) {
      message.error(governanceErrorMessage(e, t));
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return (
      <div role="alert" className={styles.card}>
        {governanceErrorMessage(error, t)}
        <Button onClick={() => void loadRolesAndDefaults()}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }

  if (!defaults) return <Skeleton active />;

  const adminLocked = Boolean(entitlements?.is_hub_admin);

  return (
    <section className={styles.panel}>
      <div className={styles.heading}>
        <div>
          <h2>{t("hub.rbac.title")}</h2>
          <p>{t("hub.rbac.description")}</p>
        </div>
        <Button
          icon={<RefreshCw size={15} />}
          onClick={() => void loadRolesAndDefaults()}
        >
          {t("common.refresh")}
        </Button>
      </div>

      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={[
          {
            key: "members",
            label: t("hub.rbac.tabs.members"),
            children: (
              <div className={styles.grid}>
                <article className={styles.card}>
                  <h3>{t("hub.rbac.selectUser")}</h3>
                  <Select
                    showSearch
                    optionFilterProp="label"
                    placeholder={t("hub.rbac.selectUser")}
                    value={selectedUserId}
                    onChange={setSelectedUserId}
                    options={members.map((u) => ({
                      value: u.user_id,
                      label: `${u.username} (${u.role})`,
                    }))}
                    style={{ width: "100%" }}
                  />
                  {!selectedUserId && (
                    <p>{t("hub.rbac.selectUserHint")}</p>
                  )}
                  {selectedUserId && entitlements && (
                    <>
                      <h3>{t("hub.rbac.applyTemplate")}</h3>
                      <p>{t("hub.rbac.applyTemplateHint")}</p>
                      <Select
                        allowClear
                        placeholder={t("hub.rbac.applyTemplate")}
                        value={templateRoleId}
                        disabled={adminLocked}
                        onChange={(value) => {
                          if (value) applyTemplate(value);
                          else setTemplateRoleId(undefined);
                        }}
                        options={templateRoles.map((r) => ({
                          value: r.role_id,
                          label: `${r.name} (${r.role_id})`,
                        }))}
                        style={{ width: "100%" }}
                      />

                      <h3>{t("hub.rbac.directAcl")}</h3>
                      <p>{t("hub.rbac.directAclHint")}</p>
                      {adminLocked && (
                        <Tag color="gold">{t("hub.rbac.adminLocked")}</Tag>
                      )}
                      <label className={styles.inline}>
                        <Switch
                          checked={chatEnabled}
                          disabled={adminLocked}
                          onChange={(v) => {
                            setChatEnabled(v);
                            markAclDirty();
                          }}
                        />
                        <span>chat:use</span>
                      </label>

                      <div>
                        <strong>{t("hub.rbac.allowedSkills")}</strong>
                        <div className={styles.inline} style={{ marginTop: 8 }}>
                          <Button
                            size="small"
                            disabled={adminLocked}
                            onClick={() => {
                              setSelectedSkills([...OFFICIAL_SKILL_OPTIONS]);
                              markAclDirty();
                            }}
                          >
                            {t("hub.rbac.selectAll")}
                          </Button>
                          <Button
                            size="small"
                            disabled={adminLocked}
                            onClick={() => {
                              setSelectedSkills([]);
                              markAclDirty();
                            }}
                          >
                            {t("hub.rbac.clearAll")}
                          </Button>
                        </div>
                        <Checkbox.Group
                          disabled={adminLocked}
                          value={selectedSkills}
                          onChange={(v) => {
                            setSelectedSkills(v as string[]);
                            markAclDirty();
                          }}
                          options={OFFICIAL_SKILL_OPTIONS.map((s) => ({
                            label: s,
                            value: s,
                          }))}
                          style={{
                            display: "grid",
                            gridTemplateColumns:
                              "repeat(auto-fit, minmax(180px, 1fr))",
                            gap: 8,
                            marginTop: 10,
                          }}
                        />
                      </div>

                      <div>
                        <strong>{t("hub.rbac.allowedTools")}</strong>
                        <Checkbox.Group
                          disabled={adminLocked}
                          value={selectedTools}
                          onChange={(v) => {
                            setSelectedTools(v as string[]);
                            markAclDirty();
                          }}
                          options={OFFICIAL_TOOL_OPTIONS.map((tool) => ({
                            label: tool,
                            value: tool,
                          }))}
                          style={{
                            display: "grid",
                            gridTemplateColumns:
                              "repeat(auto-fit, minmax(160px, 1fr))",
                            gap: 8,
                            marginTop: 10,
                          }}
                        />
                      </div>

                      <div>
                        <strong>{t("hub.rbac.advancedPerms")}</strong>
                        <Checkbox.Group
                          disabled={adminLocked}
                          value={extraPerms}
                          onChange={(v) => {
                            setExtraPerms(v as string[]);
                            markAclDirty();
                          }}
                          options={[
                            { label: "rbac:manage", value: "rbac:manage" },
                            { label: "quota:bypass", value: "quota:bypass" },
                            {
                              label: "org_skill:publish（可上架/发版自己的技能）",
                              value: "org_skill:publish",
                            },
                            {
                              label: "org_skill:manage（代管任意技能：精选/分类）",
                              value: "org_skill:manage",
                            },
                            { label: "org_kb:use（检索组织知识库）", value: "org_kb:use" },
                            { label: "org_kb:write（上传知识库）", value: "org_kb:write" },
                            { label: "org_kb:manage（管理知识库）", value: "org_kb:manage" },
                          ]}
                          style={{
                            display: "flex",
                            flexWrap: "wrap",
                            gap: 16,
                            marginTop: 10,
                          }}
                        />
                      </div>

                      <p>
                        {willSaveAsCustom
                          ? t("hub.rbac.willSaveCustom")
                          : t("hub.rbac.willSaveTemplate", {
                              role: matchedTemplate?.role_id,
                            })}
                        {aclDirty ? ` · ${t("hub.rbac.unsaved")}` : ""}
                      </p>
                      <Button
                        type="primary"
                        loading={busy}
                        disabled={adminLocked}
                        onClick={() => void saveMemberAcl()}
                      >
                        {t("hub.rbac.saveAcl")}
                      </Button>

                      <h3>{t("hub.rbac.dailyQuota")}</h3>
                      <label className={styles.inline}>
                        <Switch
                          checked={inheritQuota}
                          onChange={setInheritQuota}
                        />
                        <span>{t("hub.rbac.inheritOrgDefaults")}</span>
                      </label>
                      {!inheritQuota && (
                        <div className={styles.form}>
                          <label>
                            {t("hub.rbac.dailyChatLimit")}
                            <InputNumber
                              value={dailyChat ?? undefined}
                              onChange={(v) => setDailyChat(v)}
                              style={{ width: "100%" }}
                            />
                          </label>
                          <label>
                            {t("hub.rbac.dailyTokenLimit")}
                            <InputNumber
                              value={dailyToken ?? undefined}
                              onChange={(v) => setDailyToken(v)}
                              style={{ width: "100%" }}
                            />
                          </label>
                          <p>{t("hub.rbac.limitHint")}</p>
                        </div>
                      )}
                      <Button
                        loading={busy}
                        onClick={() => void saveUserQuota()}
                      >
                        {t("hub.rbac.saveQuota")}
                      </Button>
                    </>
                  )}
                </article>

                <article className={styles.card}>
                  <h3>{t("hub.rbac.preview")}</h3>
                  {!entitlements ? (
                    <p>{t("hub.rbac.selectUserHint")}</p>
                  ) : (
                    <>
                      <p>
                        {t("hub.rbac.currentRoles")}:{" "}
                        {entitlements.roles.length
                          ? entitlements.roles.join(", ")
                          : "—"}
                      </p>
                      <p>
                        {t("hub.rbac.usageToday")}: chat=
                        {entitlements.usage_today.chat_count}, token=
                        {entitlements.usage_today.token_count} (
                        {entitlements.usage_date})
                      </p>
                      <div>
                        <strong>{t("hub.rbac.permissions")}</strong>
                        <div className={styles.tags}>
                          {entitlements.permissions.map((p) => (
                            <Tag key={p}>{p}</Tag>
                          ))}
                        </div>
                      </div>
                      <div>
                        <strong>{t("hub.rbac.allowedSkills")}</strong>
                        <div className={styles.tags}>
                          {(entitlements.allowed_skills || []).length === 0 ? (
                            <Tag>{t("hub.rbac.noSkills")}</Tag>
                          ) : (
                            entitlements.allowed_skills.map((s) => (
                              <Tag key={s} color="blue">
                                {s}
                              </Tag>
                            ))
                          )}
                        </div>
                      </div>
                      <div>
                        <strong>{t("hub.rbac.allowedTools")}</strong>
                        <div className={styles.tags}>
                          {(entitlements.allowed_tools || []).length === 0 ? (
                            <Tag>{t("hub.rbac.noTools")}</Tag>
                          ) : (
                            entitlements.allowed_tools.map((tool) => (
                              <Tag key={tool} color="green">
                                {tool}
                              </Tag>
                            ))
                          )}
                        </div>
                      </div>
                      <p>{t("hub.rbac.syncHint")}</p>
                    </>
                  )}
                </article>
              </div>
            ),
          },
          {
            key: "roles",
            label: t("hub.rbac.tabs.roles"),
            children: (
              <div className={styles.grid}>
                {roles.map((role) => (
                  <article key={role.role_id} className={styles.card}>
                    <h3>
                      {role.name}{" "}
                      {role.is_system && (
                        <Tag>{t("hub.rbac.systemRole")}</Tag>
                      )}
                      {isCustomRoleId(role.role_id) && (
                        <Tag color="purple">{t("hub.rbac.customRoleTag")}</Tag>
                      )}
                    </h3>
                    <p>{role.description || role.role_id}</p>
                    <div className={styles.tags}>
                      {role.permissions.map((p) => (
                        <Tag key={p}>{p}</Tag>
                      ))}
                    </div>
                    {!role.is_system && (
                      <Button
                        danger
                        loading={busy}
                        onClick={() => void deleteRole(role.role_id)}
                      >
                        {t("common.delete")}
                      </Button>
                    )}
                  </article>
                ))}
                <article className={styles.card}>
                  <h3>{t("hub.rbac.createRole")}</h3>
                  <p>{t("hub.rbac.createRoleHint")}</p>
                  <Button
                    type="primary"
                    icon={<Plus size={15} />}
                    onClick={() => setRoleModalOpen(true)}
                  >
                    {t("hub.rbac.createRole")}
                  </Button>
                </article>
              </div>
            ),
          },
          {
            key: "org",
            label: t("hub.rbac.tabs.org"),
            children: (
              <article className={styles.card}>
                <h3>{t("hub.rbac.orgDefaults")}</h3>
                <p>{t("hub.rbac.orgDefaultsHint")}</p>
                <div className={styles.form}>
                  <label>
                    {t("hub.rbac.dailyChatLimit")}
                    <InputNumber
                      value={orgChat}
                      onChange={(v) => setOrgChat(v ?? -1)}
                      style={{ width: "100%" }}
                    />
                  </label>
                  <label>
                    {t("hub.rbac.dailyTokenLimit")}
                    <InputNumber
                      value={orgToken}
                      onChange={(v) => setOrgToken(v ?? -1)}
                      style={{ width: "100%" }}
                    />
                  </label>
                  <label>
                    {t("hub.rbac.timezone")}
                    <Input
                      value={orgTimezone}
                      onChange={(e) => setOrgTimezone(e.target.value)}
                    />
                  </label>
                  <p>{t("hub.rbac.limitHint")}</p>
                  <p>
                    {t("hub.rbac.currentDefaults")}: chat=
                    {limitLabel(defaults.daily_chat_limit, t("hub.rbac.unlimited"))}
                    , token=
                    {limitLabel(
                      defaults.daily_token_limit,
                      t("hub.rbac.unlimited"),
                    )}
                  </p>
                  <Button
                    type="primary"
                    loading={busy}
                    onClick={() => void saveOrgDefaults()}
                  >
                    {t("common.save")}
                  </Button>
                </div>
              </article>
            ),
          },
        ]}
      />

      <Modal
        title={t("hub.rbac.createRole")}
        open={roleModalOpen}
        onCancel={() => setRoleModalOpen(false)}
        onOk={() => void createRole()}
        confirmLoading={busy}
        okText={t("common.save")}
      >
        <div className={styles.form}>
          <label>
            {t("hub.rbac.roleId")}
            <Input
              value={newRoleId}
              onChange={(e) => setNewRoleId(e.target.value)}
              placeholder="team.writer"
            />
          </label>
          <label>
            {t("hub.rbac.roleName")}
            <Input
              value={newRoleName}
              onChange={(e) => setNewRoleName(e.target.value)}
            />
          </label>
          <label>
            {t("hub.rbac.roleDescription")}
            <Input.TextArea
              value={newRoleDesc}
              onChange={(e) => setNewRoleDesc(e.target.value)}
              rows={2}
            />
          </label>
          <div>
            <strong>{t("hub.rbac.permissions")}</strong>
            <Checkbox.Group
              value={newRolePerms}
              onChange={(v) => setNewRolePerms(v as string[])}
              options={[
                { label: "chat:use", value: "chat:use" },
                { label: "skill:use:*", value: "skill:use:*" },
                { label: "tool:use:*", value: "tool:use:*" },
                { label: "rbac:manage", value: "rbac:manage" },
                { label: "quota:bypass", value: "quota:bypass" },
                {
                  label: "org_skill:publish（可上架/发版自己的技能）",
                  value: "org_skill:publish",
                },
                {
                  label: "org_skill:manage（代管任意技能：精选/分类）",
                  value: "org_skill:manage",
                },
                { label: "org_kb:use（检索组织知识库）", value: "org_kb:use" },
                { label: "org_kb:write（上传知识库）", value: "org_kb:write" },
                { label: "org_kb:manage（管理知识库）", value: "org_kb:manage" },
                ...OFFICIAL_SKILL_OPTIONS.map((s) => ({
                  label: `skill:use:${s}`,
                  value: `skill:use:${s}`,
                })),
                ...OFFICIAL_TOOL_OPTIONS.map((tool) => ({
                  label: `tool:use:${tool}`,
                  value: `tool:use:${tool}`,
                })),
              ]}
            />
          </div>
        </div>
      </Modal>

      <div className={styles.card}>
        <Shield size={18} />
        <p>{t("hub.rbac.footerNote")}</p>
      </div>
    </section>
  );
}
