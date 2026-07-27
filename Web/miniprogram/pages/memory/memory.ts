import {
  clearMemories,
  deleteMemory,
  listMemories,
  MemoryItem,
  MemoryStatus,
} from '../../utils/api';
import { clearSession } from '../../utils/session';

type MemoryTab = 'active' | 'deleted';

interface MemoryViewItem extends MemoryItem {
  confidenceLabel: string;
  updatedLabel: string;
}

const TYPE_LABELS: Record<string, string> = {
  profile: '身份',
  preference: '偏好',
  relationship: '关系',
  goal: '目标',
  event: '事件',
  boundary: '边界',
};

function formatUpdatedAt(value?: string): string {
  if (!value) return '';
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return value;
  const month = String(timestamp.getMonth() + 1).padStart(2, '0');
  const day = String(timestamp.getDate()).padStart(2, '0');
  const hour = String(timestamp.getHours()).padStart(2, '0');
  const minute = String(timestamp.getMinutes()).padStart(2, '0');
  return `${month}-${day} ${hour}:${minute}`;
}

Page({
  data: {
    memories: [] as MemoryViewItem[],
    activeTab: 'active' as MemoryTab,
    isLoading: false,
    isClearing: false,
    errorText: '',
  },

  onShow() {
    this.loadMemories();
  },

  getStatusForTab(): MemoryStatus {
    return this.data.activeTab;
  },

  loadMemories() {
    this.setData({ isLoading: true, errorText: '' });
    listMemories(this.getStatusForTab(), 100)
      .then((result) => {
        const memories = Array.isArray(result.memories) ? result.memories : [];
        this.setData({
          memories: memories.map((memory) => ({
            ...memory,
            memory_type: TYPE_LABELS[memory.memory_type] || memory.memory_type,
            confidenceLabel: Math.round(memory.confidence * 100) + '%',
            updatedLabel: formatUpdatedAt(memory.updated_at),
          })),
          isLoading: false,
        });
      })
      .catch((err) => {
        console.error('加载记忆失败', err);
        if (err && err.isUnauthorized) {
          this.expireSession();
          return;
        }
        this.setData({
          isLoading: false,
          errorText: '记忆加载失败',
        });
      });
  },

  onSwitchTab(e: WechatMiniprogram.TouchEvent) {
    const tab = e.currentTarget.dataset.tab as MemoryTab;
    if (!tab || tab === this.data.activeTab) return;

    this.setData({ activeTab: tab, memories: [] });
    this.loadMemories();
  },

  onRefresh() {
    this.loadMemories();
  },

  onDeleteMemory(e: WechatMiniprogram.TouchEvent) {
    const memoryId = e.currentTarget.dataset.id as string;
    if (!memoryId) return;

    wx.showModal({
      title: '删除这条记忆',
      content: '删除后 Echo 不会继续使用这条长期记忆。',
      confirmText: '删除',
      confirmColor: '#E04F5F',
      success: (res) => {
        if (!res.confirm) return;

        wx.showLoading({ title: '删除中...' });
        deleteMemory(memoryId)
          .then(() => {
            wx.hideLoading();
            wx.showToast({ title: '已删除', icon: 'success' });
            this.loadMemories();
          })
          .catch((err) => {
            wx.hideLoading();
            console.error('删除记忆失败', err);
            if (err && err.isUnauthorized) this.expireSession();
            else wx.showToast({ title: '删除失败', icon: 'none' });
          });
      },
    });
  },

  onClearMemories() {
    if (this.data.isClearing) return;

    wx.showModal({
      title: '清空长期记忆',
      content: '清空后 Echo 不会继续使用当前保存的长期记忆。',
      confirmText: '清空',
      confirmColor: '#E04F5F',
      success: (res) => {
        if (!res.confirm) return;

        this.setData({ isClearing: true });
        wx.showLoading({ title: '清空中...' });
        clearMemories()
          .then((result) => {
            wx.hideLoading();
            wx.showToast({ title: `已清空 ${result.cleared_count} 条`, icon: 'none' });
            this.setData({ isClearing: false });
            this.loadMemories();
          })
          .catch((err) => {
            wx.hideLoading();
            console.error('清空记忆失败', err);
            this.setData({ isClearing: false });
            if (err && err.isUnauthorized) this.expireSession();
            else wx.showToast({ title: '清空失败', icon: 'none' });
          });
      },
    });
  },

  expireSession() {
    clearSession();
    wx.reLaunch({ url: '/pages/onboarding/onboarding' });
  },
});
