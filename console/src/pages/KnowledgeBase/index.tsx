import { useCallback, useEffect, useMemo, useState } from "react";
import {
  App,
  Button,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  Upload,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  BookOpen,
  Download,
  Link2,
  Plus,
  RefreshCw,
  Search,
  Shield,
  Trash2,
  Upload as UploadIcon,
} from "lucide-react";
import {
  canManageOrgKb,
  canUseOrgKb,
  canWriteOrgKb,
  hubApi,
  type HubOrgKb,
  type HubOrgKbCustomerGrant,
  type HubOrgKbDoc,
  type HubOrgKbHit,
  type HubSkillKbBinding,
} from "../../api/modules/hub";
import styles from "./index.module.less";

const KB_TYPE_LABEL: Record<string, string> = {
  koujing: "口径库",
  case: "案例库",
  template: "模板资产库",
  customer: "客户资料库",
  other: "其他",
};

const OFFICIAL_SKILL_OPTIONS = [
  { value: "koujing-xiezhuan", label: "koujing-xiezhuan · 口径撰写" },
  { value: "yuan-xiezhuan", label: "yuan-xiezhuan · 原声改写" },
  { value: "wangping-huashu", label: "wangping-huashu · 网评话术" },
  { value: "shensu-chegao", label: "shensu-chegao · 申诉撤稿" },
  { value: "yuqing-yanpan", label: "yuqing-yanpan · 舆情研判" },
  { value: "paicha-fangan", label: "paicha-fangan · 排查方案" },
  { value: "shiqian-pinggu", label: "shiqian-pinggu · 事前评估" },
  { value: "yuqing-baogao", label: "yuqing-baogao · 舆情报告" },
  { value: "weike-wenan", label: "weike-wenan · 微课文案" },
  { value: "yanlian-jiaoben", label: "yanlian-jiaoben · 演练脚本" },
  { value: "shuju-chuli", label: "shuju-chuli · 数据处理" },
];

function statusColor(status: string) {
  if (status === "ready") return "success";
  if (status === "failed") return "error";
  return "processing";
}

