import { IDLE_SPINE_ATLAS, IDLE_SPINE_SKELETON } from './idleSpineData';

type AnimationName = 'idle' | 'sit';

type CharacterAnimation = {
  src: string;
};

type SpineBoneDef = {
  name: string;
  parent?: string;
  x?: number;
  y?: number;
  rotation?: number;
};

type SpineSlotDef = {
  name: string;
  bone: string;
  attachment: string;
};

type SpineAttachmentDef = {
  x?: number;
  y?: number;
  rotation?: number;
  width: number;
  height: number;
};

type SpineJson = {
  skeleton: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  bones: SpineBoneDef[];
  slots: SpineSlotDef[];
  skins: Array<{
    name: string;
    attachments: Record<string, Record<string, SpineAttachmentDef>>;
  }>;
  animations: Record<string, {
    bones?: Record<string, {
      rotate?: Array<{ time?: number; angle?: number }>;
    }>;
  }>;
};

type AtlasRegion = {
  name: string;
  rotate: boolean;
  x: number;
  y: number;
  width: number;
  height: number;
};

type SpineSource = {
  skeleton: SpineJson;
  atlasRegions: Record<string, AtlasRegion>;
};

type BonePose = {
  x: number;
  y: number;
  rotation: number;
};

type SpineCanvasContext = WechatMiniprogram.CanvasRenderingContext.CanvasRenderingContext2D;
type SpineCanvasImage = ReturnType<WechatMiniprogram.Canvas['createImage']>;

const ANIMATIONS: Record<AnimationName, CharacterAnimation> = {
  idle: {
    src: '/assets/images/echo_idle.webp',
  },
  sit: {
    src: '/assets/images/idle_sit.png',
  },
};

const IDLE_SPINE_TEXTURE = '/assets/images/idle/BODY.png';
const IDLE_ANIMATION_NAME = 'animation';
const SPINE_LOG_PREFIX = '[spine-poc]';
const IDLE_SPINE_FIT_SCALE = 1.75;
const IDLE_SPINE_DRAW_SCALE = 1;
const IDLE_SPINE_OFFSET_X = 0;
const IDLE_SPINE_OFFSET_Y = 220;
const IDLE_SPINE_LAYOUT_SETTLE_MS = 360;

let spineSourceCache: SpineSource | undefined;
let spineCanvas: WechatMiniprogram.Canvas | undefined;
let spineContext: SpineCanvasContext | undefined;
let spineTexture: SpineCanvasImage | undefined;
let spineFrameId: number | undefined;
let spineStartTime = 0;
let spineCanvasWidth = 0;
let spineCanvasHeight = 0;
let spinePixelRatio = 1;
let spineRenderToken = 0;
let spineLayoutTimer: ReturnType<typeof setTimeout> | undefined;

function parseNumberPair(value: string): [number, number] {
  const parts = value.split(',').map((part) => Number(part.trim()));
  return [parts[0] || 0, parts[1] || 0];
}

function parseAtlas(atlasText: string): Record<string, AtlasRegion> {
  const lines = atlasText.split(/\r?\n/);
  const regions: Record<string, AtlasRegion> = {};
  let current: Partial<AtlasRegion> | undefined;

  function commitRegion() {
    if (!current || !current.name) {
      return;
    }

    regions[current.name] = {
      name: current.name,
      rotate: Boolean(current.rotate),
      x: current.x || 0,
      y: current.y || 0,
      width: current.width || 0,
      height: current.height || 0,
    };
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      continue;
    }

    const isProperty = rawLine.startsWith(' ') && line.includes(':');
    if (!isProperty && !line.includes(':') && line !== 'BODY.png') {
      commitRegion();
      current = { name: line };
      continue;
    }

    if (!current || !isProperty) {
      continue;
    }

    const separatorIndex = line.indexOf(':');
    const key = line.slice(0, separatorIndex).trim();
    const value = line.slice(separatorIndex + 1).trim();

    if (key === 'rotate') {
      current.rotate = value === 'true';
    } else if (key === 'xy') {
      const [x, y] = parseNumberPair(value);
      current.x = x;
      current.y = y;
    } else if (key === 'size') {
      const [width, height] = parseNumberPair(value);
      current.width = width;
      current.height = height;
    }
  }

  commitRegion();
  return regions;
}

function loadSpineSource(): SpineSource {
  if (spineSourceCache) {
    return spineSourceCache;
  }

  const skeleton = IDLE_SPINE_SKELETON as SpineJson;
  const atlasRegions = parseAtlas(IDLE_SPINE_ATLAS);
  spineSourceCache = { skeleton, atlasRegions };
  console.info(SPINE_LOG_PREFIX, 'loaded source', {
    json: 'inline idleSpineData.ts',
    atlas: 'inline idleSpineData.ts',
    texture: IDLE_SPINE_TEXTURE,
    regions: Object.keys(atlasRegions),
  });
  return spineSourceCache;
}

