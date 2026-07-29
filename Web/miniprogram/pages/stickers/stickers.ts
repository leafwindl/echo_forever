import { confirmSticker, deleteSticker, listStickers, uploadSticker } from '../../utils/api';
import type { StickerItem } from '../../utils/api';

Page({
  data: { items: [] as StickerItem[], loading: true },
  onShow() { void this.load(); },
  async load() {
    try { this.setData({ items: await listStickers(), loading: false }); }
    catch (error) { console.error(error); this.setData({ loading: false }); }
  },
  onChoose() {
    wx.chooseMedia({ count: 1, mediaType: ['image'], success: (result) => {
      const path = result.tempFiles[0]?.tempFilePath;
      if (path) void this.save(path);
    }});
  },
  async save(path: string) {
    wx.showLoading({ title: '保存中' });
    try {
      const uploaded = await uploadSticker(path);
      await confirmSticker(uploaded.sticker_id);
      await this.load();
      wx.showToast({ title: '已存进私人库', icon: 'success' });
    } catch (error) {
      console.error(error); wx.showToast({ title: '保存失败', icon: 'none' });
    } finally { wx.hideLoading(); }
  },
  onDelete(event: WechatMiniprogram.BaseEvent) {
    const id = String(event.currentTarget.dataset.id || '');
    wx.showModal({ title: '删除表情包', content: '只会从你的私人库删除。', success: (result) => {
      if (result.confirm) void this.remove(id);
    }});
  },
  async remove(id: string) {
    try { await deleteSticker(id); await this.load(); }
    catch (error) { console.error(error); wx.showToast({ title: '删除失败', icon: 'none' }); }
  },
});
