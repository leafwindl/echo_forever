type AnimationName = 'idle' | 'sit';

type CharacterAnimation = {
  src: string;
};

const ANIMATIONS: Record<AnimationName, CharacterAnimation> = {
  idle: {
    src: '/assets/images/echo_idle.webp',
  },
  sit: {
    src: '/assets/images/idle_sit.webp',
  },
};

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
  },

  methods: {
    getActiveAnimationName(): AnimationName {
      return this.data.chatExpanded ? 'sit' : 'idle';
    },

    updateActiveAnimation() {
      this.setData({
        activeAnimationSrc: ANIMATIONS[this.getActiveAnimationName()].src,
      });
    },
  },
});