function loadCanvasImage(canvas: WechatMiniprogram.Canvas, src: string): Promise<SpineCanvasImage> {
  return new Promise((resolve, reject) => {
    const image = canvas.createImage();
    image.onload = () => resolve(image);
    image.onerror = (error) => reject(error);
    image.src = src;
  });
}

function degreesToRadians(degrees: number): number {
  return degrees * Math.PI / 180;
}

function interpolateRotateOffset(
  frames: Array<{ time?: number; angle?: number }> | undefined,
  time: number,
): number {
  if (!frames || !frames.length) {
    return 0;
  }

  const normalizedFrames = frames.map((frame, index) => ({
    time: frame.time !== undefined ? frame.time : (index === 0 ? 0 : 0),
    angle: frame.angle !== undefined ? frame.angle : 0,
  }));
  const duration = normalizedFrames[normalizedFrames.length - 1].time || 0;
  const localTime = duration > 0 ? time % duration : 0;

  for (let index = 0; index < normalizedFrames.length - 1; index += 1) {
    const from = normalizedFrames[index];
    const to = normalizedFrames[index + 1];
    if (localTime < from.time || localTime > to.time) {
      continue;
    }

    const span = to.time - from.time;
    const progress = span > 0 ? (localTime - from.time) / span : 0;
    return from.angle + (to.angle - from.angle) * progress;
  }

  return normalizedFrames[normalizedFrames.length - 1].angle;
}

function computeBonePoses(skeleton: SpineJson, time: number): Record<string, BonePose> {
  const poses: Record<string, BonePose> = {};
  const animation = skeleton.animations[IDLE_ANIMATION_NAME];

  for (const bone of skeleton.bones) {
    const animatedBone = animation && animation.bones
      ? animation.bones[bone.name]
      : undefined;
    const rotationOffset = interpolateRotateOffset(
      animatedBone ? animatedBone.rotate : undefined,
      time,
    );
    const localRotation = (bone.rotation || 0) + rotationOffset;
    const localX = bone.x || 0;
    const localY = bone.y || 0;

    if (bone.parent) {
      const parent = poses[bone.parent];
      if (!parent) {
        continue;
      }

      const parentRadians = degreesToRadians(parent.rotation);
      const cos = Math.cos(parentRadians);
      const sin = Math.sin(parentRadians);
      poses[bone.name] = {
        x: parent.x + localX * cos - localY * sin,
        y: parent.y + localX * sin + localY * cos,
        rotation: parent.rotation + localRotation,
      };
      continue;
    }

    poses[bone.name] = {
      x: localX,
      y: localY,
      rotation: localRotation,
    };
  }

  return poses;
}

function getCanvasPoint(skeleton: SpineJson, x: number, y: number, scale: number) {
  const centerX = skeleton.skeleton.x + skeleton.skeleton.width / 2;
  const centerY = skeleton.skeleton.y + skeleton.skeleton.height / 2;
  return {
    x: spineCanvasWidth / 2 + IDLE_SPINE_OFFSET_X + (x - centerX) * scale,
    y: spineCanvasHeight / 2 + IDLE_SPINE_OFFSET_Y - (y - centerY) * scale,
  };
}

function drawRegion(
  context: SpineCanvasContext,
  image: SpineCanvasImage,
  region: AtlasRegion,
  attachment: SpineAttachmentDef,
) {
  if (region.rotate) {
    context.rotate(Math.PI / 2);
    context.drawImage(
      image,
      region.x,
      region.y,
      region.height,
      region.width,
      -(attachment.height || 0) / 2,
      -(attachment.width || 0) / 2,
      attachment.height || 0,
      attachment.width || 0,
    );
    return;
  }

  context.drawImage(
    image,
    region.x,
    region.y,
    region.width,
    region.height,
    -(attachment.width || 0) / 2,
    -(attachment.height || 0) / 2,
    attachment.width || 0,
    attachment.height || 0,
  );
}

