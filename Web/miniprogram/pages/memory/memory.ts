import {
  clearMemories,
  deleteMemory,
  listMemories,
  MemoryItem,
  MemoryStatus,
  USER_ID_STORAGE_KEY,
} from '../../utils/api';

type MemoryTab = 'active' | 'deleted';

const TYPE_LABELS: Record<string, string> = {
  profile: '身份',
  preference: '偏好',
  relationship: '关系',
  goal: '目标',
  event: '事件',
  boundary: '边界',
};

Page({
  data: {
    userId: '',
    memories: [] as MemoryItem[],
    activeTab: 'active' as MemoryTab,
    isLoading: false,
    isClearing: false,
    errorText: '',
  },

  onLoad() {
    const userId = wx.getStorageSync(USER_ID_STORAGE_KEY);
    if (typeof userId === 'string' && userId) {
      this.setData({ userId });
    }
  },

  onShow() {
    this.loadMemories();
  },

  getStatusForTab(): MemoryStatus {
    return this.data.activeTab;
  },

  loadMemories() {
    if (!this.data.userId) {
      this.setData({ memories: [], errorText: '请先返回聊天页完成登录' });
      return;
    }

    this.setData({ isLoading: true, errorText: '' });
    listMemories(this.data.userId, this.getStatusForTab(), 100)
      .then((result) => {
        const memories = Array.isArray(result.memories) ? result.memories : [];
        this.setData({
          memories: memories.map((memory) => ({
            ...memory,
            memory_type: TYPE_LABELS[memory.memory_type] || memory.memory_type,
          })),
          isLoading: false,
        });
      })
      .catch((err) => {
        console.error('加载记忆失败', err);
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
    if (!memoryId || !this.data.userId) return;

    wx.showModal({
      title: '删除这条记忆',
      content: '删除后 Echo 不会继续使用这条长期记忆。',
      confirmText: '删除',
      confirmColor: '#E04F5F',
      success: (res) => {
        if (!res.confirm) return;

        wx.showLoading({ title: '删除中...' });
        deleteMemory(this.data.userId, memoryId)
          .then(() => {
            wx.hideLoading();
            wx.showToast({ title: '已删除', icon: 'success' });
            this.loadMemories();
          })
          .catch((err) => {
            wx.hideLoading();
            console.error('删除记忆失败', err);
            wx.showToast({ title: '删除失败', icon: 'none' });
          });
      },
    });
  },

  onClearMemories() {
    if (!this.data.userId || this.data.isClearing) return;

    wx.showModal({
      title: '清空长期记忆',
      content: '清空后 Echo 不会继续使用当前保存的长期记忆。',
      confirmText: '清空',
      confirmColor: '#E04F5F',
      success: (res) => {
        if (!res.confirm) return;

        this.setData({ isClearing: true });
        wx.showLoading({ title: '清空中...' });
        clearMemories(this.data.userId)
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
            wx.showToast({ title: '清空失败', icon: 'none' });
          });
      },
    });
  },
});
