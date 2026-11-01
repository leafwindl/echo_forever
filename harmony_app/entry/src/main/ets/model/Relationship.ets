export function relationshipModeLabel(mode: string): string {
  return mode === 'ai_partner' ? 'AI 恋人' : '朋友';
}

export function relationshipTypeLabel(value: string): string {
  if (value === 'friend') return '朋友';
  if (value === 'ambiguous') return '暧昧';
  if (value === 'partner') return '恋人';
  return '初识';
}

export function relationshipDirectionLabel(value: string): string {
  if (value === 'friend') return '朋友';
  if (value === 'ambiguous') return '暧昧';
  if (value === 'partner') return '恋人';
  return '更亲近';
}

export function relationshipStageLabel(stage: string): string {
  if (stage === 'new') return '初识';
  if (stage === 'familiar') return '熟悉';
  if (stage === 'trusted') return '信赖';
  if (stage === 'close') return '亲近';
  return '正在了解';
}