function drawSpineFrame(time: number) {
  if (!spineCanvas || !spineContext || !spineTexture) {
    return;
  }

  const source = loadSpineSource();
  const skeleton = source.skeleton;
  const poses = computeBonePoses(skeleton, time);
  const skin = skeleton.skins[0];
  const scale = Math.min(
    spineCanvasWidth * IDLE_SPINE_FIT_SCALE / skeleton.skeleton.width,
    spineCanvasHeight * IDLE_SPINE_FIT_SCALE / skeleton.skeleton.height,
  ) * IDLE_SPINE_DRAW_SCALE;

  spineContext.setTransform(spinePixelRatio, 0, 0, spinePixelRatio, 0, 0);
  spineContext.clearRect(0, 0, spineCanvasWidth, spineCanvasHeight);

  for (const slot of skeleton.slots) {
    const bonePose = poses[slot.bone];
    const slotAttachments = skin.attachments[slot.name];
    const attachment = slotAttachments ? slotAttachments[slot.attachment] : undefined;
    const region = source.atlasRegions[slot.attachment];
    if (!bonePose || !attachment || !region) {
      continue;
    }

    const attachmentX = attachment.x || 0;
    const attachmentY = attachment.y || 0;
    const boneRadians = degreesToRadians(bonePose.rotation);
    const worldX = bonePose.x + attachmentX * Math.cos(boneRadians) - attachmentY * Math.sin(boneRadians);
    const worldY = bonePose.y + attachmentX * Math.sin(boneRadians) + attachmentY * Math.cos(boneRadians);
    const point = getCanvasPoint(skeleton, worldX, worldY, scale);

    spineContext.save();
    spineContext.translate(point.x, point.y);
    spineContext.rotate(-degreesToRadians(bonePose.rotation + (attachment.rotation || 0)));
    spineContext.scale(scale, scale);
    drawRegion(spineContext, spineTexture, region, attachment);
    spineContext.restore();
  }
}

function clearSpineLayoutTimer() {
  if (spineLayoutTimer !== undefined) {
    clearTimeout(spineLayoutTimer);
    spineLayoutTimer = undefined;
  }
}

function stopSpineLoop() {
  clearSpineLayoutTimer();
  if (spineCanvas && spineFrameId !== undefined) {
    spineCanvas.cancelAnimationFrame(spineFrameId);
  }
  spineFrameId = undefined;
  spineRenderToken += 1;
}

function scheduleSpineFrame(token: number) {
  if (!spineCanvas || token !== spineRenderToken) {
    return;
  }

  spineFrameId = spineCanvas.requestAnimationFrame((timestamp: number) => {
    if (token !== spineRenderToken) {
      return;
    }

    if (!spineStartTime) {
      spineStartTime = timestamp;
    }

    drawSpineFrame((timestamp - spineStartTime) / 1000);
    scheduleSpineFrame(token);
  });
}

Component({
  data: {
    activeAnimationSrc: ANIMATIONS.idle.src,
  },

  properties: {
    chatExpanded: {
      type: Boolean,
      value: false,
      observer() {
        this.updateActiveAnimation();
      },
    },
    sitCrop: {
      type: Object,
      value: {
        cropWidth: '750rpx',
        cropHeight: '300rpx',
        cropOffsetX: '0rpx',
        cropOffsetY: '0rpx',
        imageWidth: '1200rpx',
        imageLeft: '-225rpx',
        imageTop: '-420rpx',
      },
    },
  },

  lifetimes: {
    attached() {
      this.updateActiveAnimation();
    },
    detached() {
      stopSpineLoop();
    },
  },

  methods: {
    getActiveAnimationName(): AnimationName {
      return this.data.chatExpanded ? 'sit' : 'idle';
    },

    updateActiveAnimation() {
      const animationName = this.getActiveAnimationName();
      this.setData({
        activeAnimationSrc: ANIMATIONS[animationName].src,
      }, () => {
        if (animationName === 'idle') {
          this.startIdleSpineAfterLayout();
          return;
        }

        stopSpineLoop();
      });
    },

    startIdleSpineAfterLayout() {
      clearSpineLayoutTimer();
      this.startIdleSpine();

      spineLayoutTimer = setTimeout(() => {
        spineLayoutTimer = undefined;
        if (this.getActiveAnimationName() === 'idle') {
          this.startIdleSpine();
        }
      }, IDLE_SPINE_LAYOUT_SETTLE_MS);
    },

    startIdleSpine() {
      stopSpineLoop();
      const token = spineRenderToken;

      this.createSelectorQuery()
        .select('#idleSpineCanvas')
        .fields({ node: true, size: true })
        .exec((results) => {
          const result = results && results.length
            ? results[0] as { node?: WechatMiniprogram.Canvas; width?: number; height?: number }
            : undefined;
          if (!result || !result.node || token !== spineRenderToken) {
            return;
          }

          spineCanvas = result.node;
          spineCanvasWidth = result.width || 1;
          spineCanvasHeight = result.height || 1;
          spinePixelRatio = wx.getSystemInfoSync().pixelRatio || 1;
          spineCanvas.width = spineCanvasWidth * spinePixelRatio;
          spineCanvas.height = spineCanvasHeight * spinePixelRatio;
          spineContext = spineCanvas.getContext('2d');

          try {
            loadSpineSource();
          } catch (error) {
            console.error(SPINE_LOG_PREFIX, 'failed to initialize source', error);
            return;
          }

          loadCanvasImage(spineCanvas, IDLE_SPINE_TEXTURE)
            .then((image) => {
              if (token !== spineRenderToken) {
                return;
              }

              spineTexture = image;
              spineStartTime = 0;
              scheduleSpineFrame(token);
            })
            .catch((error) => {
              console.error(SPINE_LOG_PREFIX, 'failed to load texture', error);
            });
        });
    },
  },
});
