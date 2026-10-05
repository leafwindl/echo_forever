import common from '@ohos.app.ability.common';
import audio from '@ohos.multimedia.audio';
import media from '@ohos.multimedia.media';

/**
 * Optional study ambience. Playback failures are isolated from the focus
 * timer so the timer remains usable on devices with media issues.
 */
export class StudyFocusMedia {
  private rain?: media.AVPlayer;
  private writing?: media.AVPlayer;
  private prepareTask?: Promise<void>;

  async play(context: common.UIAbilityContext): Promise<void> {
    try {
      await this.prepare(context);
      const rain = this.rain;
      const writing = this.writing;
      if (rain !== undefined) await rain.play();
      if (writing !== undefined) await writing.play();
    } catch (error) {
      const message = `[EchoStudy] ambience playback unavailable: ${String(error)}`;
      console.error(message);
      throw new Error(message);
    }
  }

  async pause(): Promise<void> {
    try {
      if (this.rain !== undefined) await this.rain.pause();
    } catch (_) {
      // Optional media must not block the pause control.
    }
    try {
      if (this.writing !== undefined) await this.writing.pause();
    } catch (_) {
      // Optional media must not block the pause control.
    }
  }

  async stop(): Promise<void> {
    try {
      if (this.rain !== undefined) {
        await this.rain.stop();
        this.rain.seek(0);
      }
    } catch (_) {
      // Best effort cleanup.
    }
    try {
      if (this.writing !== undefined) {
        await this.writing.stop();
        this.writing.seek(0);
      }
    } catch (_) {
      // Best effort cleanup.
    }
  }

  async dispose(): Promise<void> {
    await this.stop();
    try {
      if (this.rain !== undefined) await this.rain.release();
    } catch (_) {
      // Best effort cleanup.
    }
    try {
      if (this.writing !== undefined) await this.writing.release();
    } catch (_) {
      // Best effort cleanup.
    }
    this.rain = undefined;
    this.writing = undefined;
    this.prepareTask = undefined;
  }

  private async prepare(context: common.UIAbilityContext): Promise<void> {
    if (this.rain !== undefined && this.writing !== undefined) return;
    if (this.prepareTask !== undefined) {
      await this.prepareTask;
      return;
    }
    this.prepareTask = this.preparePlayers(context);
    try {
      await this.prepareTask;
    } catch (error) {
      this.prepareTask = undefined;
      throw new Error(String(error));
    }
  }

  private async preparePlayers(context: common.UIAbilityContext): Promise<void> {
    const resourceManager = context.resourceManager;
    const rainFd = await resourceManager.getRawFd('rain.mp3');
    const writingFd = await resourceManager.getRawFd('writing.mp3');
    const rain = await media.createAVPlayer();
    const writing = await media.createAVPlayer();
    const audioRendererInfo: audio.AudioRendererInfo = {
      usage: audio.StreamUsage.STREAM_USAGE_MUSIC,
      rendererFlags: 0
    };

    const rainSource: media.AVFileDescriptor = {
      fd: rainFd.fd,
      offset: rainFd.offset,
      length: rainFd.length
    };
    const writingSource: media.AVFileDescriptor = {
      fd: writingFd.fd,
      offset: writingFd.offset,
      length: writingFd.length
    };

    try {
      this.attachDiagnostics(rain, 'rain');
      this.attachDiagnostics(writing, 'writing');

      rain.fdSrc = rainSource;
      await this.waitForState(rain, 'initialized', 'rain');
      rain.audioRendererInfo = audioRendererInfo;
      await this.prepareOne(rain, 'rain');

      writing.fdSrc = writingSource;
      await this.waitForState(writing, 'initialized', 'writing');
      writing.audioRendererInfo = audioRendererInfo;
      await this.prepareOne(writing, 'writing');

      rain.loop = true;
      writing.loop = true;
      rain.setVolume(1);
      writing.setVolume(1);
      this.rain = rain;
      this.writing = writing;
      console.info('[EchoStudy] ambience players prepared');
    } catch (error) {
      try {
        await rain.release();
      } catch (_) {
        // Best effort cleanup.
      }
      try {
        await writing.release();
      } catch (_) {
        // Best effort cleanup.
      }
      throw new Error(String(error));
    }
  }

  private attachDiagnostics(player: media.AVPlayer, name: string): void {
    player.on('stateChange', (state, reason) => {
      console.info(`[EchoStudy] ${name} state=${state}, reason=${JSON.stringify(reason)}`);
    });
    player.on('error', (error) => {
      console.error(`[EchoStudy] ${name} error=${String(error)}`);
    });
  }

  private async prepareOne(player: media.AVPlayer, name: string): Promise<void> {
    console.info(`[EchoStudy] ${name} prepare begin, state=${player.state}`);
    const prepared = this.waitForState(player, 'prepared', name);
    const prepareResult = player.prepare()
      .then(() => true)
      .catch((error: Object): boolean => {
        console.error(`[EchoStudy] ${name} prepare error=${String(error)}`);
        return false;
      });
    const completedByState = await Promise.race([prepared.then(() => true), prepareResult]);
    if (!completedByState && player.state !== 'prepared') {
      throw new Error(`${name} prepare failed`);
    }
    if (player.state !== 'prepared') {
      await this.waitForState(player, 'prepared', name);
    }
    console.info(`[EchoStudy] ${name} prepared`);
  }

  private waitForState(
    player: media.AVPlayer,
    target: media.AVPlayerState,
    name: string,
    timeoutMs: number = 12000
  ): Promise<void> {
    if (player.state === target) return Promise.resolve();
    return new Promise<void>((resolve, reject) => {
      let settled = false;
      const timeout = setTimeout(() => {
        if (settled) return;
        settled = true;
        player.off('stateChange', callback);
        reject(new Error(`${name} timed out waiting for ${target}, state=${player.state}`));
      }, timeoutMs);
      const callback: media.OnAVPlayerStateChangeHandle = (state, reason) => {
        if (state === target) {
          if (settled) return;
          settled = true;
          clearTimeout(timeout);
          player.off('stateChange', callback);
          resolve();
        } else if (state === 'error') {
          if (settled) return;
          settled = true;
          clearTimeout(timeout);
          player.off('stateChange', callback);
          reject(new Error(`${name} entered error while waiting for ${target}: ${JSON.stringify(reason)}`));
        }
      };
      player.on('stateChange', callback);
    });
  }
}
