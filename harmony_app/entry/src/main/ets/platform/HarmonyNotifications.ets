import common from '@ohos.app.ability.common';
import notificationManager from '@ohos.notificationManager';
import reminderAgentManager from '@ohos.reminderAgentManager';
import preferences from '@ohos.data.preferences';

export class HarmonyNotifications {
  private operations: Promise<void> = Promise.resolve();

  async enabled(): Promise<boolean> {
    return notificationManager.isNotificationEnabled();
  }

  async request(context: common.UIAbilityContext): Promise<boolean> {
    await notificationManager.requestEnableNotification(context);
    return this.enabled();
  }

  async openSettings(context: common.UIAbilityContext): Promise<void> {
    await notificationManager.openNotificationSettings(context);
  }

  cancel(context: common.UIAbilityContext): Promise<void> {
    const operation = this.operations.then(() => this.cancelCurrent(context));
    this.operations = operation.catch(() => {});
    return operation;
  }

  private async cancelCurrent(context: common.UIAbilityContext): Promise<void> {
    const store = await preferences.getPreferences(context, 'echo-reminders');
    const id = Number(await store.get('focus-reminder', -1));
    if (id >= 0) {
      await reminderAgentManager.cancelReminder(id);
      await store.delete('focus-reminder');
      await store.flush();
    }
  }

  schedule(context: common.UIAbilityContext, timestamp: number): Promise<void> {
    const operation = this.operations.then(() => this.scheduleCurrent(context, timestamp));
    this.operations = operation.catch(() => {});
    return operation;
  }

  private async scheduleCurrent(context: common.UIAbilityContext, timestamp: number): Promise<void> {
    await this.cancelCurrent(context);
    if (timestamp <= Date.now() || !await this.enabled()) return;
    const request: reminderAgentManager.ReminderRequestTimer = {
      reminderType: reminderAgentManager.ReminderType.REMINDER_TYPE_TIMER,
      triggerTimeInSeconds: Math.max(1, Math.ceil((timestamp - Date.now()) / 1000)),
      title: '一起学习',
      content: '这一轮学习结束了，休息一下吧。',
      expiredContent: '这一轮学习结束了，休息一下吧。',
      notificationId: 7101,
      ringDuration: 0,
      wantAgent: { pkgName: context.applicationInfo.name, abilityName: 'EntryAbility' }
    };
    const id = await reminderAgentManager.publishReminder(request);
    const store = await preferences.getPreferences(context, 'echo-reminders');
    await store.put('focus-reminder', id);
    await store.flush();
  }
}
