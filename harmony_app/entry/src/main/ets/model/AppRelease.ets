export interface InstalledApp {
  bundleName: string;
  versionName: string;
  versionCode: number;
}

export interface HarmonyRelease {
  releaseId: string;
  packageName: string;
  versionName: string;
  versionCode: number;
  sizeBytes: number;
  sha256: string;
  releaseNotes: string[];
  mandatory: boolean;
}

export function parseHarmonyRelease(
  response: Record<string, Object>, installed: InstalledApp
): HarmonyRelease | undefined {
  if (response.update_available === false) return undefined;
  if (response.update_available !== true || !response.release || typeof response.release !== 'object') {
    throw new Error('更新信息校验失败，请稍后重试');
  }
  const value = response.release as Record<string, Object>;
  const hash = String(value.sha256 ?? '').toLowerCase();
  const versionCode = Number(value.version_code);
  const sizeBytes = Number(value.size_bytes);
  if (value.platform !== 'harmonyos' || value.channel !== 'internal' ||
    value.package_name !== installed.bundleName ||
    !Number.isSafeInteger(versionCode) || versionCode <= installed.versionCode ||
    !Number.isSafeInteger(sizeBytes) || sizeBytes <= 0 ||
    !/^[0-9a-f]{64}$/.test(hash) || !String(value.release_id ?? '').trim() ||
    !String(value.version_name ?? '').trim()) {
    throw new Error('更新包不是当前 Echo 的有效鸿蒙升级包，已停止更新');
  }
  const notes: string[] = [];
  if (Array.isArray(value.release_notes)) {
    value.release_notes.forEach((note: Object) => {
      const text = String(note).trim();
      if (text) notes.push(text);
    });
  }
  return {
    releaseId: String(value.release_id), packageName: String(value.package_name),
    versionName: String(value.version_name), versionCode, sizeBytes, sha256: hash,
    releaseNotes: notes, mandatory: value.mandatory === true
  };
}

export function validateDownloadUrl(value: Object | undefined): string {
  const url = String(value ?? '');
  if (!/^https:\/\/[a-zA-Z0-9.-]+(?::\d+)?(?:\/|$)/.test(url)) {
    throw new Error('更新下载地址无效，请稍后重试');
  }
  return url;
}
