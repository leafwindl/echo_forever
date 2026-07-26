type AudioContext = ReturnType<typeof wx.createInnerAudioContext>;

let activeAudioContext: AudioContext | null = null;
let cancelActivePlayback: (() => void) | null = null;

export function stopVoice(): void {
  const cancelPlayback = cancelActivePlayback;
  cancelActivePlayback = null;
  cancelPlayback?.();

  const audioContext = activeAudioContext;
  activeAudioContext = null;
  audioContext?.stop();
  audioContext?.destroy();
}

function downloadVoiceFile(url: string): Promise<string> {
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url,
      success: (res) => {
        if (res.statusCode !== 200) {
          console.error('音频下载失败', res);
          reject(new Error('音频下载失败'));
          return;
        }
        resolve(res.tempFilePath);
      },
      fail: (err) => {
        console.error('音频下载失败', err);
        reject(new Error('音频下载失败'));
      },
    });
  });
}

function playDownloadedVoice(filePath: string): Promise<void> {
  stopVoice();

  return new Promise((resolve, reject) => {
    let settled = false;
    const audioContext = wx.createInnerAudioContext();

    const settle = (error?: Error) => {
      if (settled) return;
      settled = true;
      if (cancelActivePlayback === cancelPlayback) {
        cancelActivePlayback = null;
      }
      if (activeAudioContext === audioContext) {
        activeAudioContext = null;
      }
      audioContext.destroy();

      if (error) {
        reject(error);
      } else {
        resolve();
      }
    };

    const cancelPlayback = () => settle();
    cancelActivePlayback = cancelPlayback;
    activeAudioContext = audioContext;
    audioContext.src = filePath;
    audioContext.onEnded(() => settle());
    audioContext.onStop(() => settle());
    audioContext.onError((err) => {
      console.error('播放失败', err);
      settle(new Error('音频播放失败'));
    });
    audioContext.play();
  });
}

export async function playVoice(url: string): Promise<void> {
  const filePath = await downloadVoiceFile(url);
  await playDownloadedVoice(filePath);
}

export async function playVoiceSegments(
  urls: string[],
  shouldContinue: () => boolean,
): Promise<void> {
  if (!urls.length || !shouldContinue()) return;

  let nextDownload: Promise<string> | null = downloadVoiceFile(urls[0]);
  for (let index = 0; index < urls.length && nextDownload; index += 1) {
    const filePath = await nextDownload;
    if (!shouldContinue()) return;

    nextDownload = index + 1 < urls.length ? downloadVoiceFile(urls[index + 1]) : null;
    await playDownloadedVoice(filePath);
  }
}
