export function relationshipModeLabel(mode: string): string {
  return mode === 'ai_partner' ? 'AI 恋人' : '朋友';
}

export function relationshipStageLabel(stage: string): string {
  if (stage === 'new') return '初识';
  if (stage === 'familiar') return '熟悉';
  if (stage === 'trusted') return '信赖';
  if (stage === 'close') return '亲近';
  return '正在了解';
}
