export function playVoice(url: string): void {
  wx.downloadFile({
    url,
    success: (res) => {
      if (res.statusCode !== 200) {
        console.error('音频下载失败', res);
        wx.showToast({ title: '音频下载失败', icon: 'none' });
        return;
      }

      const innerAudio = wx.createInnerAudioContext();
      innerAudio.src = res.tempFilePath;
      innerAudio.onError((err) => {
        console.error('播放失败', err);
        wx.showToast({ title: '播放失败', icon: 'none' });
      });
      innerAudio.play();
    },
    fail: (err) => {
      console.error('音频下载失败', err);
      wx.showToast({ title: '音频下载失败', icon: 'none' });
    },
  });
}