export default function KnowledgeBasePage() {
  const { message, modal } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [canWrite, setCanWrite] = useState(false);
  const [canManage, setCanManage] = useState(false);
  const [libraries, setLibraries] = useState<HubOrgKb[]>([]);
  const [selectedKbId, setSelectedKbId] = useState<string>();
  const [docs, setDocs] = useState<HubOrgKbDoc[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchHits, setSearchHits] = useState<HubOrgKbHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [newSlug, setNewSlug] = useState("");
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("koujing");
  const [newDesc, setNewDesc] = useState("");
  const [creating, setCreating] = useState(false);
  const [bindings, setBindings] = useState<HubSkillKbBinding[]>([]);
  const [bindingsLoading, setBindingsLoading] = useState(false);
  const [bindOpen, setBindOpen] = useState(false);
  const [bindSkill, setBindSkill] = useState<string>();
  const [bindSlugs, setBindSlugs] = useState<string[]>([]);
  const [bindSaving, setBindSaving] = useState(false);
  const [uploadCustomerKey, setUploadCustomerKey] = useState("");
  const [uploadFrom, setUploadFrom] = useState("");
  const [uploadUntil, setUploadUntil] = useState("");
  const [metaOpen, setMetaOpen] = useState(false);
  const [metaDoc, setMetaDoc] = useState<HubOrgKbDoc | null>(null);
  const [metaFrom, setMetaFrom] = useState("");
  const [metaUntil, setMetaUntil] = useState("");
  const [metaCustomer, setMetaCustomer] = useState("");
  const [metaSaving, setMetaSaving] = useState(false);
  const [textOpen, setTextOpen] = useState(false);
  const [textTitle, setTextTitle] = useState("");
  const [textBody, setTextBody] = useState("");
  const [textSaving, setTextSaving] = useState(false);
  const [grants, setGrants] = useState<HubOrgKbCustomerGrant[]>([]);
  const [knownCustomerKeys, setKnownCustomerKeys] = useState<string[]>([]);
  const [grantsLoading, setGrantsLoading] = useState(false);
  const [grantOpen, setGrantOpen] = useState(false);
  const [grantUserId, setGrantUserId] = useState("");
  const [grantKeys, setGrantKeys] = useState<string[]>([]);
  const [grantSaving, setGrantSaving] = useState(false);
  const [exportingKb, setExportingKb] = useState(false);
  const [exportingAll, setExportingAll] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState<string | null>(null);
  const [feedbackDone, setFeedbackDone] = useState<Record<string, boolean>>(
    {},
  );
  const [feedbackStats, setFeedbackStats] = useState<{
    useful: number;
    not_useful: number;
    total: number;
  } | null>(null);

  const selectedKb = useMemo(
    () => libraries.find((k) => k.kb_id === selectedKbId),
    [libraries, selectedKbId],
  );

  const kbSlugOptions = useMemo(
    () =>
      libraries.map((kb) => ({
        value: kb.slug,
        label: `${kb.name} (${kb.slug})`,
      })),
    [libraries],
  );

  const loadBindings = useCallback(async () => {
    setBindingsLoading(true);
    try {
      const res = await hubApi.listOrgKbBindings();
      setBindings(res.items || []);
    } catch (e) {
      message.error((e as Error).message || "加载 Skill 绑定失败");
      setBindings([]);
    } finally {
      setBindingsLoading(false);
    }
  }, [message]);

  const loadGrants = useCallback(async () => {
    setGrantsLoading(true);
    try {
      const res = await hubApi.listOrgKbCustomerGrants();
      setGrants(res.items || []);
      setKnownCustomerKeys(res.known_customer_keys || []);
    } catch (e) {
      // Non-manage users may only see own grants; ignore soft failures.
      setGrants([]);
      setKnownCustomerKeys([]);
      if (!(e as Error).message?.includes("403")) {
        message.error((e as Error).message || "加载客户授权失败");
      }
    } finally {
      setGrantsLoading(false);
    }
  }, [message]);

  const loadLibraries = useCallback(async () => {
    setLoading(true);
    try {
      const ent = await hubApi.meEntitlements();
      const perms = ent.permissions || [];
      if (!(ent.is_hub_admin || canUseOrgKb(perms))) {
        setForbidden(true);
        setLibraries([]);
        return;
      }
      setForbidden(false);
      const manage = Boolean(ent.is_hub_admin || canManageOrgKb(perms));
      setCanWrite(Boolean(ent.is_hub_admin || canWriteOrgKb(perms)));
      setCanManage(manage);
      const res = await hubApi.listOrgKbs();
      setLibraries(res.items || []);
      setSelectedKbId((prev) => {
        if (prev && res.items.some((k) => k.kb_id === prev)) return prev;
        return res.items[0]?.kb_id;
      });
      await loadBindings();
      await loadGrants();
    } catch (e) {
      const err = e as Error;
      if (String(err.message || "").includes("403")) {
        setForbidden(true);
      } else {
        message.error(err.message || "加载知识库失败");
      }
    } finally {
      setLoading(false);
    }
  }, [loadBindings, loadGrants, message]);

  const loadDocs = useCallback(
    async (kbId: string) => {
      setDocsLoading(true);
      try {
        const res = await hubApi.listOrgKbDocs(kbId);
        setDocs(res.items || []);
      } catch (e) {
        message.error((e as Error).message || "加载文档失败");
        setDocs([]);
      } finally {
        setDocsLoading(false);
      }
    },
    [message],
  );

  const loadFeedbackStats = useCallback(async (kbId: string) => {
    try {
      const stats = await hubApi.orgKbFeedbackStats(kbId);
      setFeedbackStats({
        useful: stats.useful,
        not_useful: stats.not_useful,
        total: stats.total,
      });
    } catch {
      setFeedbackStats(null);
    }
  }, []);

  useEffect(() => {
    void loadLibraries();
  }, [loadLibraries]);

  useEffect(() => {
    if (selectedKbId) {
      void loadDocs(selectedKbId);
      void loadFeedbackStats(selectedKbId);
    } else {
      setDocs([]);
      setFeedbackStats(null);
    }
  }, [selectedKbId, loadDocs, loadFeedbackStats]);

  const handleUpload = async (file: File) => {
    if (!selectedKbId || !canWrite) return false;
    const key = uploadCustomerKey.trim().toLowerCase();
    if (selectedKb?.kb_type === "customer" && !key) {
      message.warning("客户资料库上传必须填写客户标识");
      return false;
    }
    setUploading(true);
    try {
      await hubApi.uploadOrgKbDoc(selectedKbId, file, {
        customer_key: key || undefined,
        effective_from: uploadFrom.trim() || undefined,
        effective_until: uploadUntil.trim() || undefined,
      });
      message.success(`已上传「${file.name}」`);
      await loadDocs(selectedKbId);
      await loadLibraries();
    } catch (e) {
      message.error((e as Error).message || "上传失败");
    } finally {
      setUploading(false);
    }
    return false;
  };

  const openMetaEditor = (doc: HubOrgKbDoc) => {
    setMetaDoc(doc);
    setMetaCustomer(doc.customer_key || "");
    setMetaFrom(doc.effective_from || "");
    setMetaUntil(doc.effective_until || "");
    setMetaOpen(true);
  };

  const handleSaveMeta = async () => {
    if (!metaDoc) return;
    setMetaSaving(true);
    try {
      await hubApi.patchOrgKbDoc(metaDoc.doc_id, {
        customer_key: metaCustomer.trim().toLowerCase(),
        effective_from: metaFrom.trim(),
        effective_until: metaUntil.trim(),
      });
      message.success("已更新文档元数据");
      setMetaOpen(false);
      if (selectedKbId) await loadDocs(selectedKbId);
    } catch (e) {
      message.error((e as Error).message || "保存失败");
    } finally {
      setMetaSaving(false);
    }
  };

  const handleIngestText = async () => {
    if (!selectedKbId || !canWrite) return;
    const title = textTitle.trim();
    const body = textBody.trim();
    if (!title || !body) {
      message.warning("请填写标题与正文");
      return;
    }
    const key = uploadCustomerKey.trim().toLowerCase();
    if (selectedKb?.kb_type === "customer" && !key) {
      message.warning("客户资料库沉淀必须填写客户标识");
      return;
    }
    setTextSaving(true);
    try {
      await hubApi.ingestOrgKbText(selectedKbId, {
        title,
        text: body,
        customer_key: key || undefined,
        effective_from: uploadFrom.trim() || undefined,
        effective_until: uploadUntil.trim() || undefined,
      });
      message.success(`已沉淀「${title}」`);
      setTextOpen(false);
      setTextTitle("");
      setTextBody("");
      await loadDocs(selectedKbId);
      await loadLibraries();
    } catch (e) {
      message.error((e as Error).message || "沉淀失败");
    } finally {
      setTextSaving(false);
    }
  };

  const handleDeleteDoc = (doc: HubOrgKbDoc) => {
    modal.confirm({
      title: `下架文档「${doc.title}」？`,
      content: "下架后不可被 kb_search 召回。",
      okType: "danger",
      onOk: async () => {
        try {
          await hubApi.deleteOrgKbDoc(doc.doc_id);
          message.success("已下架");
          if (selectedKbId) await loadDocs(selectedKbId);
          await loadLibraries();
        } catch (e) {
          message.error((e as Error).message || "下架失败");
        }
      },
    });
  };

  const handleSearch = async () => {
    const q = searchQuery.trim();
    if (!q) {
      message.warning("请输入检索词");
      return;
    }
    setSearching(true);
    try {
      const res = await hubApi.searchOrgKb({
        query: q,
        kb_id: selectedKbId,
        limit: 8,
      });
      setSearchHits(res.hits || []);
      setFeedbackDone({});
      if (!(res.hits || []).length) message.info("无命中");
    } catch (e) {
      message.error((e as Error).message || "检索失败");
    } finally {
      setSearching(false);
    }
  };

  const handleFeedback = async (hit: HubOrgKbHit, useful: boolean) => {
    const key = hit.chunk_id || hit.doc_id;
    if (!key || feedbackDone[key] !== undefined) return;
    setFeedbackBusy(key);
    try {
      await hubApi.feedbackOrgKb({
        useful,
        chunk_id: hit.chunk_id,
        doc_id: hit.doc_id,
        kb_id: hit.kb_id || selectedKbId,
        query: searchQuery.trim(),
      });
      setFeedbackDone((prev) => ({ ...prev, [key]: useful }));
      message.success(useful ? "已标记有用" : "已标记无用");
      if (selectedKbId) void loadFeedbackStats(selectedKbId);
    } catch (e) {
      message.error((e as Error).message || "反馈失败");
    } finally {
      setFeedbackBusy(null);
    }
  };

  const handleCreate = async () => {
    if (!newSlug.trim() || !newName.trim()) {
      message.warning("请填写标识与名称");
      return;
    }
    setCreating(true);
    try {
      const kb = await hubApi.createOrgKb({
        slug: newSlug.trim().toLowerCase(),
        name: newName.trim(),
        kb_type: newType,
        description: newDesc.trim(),
      });
      message.success(`已创建「${kb.name}」`);
      setCreateOpen(false);
      setNewSlug("");
      setNewName("");
      setNewDesc("");
      setNewType("koujing");
      await loadLibraries();
      setSelectedKbId(kb.kb_id);
    } catch (e) {
      message.error((e as Error).message || "创建失败");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteKb = () => {
    if (!selectedKb || !canManage) return;
    modal.confirm({
      title: `删除知识库「${selectedKb.name}」？`,
      content: "库与文档将软删除，不可被检索。",
      okType: "danger",
      onOk: async () => {
        try {
          await hubApi.deleteOrgKb(selectedKb.kb_id);
          message.success("已删除");
          await loadLibraries();
        } catch (e) {
          message.error((e as Error).message || "删除失败");
        }
      },
    });
  };

  const handleExportKb = async () => {
    if (!selectedKb) return;
    setExportingKb(true);
    try {
      await hubApi.exportOrgKb(
        selectedKb.kb_id,
        `org-kb-${selectedKb.slug || selectedKb.kb_id}`,
      );
      message.success(`已导出「${selectedKb.name}」`);
    } catch (e) {
      message.error((e as Error).message || "导出失败");
    } finally {
      setExportingKb(false);
    }
  };

  const handleExportAll = async () => {
    if (!canManage) return;
    setExportingAll(true);
    try {
      await hubApi.exportAllOrgKbs();
      message.success("已下载全库备份 zip");
    } catch (e) {
      message.error((e as Error).message || "备份失败");
    } finally {
      setExportingAll(false);
    }
  };

  const openBindEditor = (row?: HubSkillKbBinding) => {
    setBindSkill(row?.skill_name || undefined);
    setBindSlugs(row?.kb_slugs ? [...row.kb_slugs] : []);
    setBindOpen(true);
  };

  const handleSaveBinding = async () => {
    const name = (bindSkill || "").trim().toLowerCase();
    if (!name) {
      message.warning("请选择或填写 Skill 名");
      return;
    }
    setBindSaving(true);
    try {
      await hubApi.setOrgKbBinding(name, bindSlugs);
      message.success(`已保存「${name}」绑定`);
      setBindOpen(false);
      await loadBindings();
    } catch (e) {
      message.error((e as Error).message || "保存绑定失败");
    } finally {
      setBindSaving(false);
    }
  };

  const handleClearBinding = (row: HubSkillKbBinding) => {
    if (!canManage) return;
    modal.confirm({
      title: `清空「${row.skill_name}」的知识库绑定？`,
      content: "清空后 kb_search(skill=…) 将不再限定到特定库。",
      okType: "danger",
      onOk: async () => {
        try {
          await hubApi.setOrgKbBinding(row.skill_name, []);
          message.success("已清空绑定");
          await loadBindings();
        } catch (e) {
          message.error((e as Error).message || "清空失败");
        }
      },
    });
  };

  const openGrantEditor = (userId?: string) => {
    const uid = userId || "";
    setGrantUserId(uid);
    setGrantKeys(
      grants.filter((g) => g.user_id === uid).map((g) => g.customer_key),
    );
    setGrantOpen(true);
  };

  const handleSaveGrants = async () => {
    const uid = grantUserId.trim();
    if (!uid) {
      message.warning("请填写用户 ID");
      return;
    }
    setGrantSaving(true);
    try {
      await hubApi.setOrgKbCustomerGrants(uid, grantKeys);
      message.success(`已更新「${uid}」客户授权`);
      setGrantOpen(false);
      await loadGrants();
    } catch (e) {
      message.error((e as Error).message || "保存授权失败");
    } finally {
      setGrantSaving(false);
    }
  };

  const grantsByUser = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const g of grants) {
      const list = map.get(g.user_id) || [];
      list.push(g.customer_key);
      map.set(g.user_id, list);
    }
    return Array.from(map.entries()).map(([user_id, customer_keys]) => ({
      user_id,
      customer_keys,
    }));
  }, [grants]);

  const bindingColumns: ColumnsType<HubSkillKbBinding> = [
    {
      title: "Skill",
      dataIndex: "skill_name",
      width: 220,
      render: (v: string) => <code>{v}</code>,
    },
    {
      title: "绑定知识库（优先级从左到右）",
      dataIndex: "kb_slugs",
      render: (slugs: string[]) =>
        slugs?.length ? (
          <Space size={[4, 4]} wrap>
            {slugs.map((slug) => {
              const kb = libraries.find((k) => k.slug === slug);
              return (
                <Tag key={slug}>
                  {kb?.name || slug}
                  <Typography.Text type="secondary"> · {slug}</Typography.Text>
                </Tag>
              );
            })}
          </Space>
        ) : (
          <Typography.Text type="secondary">未绑定</Typography.Text>
        ),
    },
    {
      title: "",
      key: "actions",
      width: 120,
      render: (_, row) =>
        canManage ? (
          <Space size={4}>
            <Button type="link" size="small" onClick={() => openBindEditor(row)}>
              编辑
            </Button>
            <Button
              type="link"
              size="small"
              danger
              onClick={() => handleClearBinding(row)}
            >
              清空
            </Button>
          </Space>
        ) : null,
    },
  ];

  const grantColumns: ColumnsType<{
    user_id: string;
    customer_keys: string[];
  }> = [
    {
      title: "用户",
      dataIndex: "user_id",
      width: 200,
      render: (v: string) => <code>{v}</code>,
    },
    {
      title: "可见客户",
      dataIndex: "customer_keys",
      render: (keys: string[]) =>
        keys?.length ? (
          <Space size={[4, 4]} wrap>
            {keys.map((k) => (
              <Tag key={k}>{k}</Tag>
            ))}
          </Space>
        ) : (
          <Typography.Text type="secondary">无</Typography.Text>
        ),
    },
    {
      title: "",
      key: "actions",
      width: 88,
      render: (_, row) =>
        canManage ? (
          <Button
            type="link"
            size="small"
            onClick={() => openGrantEditor(row.user_id)}
          >
            编辑
          </Button>
        ) : null,
    },
  ];

  const docColumns: ColumnsType<HubOrgKbDoc> = [
    {
      title: "标题",
      dataIndex: "title",
      ellipsis: true,
    },
    {
      title: "客户",
      dataIndex: "customer_key",
      width: 100,
      render: (v?: string) =>
        v ? <Tag color="orange">{v}</Tag> : (
          <Typography.Text type="secondary">组织</Typography.Text>
        ),
    },
    {
      title: "生效期",
      key: "effective",
      width: 150,
      render: (_, row) => {
        const from = row.effective_from || "…";
        const until = row.effective_until || "…";
        if (!row.effective_from && !row.effective_until) {
          return <Typography.Text type="secondary">长期</Typography.Text>;
        }
        return (
          <Typography.Text style={{ fontSize: 12 }}>
            {from} → {until}
          </Typography.Text>
        );
      },
    },
    {
      title: "文件",
      dataIndex: "filename",
      width: 120,
      ellipsis: true,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (status: string, row) => (
        <Tag color={statusColor(status)}>
          {status}
          {row.error ? ` · ${row.error.slice(0, 24)}` : ""}
        </Tag>
      ),
    },
    {
      title: "上传者",
      dataIndex: "uploaded_by",
      width: 100,
      ellipsis: true,
    },
    {
      title: "",
      key: "actions",
      width: 120,
      render: (_, row) => (
        <Space size={0}>
          {canManage ? (
            <Button type="link" size="small" onClick={() => openMetaEditor(row)}>
              元数据
            </Button>
          ) : null}
          {canWrite ? (
            <Button
              type="text"
              danger
              size="small"
              icon={<Trash2 size={14} />}
              onClick={() => handleDeleteDoc(row)}
            />
          ) : null}
        </Space>
      ),
    },
  ];

  if (loading) {
    return (
      <div className={styles.page}>
        <Spin />
      </div>
    );
  }

  if (forbidden) {
    return (
      <div className={styles.page}>
        <Empty description="无组织知识库权限（需要 org_kb:use）" />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.titleBlock}>
          <BookOpen size={22} />
          <div>
            <Typography.Title level={3} className={styles.title}>
              组织知识库
            </Typography.Title>
            <Typography.Paragraph type="secondary" className={styles.subtitle}>
              口径 / 案例 / 模板 / 客户资料。对话用 <code>kb_search</code>；
              <code>skill=</code> 走绑定库；带客户标的文档按授权隔离，禁止串客户。
            </Typography.Paragraph>
          </div>
        </div>
        <Space wrap>
          <Button icon={<RefreshCw size={14} />} onClick={() => void loadLibraries()}>
            刷新
          </Button>
          {canManage ? (
            <Button
              icon={<Download size={14} />}
              loading={exportingAll}
              onClick={() => void handleExportAll()}
            >
              导出全部备份
            </Button>
          ) : null}
          {canManage ? (
            <Button icon={<Shield size={14} />} onClick={() => openGrantEditor()}>
              客户授权
            </Button>
          ) : null}
          {canManage ? (
            <Button
              icon={<Link2 size={14} />}
              onClick={() => openBindEditor()}
            >
              绑定 Skill
            </Button>
          ) : null}
          {canWrite ? (
            <Button
              type="primary"
              icon={<Plus size={14} />}
              onClick={() => setCreateOpen(true)}
            >
              新建库
            </Button>
          ) : null}
        </Space>
      </header>

      <section className={styles.bindings}>
        <div className={styles.bindingsHead}>
          <Typography.Title level={5} style={{ margin: 0 }}>
            Skill ↔ 知识库绑定
          </Typography.Title>
          <Typography.Text type="secondary">
            官方技能已预置默认库；管理员可改。Agent 调用{" "}
            <code>kb_search(skill=&quot;…&quot;)</code> 时按优先级检索绑定库。
          </Typography.Text>
        </div>
        <Table
          rowKey="skill_name"
          size="small"
          loading={bindingsLoading}
          columns={bindingColumns}
          dataSource={bindings}
          pagination={false}
          locale={{ emptyText: "暂无绑定（打开本页会种子官方默认）" }}
        />
      </section>

      <section className={styles.bindings}>
        <div className={styles.bindingsHead}>
          <Typography.Title level={5} style={{ margin: 0 }}>
            客户维 ACL
          </Typography.Title>
          <Typography.Text type="secondary">
            文档可打 <code>customer_key</code>；未授权用户检索不到他客户资料。
            管理员 / <code>org_kb:manage</code> 可看全部。客户资料库上传必填客户标识。
          </Typography.Text>
        </div>
        <Table
          rowKey="user_id"
          size="small"
          loading={grantsLoading}
          columns={grantColumns}
          dataSource={grantsByUser}
          pagination={false}
          locale={{
            emptyText: canManage
              ? "暂无授权 — 点「客户授权」为顾问开通可见客户"
              : "你当前无客户专项授权（仅见组织级未打标文档）",
          }}
        />
      </section>

      <div className={styles.layout}>
        <aside className={styles.sidebar}>
          {libraries.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无知识库"
            />
          ) : (
            libraries.map((kb) => (
              <button
                key={kb.kb_id}
                type="button"
                className={
                  kb.kb_id === selectedKbId
                    ? `${styles.kbItem} ${styles.kbItemActive}`
                    : styles.kbItem
                }
                onClick={() => setSelectedKbId(kb.kb_id)}
              >
                <div className={styles.kbName}>{kb.name}</div>
                <div className={styles.kbMeta}>
                  <Tag>{KB_TYPE_LABEL[kb.kb_type] || kb.kb_type}</Tag>
                  <span>
                    {kb.ready_count ?? 0}/{kb.doc_count ?? 0} 就绪
                  </span>
                </div>
                {kb.description ? (
                  <div className={styles.kbDesc}>{kb.description}</div>
                ) : null}
              </button>
            ))
          )}
        </aside>

        <section className={styles.main}>
          {selectedKb ? (
            <>
              <div className={styles.mainHead}>
                <div>
                  <Typography.Title level={4} style={{ margin: 0 }}>
                    {selectedKb.name}
                  </Typography.Title>
                  <Typography.Text type="secondary">
                    slug: {selectedKb.slug} · 可见性 {selectedKb.visibility}
                  </Typography.Text>
                </div>
                <Space wrap>
                  <Button
                    icon={<Download size={14} />}
                    loading={exportingKb}
                    onClick={() => void handleExportKb()}
                  >
                    导出 zip
                  </Button>
                  {canWrite ? (
                    <>
                      <Input
                        style={{ width: 130 }}
                        placeholder={
                          selectedKb.kb_type === "customer"
                            ? "客户标识（必填）"
                            : "客户标识（可选）"
                        }
                        value={uploadCustomerKey}
                        onChange={(e) => setUploadCustomerKey(e.target.value)}
                      />
                      <Input
                        style={{ width: 120 }}
                        placeholder="生效起 YYYY-MM-DD"
                        value={uploadFrom}
                        onChange={(e) => setUploadFrom(e.target.value)}
                      />
                      <Input
                        style={{ width: 120 }}
                        placeholder="生效止 YYYY-MM-DD"
                        value={uploadUntil}
                        onChange={(e) => setUploadUntil(e.target.value)}
                      />
                      <Button onClick={() => setTextOpen(true)}>
                        沉淀文本
                      </Button>
                      <Upload
                        accept=".md,.txt,.docx,.json,.csv,.pdf"
                        showUploadList={false}
                        beforeUpload={(file) => {
                          void handleUpload(file);
                          return false;
                        }}
                        disabled={uploading}
                      >
                        <Button
                          type="primary"
                          loading={uploading}
                          icon={<UploadIcon size={14} />}
                        >
                          上传文档
                        </Button>
                      </Upload>
                    </>
                  ) : null}
                  {canManage ? (
                    <Button danger onClick={handleDeleteKb}>
                      删除库
                    </Button>
                  ) : null}
                </Space>
              </div>

              <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
                支持 Markdown / TXT / DOCX / PDF（扫描件需 OCR）；「沉淀文本」可把已审口径直接入库。
                「导出 zip」含 manifest、原文与可检索文本（客户标文档按你的授权过滤）。
                带客户标识的文档仅授权用户可召回；过期文档默认不进入{" "}
                <code>kb_search</code>。对话里点「企业知识」或输入{" "}
                <code>/kb</code> 可显式查库。
              </Typography.Paragraph>

              <Table
                rowKey="doc_id"
                size="small"
                loading={docsLoading}
                columns={docColumns}
                dataSource={docs}
                pagination={{ pageSize: 8 }}
                locale={{ emptyText: "该库暂无文档 — 上传一份口径 md 即可试检索" }}
              />

              <div className={styles.searchBox}>
                <Typography.Title level={5}>试检索</Typography.Title>
                <Space.Compact style={{ width: "100%", maxWidth: 640 }}>
                  <Input
                    placeholder="输入关键词，验证 kb_search 召回"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onPressEnter={() => void handleSearch()}
                  />
                  <Button
                    type="primary"
                    icon={<Search size={14} />}
                    loading={searching}
                    onClick={() => void handleSearch()}
                  >
                    检索
                  </Button>
                </Space.Compact>
                {feedbackStats && feedbackStats.total > 0 ? (
                  <Typography.Text type="secondary" style={{ display: "block", marginTop: 8 }}>
                    本库召回反馈：有用 {feedbackStats.useful} · 无用{" "}
                    {feedbackStats.not_useful}（共 {feedbackStats.total}）
                  </Typography.Text>
                ) : null}
                {searchHits.length > 0 ? (
                  <div className={styles.hits}>
                    {searchHits.map((hit, index) => {
                      const key = hit.chunk_id || hit.doc_id || String(index);
                      const voted = feedbackDone[key];
                      return (
                      <div key={key} className={styles.hit}>
                        <div className={styles.hitTitle}>
                          [{index + 1}] {hit.kb_name || hit.kb_slug} · {hit.title}
                          {hit.customer_key ? ` · ${hit.customer_key}` : ""}
                        </div>
                        <div className={styles.hitBody}>
                          {hit.snippet || hit.body}
                        </div>
                        <Space size="small" style={{ marginTop: 6 }}>
                          <Button
                            size="small"
                            type={voted === true ? "primary" : "default"}
                            disabled={voted !== undefined}
                            loading={feedbackBusy === key}
                            onClick={() => void handleFeedback(hit, true)}
                          >
                            有用
                          </Button>
                          <Button
                            size="small"
                            danger={voted === false}
                            disabled={voted !== undefined}
                            loading={feedbackBusy === key}
                            onClick={() => void handleFeedback(hit, false)}
                          >
                            无用
                          </Button>
                          {voted !== undefined ? (
                            <Typography.Text type="secondary">
                              已反馈
                            </Typography.Text>
                          ) : null}
                        </Space>
                      </div>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            </>
          ) : (
            <Empty description="请选择左侧知识库" />
          )}
        </section>
      </div>

      <Modal
        title="沉淀文本到知识库"
        open={textOpen}
        onCancel={() => setTextOpen(false)}
        onOk={() => void handleIngestText()}
        confirmLoading={textSaving}
        okText="入库"
        destroyOnClose
        width={640}
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <Typography.Text type="secondary">
            将对话里确认过的口径 / 话术粘贴入库（写入当前库
            {selectedKb ? `「${selectedKb.name}」` : ""}
            ）。客户标识与生效期沿用上方输入框。
          </Typography.Text>
          <div>
            <div>标题</div>
            <Input
              value={textTitle}
              onChange={(e) => setTextTitle(e.target.value)}
              placeholder="如：XX 产品投诉口径 v3"
            />
          </div>
          <div>
            <div>正文（Markdown / 纯文本）</div>
            <Input.TextArea
              value={textBody}
              onChange={(e) => setTextBody(e.target.value)}
              rows={12}
              placeholder="粘贴已审内容…"
            />
          </div>
        </Space>
      </Modal>

      <Modal
        title="文档元数据"
        open={metaOpen}
        onCancel={() => setMetaOpen(false)}
        onOk={() => void handleSaveMeta()}
        confirmLoading={metaSaving}
        okText="保存"
        destroyOnClose
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <Typography.Text type="secondary">
            {metaDoc?.title || "—"}
          </Typography.Text>
          <div>
            <div>客户标识</div>
            <Input
              value={metaCustomer}
              onChange={(e) => setMetaCustomer(e.target.value)}
              placeholder="留空=组织级"
            />
          </div>
          <div>
            <div>生效起（YYYY-MM-DD）</div>
            <Input
              value={metaFrom}
              onChange={(e) => setMetaFrom(e.target.value)}
              placeholder="留空=不限"
            />
          </div>
          <div>
            <div>生效止（YYYY-MM-DD）</div>
            <Input
              value={metaUntil}
              onChange={(e) => setMetaUntil(e.target.value)}
              placeholder="留空=不限"
            />
          </div>
        </Space>
      </Modal>

      <Modal
        title="客户维授权"
        open={grantOpen}
        onCancel={() => setGrantOpen(false)}
        onOk={() => void handleSaveGrants()}
        confirmLoading={grantSaving}
        okText="保存"
        destroyOnClose
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <div>
            <div>用户 ID</div>
            <Input
              value={grantUserId}
              onChange={(e) => setGrantUserId(e.target.value)}
              placeholder="Hub user_id"
            />
          </div>
          <div>
            <div>可见客户标识</div>
            <Select
              mode="tags"
              style={{ width: "100%" }}
              placeholder="输入客户 key 后回车，如 acme"
              value={grantKeys}
              onChange={(vals) =>
                setGrantKeys(
                  vals.map((v) => String(v).trim().toLowerCase()).filter(Boolean),
                )
              }
              options={knownCustomerKeys.map((k) => ({ value: k, label: k }))}
            />
          </div>
        </Space>
      </Modal>

      <Modal
        title="Skill ↔ 知识库绑定"
        open={bindOpen}
        onCancel={() => setBindOpen(false)}
        onOk={() => void handleSaveBinding()}
        confirmLoading={bindSaving}
        okText="保存"
        destroyOnClose
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <div>
            <div>Skill 名</div>
            <Select
              style={{ width: "100%" }}
              showSearch
              allowClear
              placeholder="选择官方技能或输入 skill name"
              value={bindSkill}
              onChange={(v) => setBindSkill(v)}
              options={OFFICIAL_SKILL_OPTIONS}
              optionFilterProp="label"
              dropdownRender={(menu) => (
                <>
                  {menu}
                  <div style={{ padding: 8, borderTop: "1px solid #f0f0f0" }}>
                    <Input
                      placeholder="自定义 skill name 后回车"
                      onPressEnter={(e) => {
                        const v = (e.target as HTMLInputElement).value
                          .trim()
                          .toLowerCase();
                        if (v) setBindSkill(v);
                      }}
                    />
                  </div>
                </>
              )}
            />
          </div>
          <div>
            <div>知识库（顺序即优先级）</div>
            <Select
              mode="multiple"
              style={{ width: "100%" }}
              placeholder="选择要绑定的库"
              value={bindSlugs}
              onChange={setBindSlugs}
              options={kbSlugOptions}
              optionFilterProp="label"
            />
          </div>
        </Space>
      </Modal>

      <Modal
        title="新建知识库"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => void handleCreate()}
        confirmLoading={creating}
        okText="创建"
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <div>
            <div>标识（slug）</div>
            <Input
              value={newSlug}
              onChange={(e) => setNewSlug(e.target.value)}
              placeholder="如 branch-koujing"
            />
          </div>
          <div>
            <div>名称</div>
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="显示名称"
            />
          </div>
          <div>
            <div>类型</div>
            <Select
              style={{ width: "100%" }}
              value={newType}
              onChange={setNewType}
              options={Object.entries(KB_TYPE_LABEL).map(([value, label]) => ({
                value,
                label,
              }))}
            />
          </div>
          <div>
            <div>说明</div>
            <Input.TextArea
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              rows={2}
            />
          </div>
        </Space>
      </Modal>
    </div>
  );
}
