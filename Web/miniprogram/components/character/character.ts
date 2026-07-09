type AnimationName = 'idle' | 'sit';

type AnimationConfig = {
  src: string;
};

const ANIMATIONS: Record<AnimationName, AnimationConfig> = {
  idle: {
    src: '/assets/images/echo_idle.png',
  },
  sit: {
    src: '/assets/images/idle_sit.png',
  },
};

Component({
  properties: {
    chatExpanded: {
      type: Boolean,
      value: false,
      observer() {
        this.updateAnimation();
      },
    },
    sitCrop: {
      type: Object,
      value: {
        cropWidth: '750rpx',
        cropHeight: '500rpx',
        cropOffsetX: '0rpx',
        cropOffsetY: '0rpx',
        imageWidth: '800rpx',
        imageLeft: '-25rpx',
        imageTop: '-50rpx',
      },
    },
  },

  data: {
    activeAnimationSrc: ANIMATIONS.idle.src,
  },

  lifetimes: {
    attached() {
      this.updateAnimation();
    },
  },

  methods: {
    getActiveAnimationName(): AnimationName {
      return this.data.chatExpanded ? 'sit' : 'idle';
    },

    updateAnimation() {
      const animationName = this.getActiveAnimationName();
      this.setData({
        activeAnimationSrc: ANIMATIONS[animationName].src,
      });
    },
  },
});
