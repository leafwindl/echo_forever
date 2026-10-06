import common from '@ohos.app.ability.common';
import bundleManager from '@ohos.bundle.bundleManager';
import request from '@ohos.request';
import fs from '@ohos.file.fs';
import fileUri from '@ohos.file.fileuri';
import crypto from '@ohos.security.cryptoFramework';
import { HarmonyRelease, InstalledApp, validateDownloadUrl } from '../model/AppRelease';

export class HarmonyUpdater {
  private task?: request.DownloadTask;
  private abort?: () => void;

  async installed(): Promise<InstalledApp> {
    const info = await bundleManager.getBundleInfoForSelf(0);
    return { bundleName: info.name, versionName: info.versionName, versionCode: info.versionCode };
  }

  async download(
    context: common.UIAbilityContext, url: string, release: HarmonyRelease, progress: (value: number) => void
  ): Promise<string> {
    validateDownloadUrl(url);
    const path = `${context.cacheDir}/echo-update-${release.versionCode}.hap`;
    if (fs.accessSync(path)) await fs.unlink(path);
    const task = await request.downloadFile(context, {
      url, filePath: path, enableMetered: true, enableRoaming: false, title: 'Echo 更新'
    });
    this.task = task;
    try {
      await new Promise<void>((resolve, reject) => {
        let settled = false;
        const timer = setTimeout(() => finish(new Error('更新下载超时，请重试')), 20 * 60 * 1000);
        const poll = setInterval(() => {
          void task.getTaskInfo().then((info: request.DownloadInfo) => {
            if (info.status === request.SESSION_SUCCESSFUL) finish();
            else if (info.status === request.SESSION_FAILED) finish(new Error('更新下载失败，请重试'));
          }).catch(() => {});
        }, 750);
        const finish = (error?: Error): void => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          clearInterval(poll);
          this.abort = undefined;
          if (error) reject(error);
          else resolve();
        };
        this.abort = () => finish(new Error('更新下载已取消'));
        task.on('progress', (received: number, total: number) => {
          progress(Math.min(1, received / (total > 0 ? total : release.sizeBytes)));
        });
        task.on('complete', () => finish());
        task.on('fail', (reason: number) => finish(new Error(`更新包下载失败 (${reason})，请重试`)));
        task.on('remove', () => finish(new Error('更新下载已取消')));
      });
      return path;
    } catch (error) {
      await task.delete().catch(() => {});
      if (fs.accessSync(path)) await fs.unlink(path);
      throw new Error(String(error));
    } finally {
      task.off('progress');
      task.off('complete');
      task.off('fail');
      task.off('remove');
      this.task = undefined;
    }
  }

  async verify(path: string, release: HarmonyRelease): Promise<void> {
    try {
      const stat = await fs.stat(path);
      if (stat.size !== release.sizeBytes) throw new Error('安装包下载不完整，请重新下载');
      const digest = crypto.createMd('SHA256');
      const file = await fs.open(path, fs.OpenMode.READ_ONLY);
      try {
        const buffer = new ArrayBuffer(256 * 1024);
        let count = 0;
        while ((count = await fs.read(file.fd, buffer)) > 0) {
          await digest.update({ data: new Uint8Array(buffer.slice(0, count)) });
        }
      } finally {
        await fs.close(file);
      }
      const hash = (await digest.digest()).data;
      let hex = '';
      hash.forEach((byte: number) => hex += byte.toString(16).padStart(2, '0'));
      if (hex !== release.sha256) throw new Error('安装包 SHA-256 校验失败，请重新下载');
    } catch (error) {
      if (fs.accessSync(path)) await fs.unlink(path);
      throw new Error(String(error));
    }
  }

  async openInstaller(context: common.UIAbilityContext, path: string): Promise<void> {
    try {
      // Handoff only: the system must verify the HAP signature and bundle identity.
      await context.startAbility({
        action: 'ohos.want.action.viewData', uri: fileUri.getUriFromPath(path),
        type: 'application/vnd.huawei.hap', flags: 1
      });
    } catch (_) {
      throw new Error('当前设备不允许此开发包拉起 HAP 安装程序。请使用 DevEco 安装同签名更新包；正式发布需使用鸿蒙认可的分发渠道。');
    }
  }

  cancel(): void {
    this.abort?.();
    if (this.task) void this.task.delete().catch(() => {});
  }
}
