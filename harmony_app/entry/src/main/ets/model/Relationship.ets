export function relationshipStageLabel(stage: string): string {
  if (stage === 'new') return '初识';
  if (stage === 'familiar') return '熟悉';
  if (stage === 'ambiguous') return '暧昧';
  if (stage === 'lover') return '恋人';
  if (stage === 'beloved') return '爱人';
  return '正在了解';
}
