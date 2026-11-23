export const SOURCE_LABELS: Record<string, string> = {
  qwenpaw: "小蜜蜂",
  clawhub: "ClawHub",
  modelscope: "ModelScope",
  aliyun: "Aliyun",
  "beeagent-org": "组织技能",
};

export function sourceLabel(source: string, label?: string | null): string {
  return label || SOURCE_LABELS[source] || source;
}
