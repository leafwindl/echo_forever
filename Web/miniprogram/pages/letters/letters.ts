import { listLetters, markLetterRead } from '../../utils/api';
import type { DailyLetter } from '../../utils/api';

Page({
  data: {
    letters: [] as DailyLetter[],
    selected: null as DailyLetter | null,
    loading: true,
    errorText: '',
  },

  onShow() { void this.loadLetters(); },

  async loadLetters() {
    this.setData({ loading: true, errorText: '' });
    try {
      const result = await listLetters(50);
      this.setData({ letters: result.items, loading: false });
    } catch (error) {
      console.error('加载来信失败', error);
      this.setData({ loading: false, errorText: '暂时没能取回来信，请稍后重试。' });
    }
  },

  async onOpenLetter(event: WechatMiniprogram.BaseEvent) {
    const letterId = String(event.currentTarget.dataset.id || '');
    const letter = this.data.letters.find((item) => item.letter_id === letterId);
    if (!letter) return;
    this.setData({ selected: letter });
    if (letter.status === 'ready') {
      try {
        const updated = await markLetterRead(letterId);
        this.setData({
          selected: updated,
          letters: this.data.letters.map((item) => item.letter_id === letterId ? updated : item),
        });
      } catch (error) { console.warn('标记来信已读失败', error); }
    }
  },

  onCloseLetter() { this.setData({ selected: null }); },
});
